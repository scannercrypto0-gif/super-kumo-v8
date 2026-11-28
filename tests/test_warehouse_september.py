"""Small generated native fixtures; no source acquisition during CI."""
from io import BytesIO
import json
from zipfile import ZipFile, ZIP_DEFLATED

import pytest

from aql.warehouse import diagnose as diagnostic
from aql.warehouse.engine import parse_archive
from aql.warehouse.storage import seal
from tests.test_warehouse import fixture, warehouse

START = 1504713540000
END = 1506816000000
KEY = diagnostic.SEPT_KEY
# Public native values localizing the observed error; generated fixture ZIP.
ROW = ['1504713540000','4603.74000000','4619.43000000','4603.74000000',
       '4619.43000000','0.27733300','1504713599999','1277.13769335',
       '2','0.02349700','108.54274671','11146.71897399']


def native(row, key=KEY):
    out = BytesIO()
    name = key.rsplit('/',1)[1]
    with ZipFile(out,'w',compression=ZIP_DEFLATED) as z:
        z.writestr(name[:-4]+'.csv', ','.join(row)+'\n')
    raw = out.getvalue()
    return raw, (seal(raw)+'  '+name).encode()


def test_monthly_september_exclusive_close_is_rejected_and_localized():
    row = list(ROW)
    row[6] = '1504713600000'
    raw, checksum = native(row)
    with pytest.raises(ValueError, match='NATIVE_TIME_OR_MARKET_FIELDS'):
        parse_archive(raw,checksum,KEY,END)
    result = diagnostic.diagnose_archive(raw,checksum,KEY,observed_ms=END)
    assert result['rows_imported'] == 0 and result['failed_rows'] == 1
    assert result['first_failure'] == dict(native_csv_line=1,open_time=row[0],predicates=[
        dict(field=6,value=row[6],expected='1504713599999',delta_native_units=1,
             predicate='close_time_equals_open_plus_minute_minus_one')])


def test_daily_alternative_zero_duration_placeholder_still_rejected():
    row = list(ROW)
    row[0] = row[6] = '1504713600000'
    row[1:5] = ['4619.43000000']*4
    row[5] = row[7] = row[8] = row[9] = row[10] = row[11] = '0'
    key = KEY.replace('/monthly/','/daily/').replace('2017-09.zip','2017-09-06.zip')
    raw, checksum = native(row,key)
    result = diagnostic.diagnose_archive(raw,checksum,key,observed_ms=END)
    assert result['status'] == 'STRICT_NATIVE_SOURCE_REJECTED'
    assert result['first_failure']['predicates'][0]['expected'] == '1504713659999'


@pytest.mark.parametrize('field,value', [
    (0,'1504713540001'),(0,'1504137540000'),(6,'1504713540000'),
    (1,'-1'),(1,'NaN'),(2,'4000'),(3,'4700'),(4,'NaN'),
    (5,'-1'),(5,'Infinity'),(8,'-1'),(8,'1.5'),
    (7,'-1'),(9,'NaN'),(10,'Infinity'),(11,'-1'),
])
def test_existing_validator_negative_controls_remain_fail_closed(field,value):
    row = list(ROW)
    row[field] = value
    raw, checksum = native(row)
    with pytest.raises(ValueError):
        parse_archive(raw,checksum,KEY,END)


def test_unchanged_validator_accepts_valid_native_endpoint():
    raw, checksum = native(ROW)
    rows, _ = parse_archive(raw,checksum,KEY,END)
    assert len(rows) == 1 and rows[0]['close_exclusive_ms'] == 1504713600000


def test_bad_checksum_never_localized_as_verified_native_evidence():
    raw, checksum = native(ROW)
    result = diagnostic.diagnose_archive(raw+b'x',checksum,KEY,observed_ms=END)
    assert result['validator_error'] == 'PUBLISHER_CHECKSUM_MISMATCH'
    assert 'first_failure' not in result


def test_recovery_quarantines_reference_and_preserves_21360_august_rows(tmp_path,monkeypatch):
    w = warehouse(tmp_path)
    august_key = KEY.replace('2017-09.zip','2017-08.zip')
    august, august_check = fixture(1502942400000,august_key,count=21360)
    bad = list(ROW); bad[6] = '1504713600000'
    september, check = native(bad)
    with w.writer():
        w.import_archive(august,august_check,august_key,observed_ms=END)
        w.write_once(f'raw/{seal(september)}.zip',september)
        w.write_once(f'raw/{seal(check)}.CHECKSUM',check)
    monkeypatch.setattr(diagnostic,'AUGUST_PIN',seal(august))
    before = {p.name:p.read_bytes() for p in (tmp_path/'bars').glob('*.sqlite')}
    result = diagnostic.resume_or_block(w,observed_ms=END,expected_source_pin=seal(september))
    after = {p.name:p.read_bytes() for p in (tmp_path/'bars').glob('*.sqlite')}
    assert result['status'] == 'BLOCKED_INVALID_PUBLISHER_SOURCE'
    assert result['august']['rows'] == result['warehouse']['one_minute_rows'] == 21360
    assert result['august_unchanged'] and before == after and not result['resume_attempted']
    assert (tmp_path/f'raw/{seal(september)}.zip').read_bytes() == september
    assert list((tmp_path/'quarantine').glob('*.json'))
    assert not list((tmp_path/'bars').glob('2017-09-*.sqlite'))


def test_recovery_never_provisions_a_new_warehouse(tmp_path):
    root = tmp_path/'absent'
    with pytest.raises(ValueError,match='NO_REBUILD'):
        diagnostic.resume_or_block(warehouse(root),observed_ms=END)
    assert not root.exists()
