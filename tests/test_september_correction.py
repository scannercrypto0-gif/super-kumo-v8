"""Generated-only policy fixtures. Never downloads publisher data during CI."""
import copy
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZIP_STORED

import pytest

from aql.warehouse import september_correction as sc
from aql.warehouse.engine import parse_archive
from aql.warehouse.storage import seal
from tests.test_warehouse import fixture, warehouse


def pack(csv):
    out = BytesIO()
    with ZipFile(out,'w',compression=ZIP_STORED) as z:
        z.writestr(sc.NAME[:-4]+'.csv',csv)
    raw=out.getvalue()
    return raw,(seal(raw)+'  '+sc.NAME).encode()


@pytest.fixture(scope='module')
def generated_source():
    records=[]
    for opened in range(sc.START,sc.END,60000):
        if sc.GAP[0] <= opened < sc.GAP[1]:
            continue
        closed=opened+59999
        if opened == 1504713540000:
            closed=1504713600000
        records.append(f'{opened},1,2,1,1,3,{closed},4,1,2,3,0\n')
    csv=''.join(records).encode()
    raw,checksum=pack(csv)
    return raw,checksum,csv


@pytest.fixture
def policy(monkeypatch,generated_source):
    raw,checksum,csv=generated_source
    # TEST_ONLY substitution: production constants remain exact publisher pins.
    monkeypatch.setattr(sc,'SEPT_PIN',seal(raw))
    monkeypatch.setattr(sc,'CHECKSUM_PIN',seal(checksum))
    monkeypatch.setattr(sc,'CSV_PIN',seal(csv))
    return raw,checksum,csv


def test_exact_transform_preserves_every_other_native_field_and_byte(policy):
    raw,checksum,csv=policy
    derived,local_check,lineage=sc.derive(raw,checksum)
    with ZipFile(BytesIO(derived)) as z:
        changed=z.read(z.namelist()[0])
    before,after=csv.splitlines(keepends=True),changed.splitlines(keepends=True)
    assert before[:8159] == after[:8159] and before[8160:] == after[8160:]
    a,b=before[8159].split(b','),after[8159].split(b',')
    assert a[:6] == b[:6] and a[7:] == b[7:]
    assert (a[6],b[6]) == (b'1504713600000',b'1504713599999')
    assert sc.derive(raw,checksum) == (derived,local_check,lineage)
    assert lineage['version'] == 1 and lineage['authorizing_decision'] == sc.DECISION
    assert lineage['missing_minutes'] == 420 and not lineage['full_history_verified']
    assert lineage['derived_csv_sha256'] == seal(changed)
    with pytest.raises(ValueError,match='NATIVE_TIME_OR_MARKET_FIELDS'):
        parse_archive(raw,checksum,sc.SEPT_KEY,sc.END)
    rows,_=parse_archive(derived,local_check,sc.SEPT_KEY,sc.END)
    assert len(rows) == 42780


@pytest.mark.parametrize('field', ['original_zip','original_checksum','original_csv'])
def test_each_original_pin_is_mandatory(policy,monkeypatch,field):
    raw,checksum,_=policy
    if field == 'original_zip':raw+=b'x'
    elif field == 'original_checksum':checksum+=b'\n'
    else:monkeypatch.setattr(sc,'CSV_PIN','0'*64)
    with pytest.raises(ValueError,match='PIN_MISMATCH'):
        sc.derive(raw,checksum)


@pytest.mark.parametrize('kind',['target_field','target_open','extra_price_anomaly','row_census'])
def test_policy_never_corrects_extra_anomalies(policy,monkeypatch,kind):
    _,_,csv=policy
    records=csv.splitlines(keepends=True)
    if kind == 'row_census':records.pop()
    else:
        idx=8159 if kind != 'extra_price_anomaly' else 100
        row=records[idx].split(b',')
        if kind == 'target_field':row[6]=b'1504713600001'
        elif kind == 'target_open':row[0]=b'1504713480000'
        else:row[1]=b'-1'
        records[idx]=b','.join(row)
    csv=b''.join(records)
    raw,checksum=pack(csv)
    monkeypatch.setattr(sc,'SEPT_PIN',seal(raw));monkeypatch.setattr(sc,'CHECKSUM_PIN',seal(checksum))
    monkeypatch.setattr(sc,'CSV_PIN',seal(csv))
    with pytest.raises(ValueError):sc.derive(raw,checksum)


@pytest.mark.parametrize('kind',['lineage','derived_bytes','checksum','wrong_source'])
def test_unapproved_derivation_or_artifact_rejected_before_store_mutation(policy,tmp_path,kind):
    original,check,_=policy
    derived,local,lineage=sc.derive(original,check)
    w=warehouse(tmp_path)
    with w.writer():
        w.write_once(f'raw/{sc.SEPT_PIN}.zip',original)
        w.write_once(f'raw/{sc.CHECKSUM_PIN}.CHECKSUM',check)
        key=sc.SEPT_KEY
        if kind=='lineage':lineage={**lineage,'authorizing_decision':'UNAPPROVED'}
        elif kind=='derived_bytes':derived+=b'x'
        elif kind=='checksum':local+=b'\n'
        else:key=key.replace('2017-09.zip','2017-10.zip')
        with pytest.raises(ValueError):sc.verify_derivative(w,derived,local,key,lineage)
        assert not list((tmp_path/'bars').glob('*.sqlite'))


def initialize(w,policy,monkeypatch):
    original,check,_=policy
    key=sc.SEPT_KEY.replace('2017-09.zip','2017-08.zip')
    august,augcheck=fixture(1502942400000,key,count=21360)
    with w.writer():
        w.import_archive(august,augcheck,key,observed_ms=sc.END)
        w.write_once(f'raw/{sc.SEPT_PIN}.zip',original)
        w.write_once(f'raw/{sc.CHECKSUM_PIN}.CHECKSUM',check)
    monkeypatch.setattr(sc,'AUGUST_PIN',seal(august))
    monkeypatch.setattr(sc,'AUGUST_SHARDS',sc._august_snapshot(w)['shard_sha256'])


def test_apply_replay_restart_and_retained_runner_preserve_august_and_gap(policy,tmp_path,monkeypatch):
    w=warehouse(tmp_path)
    initialize(w,policy,monkeypatch)
    before={p.name:p.read_bytes() for p in (tmp_path/'bars').glob('*.sqlite')}
    result=sc.apply_correction(w,observed_ms=sc.END)
    assert result['september_rows'] == 42780 and result['missing_minutes'] == 420
    assert result['august_unchanged'] and result['original_bytes_unchanged']
    assert result['warehouse']['one_minute_rows'] == 64140
    registry = result['warehouse']['registry']
    assert registry['physical_rows'] == 64140 and registry['internal_gaps'] == [sc.GAP]
    correction = [s for s in registry['sources'] if s['derivation'] is not None]
    assert len(correction) == 1 and correction[0]['derivation'] == result['lineage']
    from aql.warehouse.registry import history
    corrected_events = [e for e in history(w) if e['event_type'] == 'APPROVED_DERIVED_CORRECTION']
    assert len(corrected_events) == 1 and corrected_events[0]['policy_ref'] == sc.POLICY
    assert result['september_gaps'] == result['warehouse']['internal_gaps'] == [sc.GAP]
    assert result['full_history_verified'] is False
    for name,raw in before.items():assert (tmp_path/'bars'/name).read_bytes() == raw
    replay=sc.apply_correction(warehouse(tmp_path),observed_ms=sc.END+86400000)
    assert replay['import_result']['inserted_rows'] == 0
    assert replay['import_result']['duplicate_rows'] == 42780
    from aql.warehouse.runner import run
    class Source:
        authority={}
        def discover(self,now_ms):
            return [dict(key=sc.SEPT_KEY,start_ms=sc.START,end_ms=sc.END,size=100)]
        def acquire(self,*a,**k):raise AssertionError('RETAINED_DERIVATIVE_MUST_NOT_REDOWLOAD_ORIGINAL')
    retained=run(w,Source(),now_ms=sc.END)
    assert not retained['full_history_verified'] and retained['internal_gaps'] == [sc.GAP]
    import json
    catalog=json.loads((tmp_path/f"catalog/{result['lineage']['derived_zip_sha256']}.json").read_bytes())
    assert catalog['source_kind'] == 'OWNER_AUTHORIZED_DERIVATIVE'
    assert catalog['publisher_integrity'] == 'ORIGINAL_PINNED_DERIVATIVE_LOCAL_CHECKSUM'


def test_crash_after_some_september_shards_recovers_without_touching_august(policy,tmp_path,monkeypatch):
    w=warehouse(tmp_path);initialize(w,policy,monkeypatch)
    replace=sc.os.replace
    def crash(source,target):
        if Path(target).name == '2017-09-03.sqlite':raise OSError('TEST_ONLY_POWER_INTERRUPTION')
        return replace(source,target)
    monkeypatch.setattr(sc.os,'replace',crash)
    with pytest.raises(OSError,match='POWER_INTERRUPTION'):
        sc.apply_correction(w,observed_ms=sc.END)
    monkeypatch.setattr(sc.os,'replace',replace)
    result=sc.apply_correction(warehouse(tmp_path),observed_ms=sc.END+86400000)
    assert result['september_rows'] == 42780 and result['august_unchanged']
    assert result['september_gaps'] == [sc.GAP]


def test_prior_owner_august_hash_mismatch_stops_before_derivative_writes(policy,tmp_path,monkeypatch):
    w=warehouse(tmp_path);initialize(w,policy,monkeypatch)
    monkeypatch.setattr(sc,'AUGUST_SHARDS',{})
    before={str(p.relative_to(tmp_path)):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    with pytest.raises(ValueError,match='AUGUST_BASELINE_MISMATCH'):
        sc.apply_correction(w,observed_ms=sc.END)
    after={str(p.relative_to(tmp_path)):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    assert before == after


def test_derivative_budget_failure_never_imports_september(policy,tmp_path,monkeypatch):
    w=warehouse(tmp_path);initialize(w,policy,monkeypatch)
    before=sc._august_snapshot(w)
    original_budget=w.budget
    def bounded(size):
        if size > 1000000:raise ValueError('WAREHOUSE_BUDGET_EXCEEDED')
        return original_budget(size)
    monkeypatch.setattr(w,'budget',bounded)
    with pytest.raises(ValueError,match='BUDGET_EXCEEDED'):
        sc.apply_correction(w,observed_ms=sc.END)
    assert sc._august_snapshot(w) == before
    assert not list((tmp_path/'bars').glob('2017-09-*.sqlite'))


def test_existing_bar_inside_authorized_missing_gap_is_never_hidden(policy,tmp_path,monkeypatch):
    w=warehouse(tmp_path);initialize(w,policy,monkeypatch)
    from aql.research_bar_store import ResearchBarStore
    path=tmp_path/'bars/2017-09-06.sqlite'
    with ResearchBarStore(path) as store:
        store.insert_1m(dict(symbol='BTCUSDT',interval='1m',open_ms=sc.GAP[0],final=True,
                            o='1',h='2',l='1',c='1',v='0',source_sha256='9'*64,
                            available_at_ms=sc.END),source_class='RETROSPECTIVE_NON_PIT')
    before={p.name:p.read_bytes() for p in (tmp_path/'bars').glob('*.sqlite')}
    with pytest.raises(ValueError,match='UNEXPECTED_EXISTING_SEPTEMBER_BAR'):
        sc.apply_correction(w,observed_ms=sc.END)
    assert before == {p.name:p.read_bytes() for p in (tmp_path/'bars').glob('*.sqlite')}
