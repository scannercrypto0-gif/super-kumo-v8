"""Generated data through actual pinned native APIs, never original host evidence."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from tools.realtime_market_feed.test_forward_research import (
    ROOT, WAREHOUSE, BASELINE, DEPENDENCIES, REST_CODE_SHA256, _feed, _config,
)
from tools.realtime_market_feed.service import PRODUCER_CODE_SHA256

CALL = r'''
import json,sys,os
from pathlib import Path
root=Path(os.environ['AQL_WORKTREE']);sys.path[:0]=[str(root),str(root/'.integration/warehouse/src')]
from tools.realtime_market_feed import native_consumers as n
from tools.realtime_market_feed import forward_research as fr
args=json.loads(Path(sys.argv[1]).read_text())
mode=args.pop('mode',None)
try:
 if mode is None or mode in ('deny_original','crash_after_factory'):
  if mode=='crash_after_factory':
   original=n._apis
   def injected(*a,**kw):
    apis=original(*a,**kw)
    def fail(*a,**kw):raise RuntimeError('INJECTED_AFTER_DURABLE_FACTORY_COMMIT')
    apis[-1].route_forward_wait=fail
    return apis
   n._apis=injected
  value=n.run_generated_native_chain(args.pop('feed_database'),args.pop('research_database'),**args)
 else:
  prior=json.loads(Path(args.pop('prior')).read_text())
  receipt=prior['receipt'];expected=receipt['receipt_sha256'];snapshot=receipt['source']['source_snapshot_sha256']
  if mode=='tamper':receipt['decision']['state']='NO_SIGNAL'
  if mode=='reorder':receipt['decision']['state_by_slot'].reverse()
  if mode=='wrong_source':receipt['source']['source_class']='RETROSPECTIVE_NON_PIT'
  if mode=='future':receipt['source']['availability_max_ms']=receipt['decision']['decision_cutoff_ms']+1
  if mode in ('reorder','wrong_source','future'):
   receipt['receipt_sha256']=fr._sha({k:v for k,v in receipt.items() if k!='receipt_sha256'});expected=receipt['receipt_sha256']
  value=n.consume_generated_forward_receipt(receipt,generated_feed_database=args['feed_database'],output_root=args['output_root'],baseline_root=args['baseline_root'],dependency_root=args['dependency_root'],expected_receipt_sha256=expected,expected_source_snapshot_sha256=snapshot,expected_adapter_code_sha256=args['config']['adapter_code_sha256'],expected_strategy_definition_sha256=args['config']['strategy_definition_sha256'],expected_config_sha256=args['expected_config_sha256'])
 print(json.dumps({'ok':True,'result':value},sort_keys=True))
except Exception as e:
 print(json.dumps({'ok':False,'error':str(e)},sort_keys=True));sys.exit(3)
'''


def args_for(tmp_path):
    source = tmp_path / 'feed.sqlite'
    start, end = _feed(source)
    config, pin = _config(start, 12)
    return dict(feed_database=str(source), research_database=str(tmp_path / 'projected.sqlite'),
        output_root=str(tmp_path / 'native'), symbol='BTCUSDT', start_ms=start, bar_count=12,
        decision_cutoff_ms=end+1000, clock_evidence={
            'schema':'atlas.realtime-market-feed.validated-clock.v1',
            'method':'WALL_MONOTONIC_BRACKET_V1','observed_at_ms':end+1000,'uncertainty_ms':0},
        config=config,expected_config_sha256=pin,
        expected_ws_producer_code_sha256=PRODUCER_CODE_SHA256,
        expected_rest_producer_code_sha256=REST_CODE_SHA256,
        baseline_root=str(BASELINE), dependency_root=str(DEPENDENCIES),
        warehouse_root=str(WAREHOUSE),allow_synthetic_fixture=True)


def call(tmp_path, args):
    path=tmp_path/'arguments.json';path.write_text(json.dumps(args))
    env={**os.environ,'AQL_WORKTREE':str(ROOT)}
    result=subprocess.run([sys.executable,'-B','-c',CALL,str(path)],cwd=ROOT,env=env,capture_output=True,text=True,timeout=60)
    assert result.stdout.strip(), result.stderr
    value=json.loads(result.stdout.strip().splitlines()[-1])
    if result.returncode not in (0,3):raise AssertionError(result.stderr)
    return value


def test_native_source_scanner_factory_lab_secretary_replay(tmp_path):
    args=args_for(tmp_path)
    before=hashlib.sha256(Path(args['feed_database']).read_bytes()).hexdigest()
    first=call(tmp_path,args);assert first['ok'],first
    second=call(tmp_path,args);assert second['ok'],second
    a=first['result']['native_consumers'];b=second['result']['native_consumers']
    assert a['factory_store_status']=='STORED_IMMUTABLE'
    assert b['factory_store_status']=='REPLAY_IDENTICAL'
    assert a['factory_package_sha256']==b['factory_package_sha256']
    assert a['lab_sha256']==b['lab_sha256'] and a['secretary']==b['secretary']
    assert a['census']['expected_bars']==a['census']['decision_slots']==12
    assert a['census']['signal_unknown']==7 and a['census']['modeled_trades']==0
    assert a['secretary']['state']=='WAIT_AUTHENTICATED_PARENTS_AND_RESEARCH_REVIEW'
    assert all(a['secretary'][key] is None for key in ('core_245_sha256','core_253_sha256','source_ack_sha256','strategy_approval_sha256','factory_consumer_ack_sha256'))
    assert hashlib.sha256(Path(args['feed_database']).read_bytes()).hexdigest()==before
    with sqlite3.connect(Path(args['output_root'])/'factory.sqlite') as con:
        package=json.loads(con.execute('SELECT document FROM factory_h_research_results_v1').fetchone()[0])
    assert package['source_class']=='FORWARD_UNQUALIFIED'
    assert package['scientific_lab']['metrics']['net_compounded_return'] is None
    assert package['scientific_lab']['metrics']['unknown_outcomes']>0
    assert package['scientific_lab']['assessment']=='DESCRIPTIVE_RESEARCH_ONLY_NO_ALPHA_CLAIM'
    with sqlite3.connect(Path(args['output_root'])/'secretary/warehouse.sqlite') as con:
        assert con.execute('SELECT COUNT(*) FROM forward_research_wait_v1').fetchone()[0]==1
        assert con.execute('SELECT COUNT(*) FROM price_bars').fetchone()[0]==0
        assert con.execute('SELECT COUNT(*) FROM distribution_outbox').fetchone()[0]==0


@pytest.mark.parametrize('mode,reason',[('tamper','FACTORY_FORWARD_RECEIPT_SEAL_INVALID'),('reorder','NATIVE_CENSUS_ORDER_OR_DENOMINATOR'),('wrong_source','FACTORY_FORWARD_RECEIPT_PIN_MISMATCH'),('future','FACTORY_FORWARD_DECISION_CAUSALITY_INVALID')])
def test_native_denies_mutation_order_source_and_future(tmp_path,mode,reason):
    args=args_for(tmp_path);first=call(tmp_path,args);assert first['ok'],first
    prior=tmp_path/'prior.json';prior.write_text(json.dumps(first['result']))
    value=call(tmp_path,{**args,'prior':str(prior),'mode':mode})
    assert not value['ok'] and value['error']==reason,value


def test_original_scope_and_secretary_corruption_are_not_silent(tmp_path):
    args=args_for(tmp_path)
    denied=call(tmp_path,{**args,'mode':'deny_original','allow_synthetic_fixture':False})
    assert not denied['ok'] and denied['error']=='NATIVE_ORIGINAL_RUN_AUTHORIZATION_NOT_IMPLEMENTED'
    assert not Path(args['output_root']).exists()
    accepted=call(tmp_path,args);assert accepted['ok'],accepted
    db=Path(args['output_root'])/'secretary/warehouse.sqlite'
    with sqlite3.connect(db) as con:
        con.execute("UPDATE forward_research_wait_v1 SET document='{}'");con.commit()
    replay=call(tmp_path,args)
    assert not replay['ok'] and replay['error']=='FORWARD_SECRETARY_IMMUTABLE_CONFLICT',replay


def test_factory_committed_secretary_interrupted_replays_once(tmp_path):
    args=args_for(tmp_path)
    failed=call(tmp_path,{**args,'mode':'crash_after_factory'})
    assert not failed['ok'] and failed['error']=='INJECTED_AFTER_DURABLE_FACTORY_COMMIT'
    with sqlite3.connect(Path(args['output_root'])/'factory.sqlite') as con:
        assert con.execute('SELECT COUNT(*) FROM factory_h_research_results_v1').fetchone()[0]==1
    resumed=call(tmp_path,args);assert resumed['ok'],resumed
    assert resumed['result']['native_consumers']['factory_store_status']=='REPLAY_IDENTICAL'
    with sqlite3.connect(Path(args['output_root'])/'secretary/warehouse.sqlite') as con:
        assert con.execute('SELECT COUNT(*) FROM forward_research_wait_v1').fetchone()[0]==1


def test_generated_source_marker_required_before_direct_intake(tmp_path):
    args=args_for(tmp_path);first=call(tmp_path,args);assert first['ok'],first
    prior=tmp_path/'prior.json';prior.write_text(json.dumps(first['result']))
    with sqlite3.connect(args['feed_database']) as con:
        con.execute('DELETE FROM engineering_fixture');con.commit()
    before=hashlib.sha256(Path(args['feed_database']).read_bytes()).hexdigest()
    bad=call(tmp_path,{**args,'prior':str(prior),'mode':'marker_missing'})
    assert not bad['ok'] and bad['error']=='SYNTHETIC_FIXTURE_MARKER_INVALID',bad
    assert hashlib.sha256(Path(args['feed_database']).read_bytes()).hexdigest()==before


def test_hardlinked_factory_store_denied_before_mutation(tmp_path):
    args=args_for(tmp_path)
    root=Path(args['output_root']);root.mkdir()
    target=tmp_path/'other.sqlite';target.write_bytes(b'untouched')
    try:os.link(target,root/'factory.sqlite')
    except OSError:pytest.skip('hardlinks unavailable on this filesystem')
    before=target.read_bytes()
    bad=call(tmp_path,args)
    assert not bad['ok'] and bad['error']=='NATIVE_OUTPUT_LINK_DENIED',bad
    assert target.read_bytes()==before


def _secretary_module():
    import importlib.util
    path=ROOT/'src/aql/research_forward_secretary.py'
    spec=importlib.util.spec_from_file_location('_forward_secretary_direct_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def _direct_wait(module):
    body=dict(schema=module.SCHEMA,experiment_id='FORWARD-RESEARCH-'+'a'*64,
        analysis_receipt_sha256='a'*64,source_snapshot_sha256='b'*64,
        factory_package_sha256='c'*64,lab_sha256='d'*64,
        strategy_definition_sha256='e'*64,config_sha256='f'*64,
        decision_cutoff_ms=9000000,expected_slots=8,unknown_slots=7,
        source_class='FORWARD_UNQUALIFIED',evidence_grade='GENERATED_NATIVE_INTERFACE_TEST',
        state='WAIT_AUTHENTICATED_PARENTS_AND_RESEARCH_REVIEW',
        core_245_sha256=None,core_253_sha256=None,source_ack_sha256=None,
        strategy_approval_sha256=None,factory_consumer_ack_sha256=None,
        orders=0,trading_authority='NONE',pit_oos='NOT_ATTESTED')
    return {**body,'sha256':module.digest(body)}


def test_direct_secretary_outside_generated_temp_denied_without_creating_root(tmp_path,monkeypatch):
    module=_secretary_module();allowed=tmp_path/'allowed';allowed.mkdir()
    monkeypatch.setattr(module.tempfile,'gettempdir',lambda:str(allowed))
    forbidden=tmp_path/'not-generated'
    with pytest.raises(ValueError,match='FORWARD_SECRETARY_GENERATED_ROOT_OUTSIDE_TEMP'):
        module.route_forward_wait(forbidden,_direct_wait(module))
    assert not forbidden.exists()


@pytest.mark.parametrize('filename',['warehouse.sqlite','warehouse.sqlite-wal','warehouse.sqlite-shm','warehouse.sqlite-journal'])
def test_direct_secretary_hardlinked_sqlite_or_sidecar_denied(tmp_path,filename):
    module=_secretary_module();root=tmp_path/'secretary-direct';root.mkdir()
    target=tmp_path/'untouched.sqlite';target.write_bytes(b'untouched linked target')
    try:os.link(target,root/filename)
    except OSError:pytest.skip('hardlinks unavailable on this filesystem')
    with pytest.raises(ValueError,match='FORWARD_SECRETARY_LINKED_SQLITE_DENIED'):
        module.route_forward_wait(root,_direct_wait(module))
    assert target.read_bytes()==b'untouched linked target'
    assert {p.name for p in root.iterdir()}=={filename}


def test_direct_secretary_symlink_ancestor_denied(tmp_path):
    module=_secretary_module();target=tmp_path/'real';target.mkdir();alias=tmp_path/'alias'
    try:alias.symlink_to(target,target_is_directory=True)
    except OSError:pytest.skip('symlink creation is unavailable for this Windows account')
    with pytest.raises(ValueError,match='FORWARD_SECRETARY_LINKED_PATH_DENIED'):
        module.route_forward_wait(alias/'secretary',_direct_wait(module))
    assert list(target.iterdir())==[]


@pytest.mark.parametrize('owned',['factory','projected'])
@pytest.mark.parametrize('suffix',['-wal','-shm','-journal'])
def test_linked_owned_database_sidecars_denied_before_mutation(tmp_path,owned,suffix):
    args=args_for(tmp_path)
    root=Path(args['output_root']);root.mkdir()
    database=root/'factory.sqlite' if owned=='factory' else Path(args['research_database'])
    sidecar=Path(str(database)+suffix)
    target=tmp_path/'external-sentinel';target.write_bytes(b'untouched-sidecar')
    try:os.link(target,sidecar)
    except OSError:pytest.skip('hardlinks unavailable on this filesystem')
    source_before=Path(args['feed_database']).read_bytes()
    bad=call(tmp_path,args)
    assert not bad['ok'] and bad['error']=='NATIVE_OUTPUT_LINK_DENIED',bad
    assert target.read_bytes()==b'untouched-sidecar'
    assert sidecar.is_file() and sidecar.read_bytes()==b'untouched-sidecar'
    assert not database.exists()
    assert Path(args['feed_database']).read_bytes()==source_before


def test_direct_consumer_source_output_overlap_denied_before_writes(tmp_path):
    args=args_for(tmp_path);first=call(tmp_path,args);assert first['ok'],first
    prior=tmp_path/'prior.json';prior.write_text(json.dumps(first['result']))
    before=Path(args['feed_database']).read_bytes()
    bad=call(tmp_path,{**args,'prior':str(prior),'mode':'direct_overlap','output_root':str(tmp_path)})
    assert not bad['ok'] and bad['error']=='NATIVE_SOURCE_OUTPUT_COLLISION',bad
    assert Path(args['feed_database']).read_bytes()==before
    assert not (tmp_path/'factory.sqlite').exists()
