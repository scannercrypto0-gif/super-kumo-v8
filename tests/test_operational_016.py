import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import atlas_operational_016 as op


def config(tmp_path):
    inp=tmp_path/'reports';out=tmp_path/'monitor';inp.mkdir();out.mkdir()
    return dict(schema='atlas.operational016.config.v1',protected_roots=[str(tmp_path/'data')],input_root=str(inp),output_root=str(out),activation_ref='GENERATED_TEST_ONLY',
        retention_authorization_ref='GENERATED_TEST_ONLY',clock_uncertainty_ms=100)


def test_exit_two_does_not_identify_a_crash():
    receipt=dict(schema='aql.warehouse.full-history-continuation.v1',failures=[],
        unresolved_gap_ranges=[],all_published_partitions_ingested=False,accepted_prefix_unchanged=True)
    result=op.classify_history(receipt,2)
    assert result['reason']=='BOUNDED_PROGRESS_OR_UNFINISHED_PLAN_NOT_A_CRASH_PROOF'
    assert result['exit_consistent'] and not result['recovery_accepted']
    receipt['unresolved_gap_ranges']=[[0,60000]]
    assert op.classify_history(receipt,2)['reason']=='UNRESOLVED_COVERAGE_GAPS'
    receipt['failures']=[{'reason':'EXACT_SOURCE_FAILURE'}]
    assert 'FAILURE_REQUIRES_EXACT' in op.classify_history(receipt,2)['reason']
    assert op.classify_history({},2)['reason']=='INSUFFICIENT_TERMINAL_EVIDENCE'


def test_actual_stdio_and_restart_sequence(tmp_path):
    c=config(tmp_path);now=[op.time.time_ns()//1000000]
    def wait(seconds):now[0]+=seconds*1000
    first=op.monitor(c,cycles=2,now=lambda:now[0],wait=wait)
    assert [r['sequence'] for r in first]==[0,1]
    assert first[0]['mcp_readback']['tools']==2 and first[0]['mcp_readback']['resources']==4
    assert first[0]['mcp_readback']['writes_refused']
    assert first[0]['state']=='UNKNOWN'  # empty inputs never become healthy
    again=op.monitor(c,cycles=1,now=lambda:now[0]+300000,wait=wait)
    assert again[0]['sequence']==2


def test_retention_owned_pairs_only_and_restart(tmp_path):
    c=config(tmp_path);now=[op.time.time_ns()//1000000]
    result=op.monitor(c,cycles=10,now=lambda:now[0],wait=lambda s:now.__setitem__(0,now[0]+s*1000))
    assert all(r['status']=='REFRESH_PUBLISHED_REPORT_ONLY' for r in result)
    out=Path(c['output_root'])
    assert len(list(out.glob('early-*.manifest.json')))==8
    assert len(list(out.glob('early-*.json')))==16
    state,_=op.wd.read_json(out/'monitor-state.json')
    assert not state['prune_pending']


def test_unknown_files_and_unauthorized_host_activation_refused(tmp_path):
    c=config(tmp_path);c['activation_ref']=''
    with pytest.raises(ValueError,match='PERMISSION_REQUIRED'):op.monitor(c,cycles=1)
    c['activation_ref']='TEST';(Path(c['output_root'])/'existing-data').write_text('preserve')
    with pytest.raises(ValueError,match='UNOWNED_OUTPUT'):op.monitor(c,cycles=1)
    assert (Path(c['output_root'])/'existing-data').read_text()=='preserve'


def test_transient_refresh_failure_recovers_without_freshening_old_snapshot(tmp_path,monkeypatch):
    c=config(tmp_path);now=[op.time.time_ns()//1000000];original=op.refresh.refresh_once;attempt=[0]
    def flaky(*a,**kw):
        attempt[0]+=1
        if attempt[0]==1:raise OSError('INJECTED')
        return original(*a,**kw)
    monkeypatch.setattr(op.refresh,'refresh_once',flaky)
    results=op.monitor(c,cycles=2,now=lambda:now[0],wait=lambda s:now.__setitem__(0,now[0]+s*1000))
    assert results[0]['status']=='MONITOR_BLOCKED' and results[1]['state']=='UNKNOWN'
    assert len(list(Path(c['output_root']).glob('*.manifest.json')))==1


def test_repeated_restart_and_interrupted_manifest_publication(tmp_path,monkeypatch):
    c=config(tmp_path);now=[op.time.time_ns()//1000000];original=op.refresh.atomic_new;once=[True]
    def fail_manifest(path,value):
        if '.manifest.' in str(path) and once[0]:
            once[0]=False;raise OSError('INJECTED_AFTER_SNAPSHOT')
        return original(path,value)
    monkeypatch.setattr(op.refresh,'atomic_new',fail_manifest)
    result=op.monitor(c,cycles=1,now=lambda:now[0])
    assert result[0]['status']=='MONITOR_BLOCKED'
    for expected in [1,2,3]:
        now[0]+=300000
        result=op.monitor(c,cycles=1,now=lambda:now[0])
        assert result[0]['sequence']==expected
        assert result[0]['status']=='REFRESH_PUBLISHED_REPORT_ONLY'
    state,_=op.wd.read_json(Path(c['output_root'])/'monitor-state.json')
    assert len(state['orphans'])==1 and not state['pending_publish']


def test_protected_data_root_not_usable_as_report_root(tmp_path):
    c=config(tmp_path);c['protected_roots']=[c['input_root']]
    with pytest.raises(ValueError,match='PROTECTED_ROOT_OVERLAP'):op.monitor(c,cycles=1)


def test_inspection_does_not_create_roots_and_fatal_reason_is_sanitized(tmp_path):
    cfg=tmp_path/'config.json';cfg.write_text(json.dumps(dict(input_root=str(tmp_path/'missing-in'),output_root=str(tmp_path/'missing-out'))))
    result=op.inspect_config(cfg)
    assert result['activation']=='NOT_PERFORMED' and result['input_root']=='MISSING_OR_UNAPPROVED_ROOT'
    assert not (tmp_path/'missing-in').exists()
    result=op.classify_history({'status':'FULL_HISTORY_STOPPED_FAIL_CLOSED','error_type':'OSError','reason':'C:/private/secret'},2)
    assert result['reported_reason_code']=='PRIVATE_DETAIL_RETAINED_LOCALLY'
    assert 'private' not in json.dumps(result)


def test_exclusive_lock_and_output_quota_are_enforced(tmp_path):
    c=config(tmp_path);out=Path(c['output_root'])
    with op.exclusive(out):
        with pytest.raises(OSError):op.monitor(c,cycles=1)
    candidate=out/'early-000000000000.json';candidate.write_bytes(b'x'*(op.QUOTA+1))
    with pytest.raises(ValueError,match='DISK_QUOTA'):op.monitor(c,cycles=1)
    assert candidate.stat().st_size==op.QUOTA+1
