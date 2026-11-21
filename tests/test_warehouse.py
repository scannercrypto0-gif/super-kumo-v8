"""Generated source fixtures only. No provider, task or WS service calls."""
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import json
from zipfile import ZipFile, ZIP_DEFLATED

import pytest

from aql.warehouse.engine import HistoricalWarehouse, DAY, parse_archive
from aql.warehouse.storage import seal
from aql.warehouse.source import VisionHTTP, HOST
from aql.warehouse.adapters import register_window

START = 1704067200000
KEY = 'data/spot/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01-01.zip'
AUTH = dict(bulk_download_ref='TEST_ONLY', source_rights_ref='TEST_ONLY', network_permission_ref='TEST_ONLY')


def fixture(start=START, key=KEY, count=1440, missing=(), changed=None, unit=1):
    data = []
    for i in range(count):
        if i in missing:
            continue
        opened = (start + i * 60000) * unit
        close = '2' if i == changed else '1'
        data.append(f'{opened},1,2,1,{close},3,{opened+60000*unit-1},4,1,2,3,0\n')
    out = BytesIO()
    with ZipFile(out, 'w', compression=ZIP_DEFLATED) as z:
        z.writestr(key.rsplit('/', 1)[1][:-4] + '.csv', ''.join(data))
    raw = out.getvalue()
    checksum = (seal(raw) + '  ' + key.rsplit('/', 1)[1] + '\n').encode()
    return raw, checksum


def warehouse(path, **kw):
    return HistoricalWarehouse(path, reserve=0, test_root=True, **kw)


def test_replay_restart_native_read_and_gap_repair(tmp_path):
    raw, check = fixture(missing=(7,))
    w = warehouse(tmp_path)
    with w.writer():
        first = w.import_archive(raw, check, KEY, observed_ms=START+DAY)
        assert first['inserted_rows'] == 1439
        assert w.report()['internal_gaps'] == [[START+7*60000, START+8*60000]]
    w = warehouse(tmp_path)
    with w.writer():
        repeat = w.import_archive(raw, check, KEY, observed_ms=START+2*DAY)
        assert repeat['inserted_rows'] == 0
        repaired, check2 = fixture()
        assert w.import_archive(repaired, check2, KEY, observed_ms=START+2*DAY)['inserted_rows'] == 1
    report = w.report()
    assert report['one_minute_rows'] == 1440 and not report['internal_gaps']
    assert report['available_complete_projections']['15m'] == 96
    assert len(list((tmp_path/'raw').glob('*.zip'))) == 2
    row = w.query('15m', START, START+900000, cutoff_ms=START+2*DAY)[0]
    assert row['v'] == '45' and row['source_class'] == 'RETROSPECTIVE_NON_PIT'
    from research_wp_r0.historical_library import HistoricalLibrary
    lib = HistoricalLibrary()
    manifest = register_window(w, lib, dataset_id='warehouse-test', interval='15m',
                               start_ms=START, end_ms=START+DAY, cutoff_ms=START+2*DAY)
    assert manifest.bar_count == 96 and manifest.verify_integrity()


def test_corruption_conflict_future_and_immutability(tmp_path):
    w = warehouse(tmp_path)
    raw, check = fixture()
    with w.writer():
        with pytest.raises(ValueError, match='CHECKSUM'):
            w.import_archive(raw+b'x', check, KEY, observed_ms=START+DAY)
        assert not list((tmp_path/'bars').glob('*.sqlite'))
        w.import_archive(raw, check, KEY, observed_ms=START+DAY)
        before = (tmp_path/'bars/2024-01-01.sqlite').read_bytes()
        changed, check2 = fixture(changed=2)
        with pytest.raises(ValueError, match='SOURCE_BAR_CONFLICT'):
            w.import_archive(changed, check2, KEY, observed_ms=START+DAY)
        assert (tmp_path/'bars/2024-01-01.sqlite').read_bytes() == before
        with pytest.raises(ValueError, match='INCOMPLETE_SOURCE'):
            w.import_archive(raw, check, KEY, observed_ms=START+DAY-1)
    with pytest.raises(ValueError, match='FUTURE|UNAVAILABLE'):
        w.query('15m', START, START+900000, cutoff_ms=START+900000)


def test_storage_caps_paths_links_lock_and_unknown_data(tmp_path):
    w = warehouse(tmp_path/'cap', cap=1000)
    with w.writer():
        with pytest.raises(ValueError, match='BUDGET'):
            w.write_once('raw/test', b'x'*1001)
        assert not (tmp_path/'cap/raw/test').exists()
        for name in ('../escaped', 'raw/../../escaped', '/escaped', 'raw/C:escaped'):
            with pytest.raises(ValueError, match='PATH_ESCAPE'):
                w.path(name)
        other = warehouse(tmp_path/'cap', cap=1000)
        with pytest.raises(ValueError, match='BUSY'):
            with other.writer():
                pass
    outside = tmp_path/'outside'
    outside.mkdir()
    symlink = tmp_path/'linked'
    try:
        symlink.symlink_to(outside, target_is_directory=True)
    except OSError:
        pass  # Windows runner without symlink privilege; reparse covered separately.
    else:
        with pytest.raises(ValueError, match='REPARSE'):
            warehouse(symlink)
    occupied = tmp_path/'occupied'
    occupied.mkdir()
    (occupied/'existing').write_text('keep')
    with pytest.raises(ValueError, match='UNMANAGED'):
        with warehouse(occupied).writer():
            pass
    assert (occupied/'existing').read_text() == 'keep'


@pytest.mark.parametrize('unit,start,key', [
    (1, START, KEY),
    (1000, 1735689600000, KEY.replace('2024-01-01', '2025-01-01')),
])
def test_timestamp_units(unit, start, key):
    raw, check = fixture(start, key, unit=unit)
    rows, meta = parse_archive(raw, check, key, start+DAY)
    assert rows[-1]['open_ms'] == start+1439*60000
    assert meta['timestamp_unit'] == ('us' if unit == 1000 else 'ms')


class Response(BytesIO):
    def __init__(self, raw, status=200, headers=None, fail_after=None):
        super().__init__(raw)
        self.status = status
        self.headers = headers or {'Content-Length': str(len(raw))}
        self.fail_after = fail_after
    def read(self, size=-1):
        if self.fail_after is not None:
            if self.tell() >= self.fail_after:
                raise ConnectionResetError('fixture disconnect')
            size = min(size, self.fail_after-self.tell())
        return super().read(size)


def test_interrupted_download_resumes_range_and_checksum(tmp_path):
    raw, check = fixture()
    requests = []
    disconnected = [False]
    def opener(req, timeout):
        requests.append((req.full_url, dict(req.header_items())))
        if req.full_url.endswith('.CHECKSUM'):
            return Response(check)
        offset = int(req.get_header('Range').split('=')[1].split('-')[0]) if req.has_header('Range') else 0
        if not disconnected[0]:
            disconnected[0] = True
            return Response(raw, fail_after=200)
        assert offset == 200
        return Response(raw[offset:], 206, {'Content-Range': f'bytes {offset}-{len(raw)-1}/{len(raw)}'})
    http = VisionHTTP(authority=AUTH, opener=opener)
    w = warehouse(tmp_path)
    with w.writer():
        with pytest.raises(ConnectionResetError):
            http.acquire(w, KEY, expected_size=len(raw))
    with warehouse(tmp_path).writer() as w:
        path, retained = http.acquire(w, KEY, expected_size=len(raw))
        assert path.read_bytes() == raw and retained == check
    assert any('Range' in h for _, h in requests)


def test_recover_after_shard_commit_before_catalog(tmp_path, monkeypatch):
    w = warehouse(tmp_path)
    raw, check = fixture()
    original = w.write_once
    def crash(relative, data):
        if relative.startswith('catalog/') and relative != 'catalog/warehouse-policy.json':
            raise OSError('fixture crash')
        return original(relative, data)
    with w.writer():
        monkeypatch.setattr(w, 'write_once', crash)
        with pytest.raises(OSError, match='crash'):
            w.import_archive(raw, check, KEY, observed_ms=START+DAY)
    with warehouse(tmp_path).writer() as recovered:
        result = recovered.import_archive(raw, check, KEY, observed_ms=START+2*DAY)
        assert result['inserted_rows'] == 0
        assert recovered.report()['one_minute_rows'] == 1440


def test_weekly_monday_membership_and_all_intervals(tmp_path):
    w = warehouse(tmp_path)
    with w.writer():
        for d in range(7):
            start = START+d*DAY
            key = KEY.replace('2024-01-01', f'2024-01-{d+1:02d}')
            raw, check = fixture(start, key)
            w.import_archive(raw, check, key, observed_ms=START+8*DAY)
    report = w.report()
    assert report['available_complete_projections'] == {
        '1m':10080, '5m':2016, '15m':672, '30m':336, '1h':168, '1d':7, '1w':1}
    weekly = w.query('1w', START, START+7*DAY, cutoff_ms=START+8*DAY)[0]
    assert weekly['constituent_count'] == 10080 and weekly['v'] == '30240'
    with pytest.raises(ValueError, match='QUERY_BOUND'):
        w.query('1w', START+DAY, START+8*DAY, cutoff_ms=START+8*DAY)


def test_retained_daily_import_no_source_calls(tmp_path):
    from aql.warehouse.daily import import_retained
    source = tmp_path/'task-output'
    source.mkdir()
    raw, check = fixture()
    name = KEY.rsplit('/', 1)[1]
    (source/name).write_bytes(raw)
    (source/(name+'.CHECKSUM')).write_bytes(check)
    w = warehouse(tmp_path/'warehouse')
    report = import_retained(w, source, observed_ms=START+DAY)
    assert report['source_network_calls'] == report['scheduler_changes'] == 0
    assert report['one_minute_rows'] == 1440
    replay = import_retained(w, source, observed_ms=START+2*DAY)
    assert replay['this_run'][0]['inserted_rows'] == 0


@pytest.mark.parametrize('missing', [(), (3,)])
def test_source_run_completeness_truth(tmp_path, missing):
    from aql.warehouse.runner import run
    raw, check = fixture(missing=missing)
    class Source:
        authority = AUTH
        def discover(self, now_ms):
            return [dict(key=KEY, size=len(raw), start_ms=START, end_ms=START+DAY)]
        def acquire(self, w, key, expected_size):
            return w.write_once(f'raw/{seal(raw)}.zip', raw), check
    report = run(warehouse(tmp_path), Source(), now_ms=START+DAY, archive_limit=1)
    assert report['full_history_verified'] == (not missing)
    if not missing:
        assert run(warehouse(tmp_path), Source(), now_ms=START+DAY)['this_run'] == []


@pytest.mark.parametrize('status,content_range', [(206,'bytes 99-200/201'), (302,''), (200,'')])
def test_bad_download_response_is_rejected(tmp_path, status, content_range):
    raw, check = fixture()
    def opener(req, timeout):
        if req.full_url.endswith('.CHECKSUM'):
            return Response(check)
        return Response(raw, status, {'Content-Range':content_range, 'Content-Length':'0'})
    with warehouse(tmp_path).writer() as w:
        with pytest.raises(ValueError, match='RANGE|STATUS|LENGTH'):
            VisionHTTP(authority=AUTH, opener=opener).acquire(w, KEY)


def test_corrupt_download_quarantined(tmp_path):
    raw, check = fixture()
    bad = raw[:-1] + bytes([raw[-1]^1])
    def opener(req, timeout):
        return Response(check if req.full_url.endswith('.CHECKSUM') else bad)
    with warehouse(tmp_path).writer() as w:
        with pytest.raises(ValueError, match='CHECKSUM_MISMATCH'):
            VisionHTTP(authority=AUTH, opener=opener).acquire(w, KEY)
        assert len(list((tmp_path/'quarantine').glob('*.zip'))) == 1
        assert not (tmp_path/f'raw/{seal(raw)}.zip').exists()


def test_listing_pagination_and_complete_periods():
    pages = [b'''<ListBucketResult><IsTruncated>true</IsTruncated><NextContinuationToken>x</NextContinuationToken>
      <Contents><Key>data/spot/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01.zip</Key><Size>100</Size></Contents></ListBucketResult>''',
      b'<ListBucketResult><IsTruncated>false</IsTruncated></ListBucketResult>',
      (f'<ListBucketResult><IsTruncated>false</IsTruncated><Contents><Key>{KEY}</Key><Size>100</Size></Contents>'
       '<Contents><Key>data/spot/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01-02.zip</Key><Size>100</Size></Contents></ListBucketResult>').encode()]
    urls = []
    def opener(req, timeout):
        urls.append(req.full_url)
        return Response(pages.pop(0))
    result = VisionHTTP(authority=AUTH, opener=opener).discover(now_ms=START+DAY)
    assert len(result) == 1 and result[0]['key'] == KEY
    assert 'continuation-token=x' in urls[1]


def test_runtime_reserve_and_reparse_attribute(tmp_path, monkeypatch):
    import aql.warehouse.storage as storage
    with warehouse(tmp_path).writer() as w:
        monkeypatch.setattr(storage.shutil, 'disk_usage', lambda path: type('Usage', (), {'free':0})())
        with pytest.raises(ValueError, match='FREE_RESERVE'):
            w.write_once('raw/not-written', b'x')
    class S:
        st_mode = 0o040755
        st_file_attributes = 0x400
    monkeypatch.setattr(storage.Path, 'lstat', lambda self: S())
    with pytest.raises(ValueError, match='REPARSE'):
        storage.safe(tmp_path)


def test_kernel_lock_released_on_process_death_and_ws_untouched(tmp_path):
    import os
    import subprocess
    import sys
    root = tmp_path/'warehouse'
    ws = tmp_path/'existing-ws'
    ws.mkdir()
    (ws/'receipt.json').write_text('{"existing":"unchanged"}')
    before = (ws/'receipt.json').read_bytes()
    code = '''import os,sys
from aql.warehouse.engine import HistoricalWarehouse
with HistoricalWarehouse(sys.argv[1],reserve=0,test_root=True).writer():
    os._exit(17)
'''
    result = subprocess.run([sys.executable, '-c', code, str(root)])
    assert result.returncode == 17
    with warehouse(root).writer() as w:
        w.write_once('receipts/recovered.json', b'{}')
    assert (ws/'receipt.json').read_bytes() == before
    # Capture modules are not dependencies of the warehouse acquisition/import.
    import ast
    modules = Path(__file__).resolve().parents[1]/'src/aql/warehouse'
    for path in modules.glob('*.py'):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert not any(x in (node.module or '') for x in ('collector', 'research_ws', 'scheduler'))
