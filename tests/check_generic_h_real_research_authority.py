"""Synthetic-only Generic H integration using real Core, Scanner and Factory."""
import copy
import hashlib,json,sqlite3,sys,tempfile
from contextlib import closing
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from research_wp_r0.aql_core_backbone_local_v1 import admit_local_original, query_local
from research_wp_r0.aql_authenticated_historical_admission_v1 import PIN_SCHEMA
from research_wp_r0.aql_factory_e_research_results_store_v1 import digest,migrate_store_v2
from research_wp_r0.aql_factory_h_research_package_v1 import TABLE
from research_wp_r0 import aql_factory_h_generic_signal_adapter_v1 as f
from tools.scanner_strategy_f import research_strategy_plugin as s
from tools.atlas_h_generic_secretary_bridge import deliver_generic_research_wait,GenericBridgeError
START=1709251200000
STEP=900000
N=64


def synthetic_real_sqlite(root,*,partial=False):
    """Actual Core admission, not a mocked query, using native-format test ZIP."""
    basename="BTCUSDT-15m-2024-03"
    rows=[]
    for i in range(N):
        opened=START+i*STEP
        px=101.0+(i%17)*0.03
        rows.append(",".join((
            str(opened),str(px),str(px+0.05),str(px-0.05),str(px),
            str(float(i+1)),str(opened+STEP-1),"505",str(2+i),
            "2","202","0"
        )))
    csv=("\n".join(rows)+"\n").encode()
    stream=BytesIO()
    with ZipFile(stream,"w",compression=ZIP_DEFLATED) as archive:
        archive.writestr(basename+".csv",csv)
    raw=stream.getvalue()
    source=hashlib.sha256(raw).hexdigest()
    checksum=(source+"  "+basename+".zip\n").encode()
    end=START+N*STEP
    pin={
        "schema":PIN_SCHEMA,"source_kind":"BINANCE_KLINES_ZIP",
        "original_object_id":"TEST_LAB3_RAW_ZIP",
        "original_sha256":source,
        "provenance_reference":"SYNTHETIC_TEST_ONLY",
        "captured_at_ms":end+10000,"claimed_available_at_ms":None,
        "expected_inventory_sha256":None,
        "vault_object_metadata":None,"universe_manifest_sha256":None,
        "universe_member_count":None,"test_only":True,
        "archive_name":basename+".zip",
        "csv_member_name":basename+".csv",
        "csv_member_sha256":hashlib.sha256(csv).hexdigest(),
        "checksum_file_sha256":hashlib.sha256(checksum).hexdigest(),
    }
    spec={
        "dataset_id":"TEST-ONLY-H-BTC-15M","version":1,
        "symbol":"BTCUSDT","interval":"15m","exchange":"BINANCE",
        "market":"SPOT","source_label":"native-monthly-zip",
        "start_ms":START,"end_exclusive_ms":end,"as_of_ms":end+5000,
        "parent_source_sha256":None,"correction_reason":None,
        "test_only":True,
    }
    receipt=admit_local_original(
        root,raw,checksum,pin,spec,decision_cutoff_ms=end+2000)
    # The real read explicitly opens Core's derived SQLite in immutable mode.
    # A missing/unavailable bar is a bounded cutoff case, not an
    # invalid ZIP. Core admission correctly rejects structurally sparse ZIP.
    query_cutoff=(START+STEP+2000) if partial else (end+2000)
    query=query_local(root,spec["dataset_id"],1,START,end,query_cutoff,
                      required_source_sha256=source,
                      require_complete=not partial,sqlite_immutable=True)
    assert query["source_bytes_sha256"]==receipt["source_zip_sha256"]
    assert query["query_sha256"]!=receipt["receipt_sha256"]
    assert query["historical_pit"]=="NOT_ATTESTED"
    return query,receipt


def seal(x):
 return {**x,"sha256":digest(x)}
with tempfile.TemporaryDirectory() as d:
 root=Path(d)
 q,_=synthetic_real_sqlite(root/'warehouse')
 raw=json.loads(Path('tools/strategy_service_offline/fixtures/strategies.json').read_text())[0]
 a=raw['payload']
 plugin=s.register_strategy_plugin(a['definition'],config_digest=a['config_digest'],source_spec_receipt=raw)
 policy=s.research_signal_policy(source_class='OWNER_LOCAL_RECOVERY_DIAGNOSTIC')
 batch=s.evaluate_strategy_plugin(plugin,q,warehouse_root=root/'warehouse',policy=policy)
 costs={k:'1' for k in f.COST_KEYS}; costs['funding_bps_per_bar']='0'
 cost=seal(dict(schema=f.COST_SCHEMA,costs=costs,market='SPOT',direction='LONG',scenario_class='SYNTHETIC_TEST_EXPLICIT',owner_operator_authorized=False,fill_semantics='NEXT_ELIGIBLE_OPEN_UNKNOWN_ON_INTRABAR_TOUCH',holdout='SEALED_UNOPENED',trading_authority='NONE'))
 packet=seal(dict(schema=f.SCHEMA,experiment_id='RESEARCH-H-GENERIC-CLEAN-MAIN-SYNTHETIC',strategy_plugin=plugin,scanner_signal_policy=policy,scanner_signal_batch=batch,core_query=q,operator_cost_policy=cost,factory_code_sha256=hashlib.sha256(Path(f.__file__).read_bytes()).hexdigest(),source_query_sha256=q['query_sha256'],source_bytes_sha256=q['source_bytes_sha256'],manifest_integrity_sha256=q['manifest_integrity_sha256'],strategy_definition_sha256=a['definition']['digest'],strategy_plugin_sha256=plugin['sha256'],config_sha256=a['config_digest'],scanner_policy_sha256=policy['sha256'],scanner_evaluator_code_sha256=s._code_sha(),decision_cutoff_ms=q['decision_cutoff_ms'],holdout='SEALED_UNOPENED',historical_pit='NOT_ATTESTED',trading_authority='NONE',source_ack_sha256=None,strategy_approval_sha256=None,factory_consumer_ack_sha256=None))
 db=root/'results.sqlite'
 migrate_store_v2(db)
 res=f.run_factory_h_generic_research(packet,db)
 with closing(sqlite3.connect(db.as_uri()+'?mode=ro&immutable=1',uri=True)) as con:
  package=json.loads(con.execute(f'SELECT document FROM {TABLE}').fetchone()[0])
 scope={k:q[k] for k in ('dataset_id','version','source_bytes_sha256','manifest_integrity_sha256','query_sha256','decision_cutoff_ms')}
 scope.update(rights_reference='fixture-owned-synthetic',valid_until_ms=4102444800000)
 route=dict(secretary_root=root/'secretary',packet=packet,factory_package=package,factory_result=res)
 def call(lane,**overrides):
  args=dict(route,lane=lane,source_scope=scope,warehouse_root=root/'warehouse')
  args.update(overrides)
  return deliver_generic_research_wait(**args)
 accept=call('EXPERIMENTAL')
 assert accept['status']=='ACCEPTED' and not accept['secretary_enqueued']
 assert accept['trading_authority']=='NONE' and accept['paper']=='NOT_ACTIVATED'
 assert accept['source_query_sha256']==q['query_sha256']
 assert package['scientific_lab']['metrics']['fee_spread_slippage_bps_per_trade']=='6'
 assert all(package['factory_report'][key] is None for key in
            ('source_ack_sha256','strategy_approval_sha256','factory_consumer_ack_sha256'))
 assert call('RESEARCH_VALIDATED')['status']=='BLOCKED'
 assert not (root/'secretary').exists()
 for lane in ('LIVE','PAPER','ORDER'):
  try: call(lane)
  except GenericBridgeError as e: assert 'LANE_FORBIDDEN' in str(e)
  else: raise AssertionError(lane)
 for change in ({'valid_until_ms':0},{'rights_reference':''},{'query_sha256':'0'*64}):
  try: call('EXPERIMENTAL',source_scope={**scope,**change})
  except GenericBridgeError as e: assert 'SOURCE_SCOPE' in str(e)
  else: raise AssertionError(change)
 try: call('EXPERIMENTAL',factory_package={**package,'sha256':'0'*64})
 except ValueError: pass
 else: raise AssertionError('forged package accepted')
 def rejects(action, reason):
  try:
   action()
  except ValueError as exc:
   assert reason in str(exc), str(exc)
  else:
   raise AssertionError(f"expected {reason}")

 assert s._code_sha() == "130261351afda1642e2bda950d1f5f00f9b6fff979e234acc9ea58aa4896f099"
 old_payload = {**plugin["payload"], "evaluator_code_sha256": "18d3b6a6785cb4890c75a6d30265f546eafa941b936b2ba0900aa2c2da4bf298"}
 old_plugin = {"payload": old_payload, "sha256": digest(old_payload)}
 rejects(lambda: s.evaluate_strategy_plugin(old_plugin, q, warehouse_root=root/'warehouse',
                                           policy=policy), 'H_PLUGIN_CODE_OR_AUTHORITY_DRIFT')
 forged = seal({k: v for k, v in {**packet, 'trading_authority': 'LIVE'}.items()
                if k != 'sha256'})
 rejects(lambda: call('EXPERIMENTAL', packet=forged), 'PARENT_AUTHORITY')
 missing_cost = dict(costs)
 del missing_cost['fee_entry_bps']
 incomplete_cost = seal({k: v for k, v in {**cost, 'costs': missing_cost}.items()
                         if k != 'sha256'})
 cost_packet = seal({k: v for k, v in {**packet, 'operator_cost_policy': incomplete_cost}.items()
                     if k != 'sha256'})
 rejects(lambda: call('EXPERIMENTAL', packet=cost_packet), 'EXPLICIT_COST_POLICY_REQUIRED')
 future = copy.deepcopy(q)
 future['bars'][-1]['bar_close_ms'] = q['decision_cutoff_ms'] + 1
 future['query_sha256'] = digest({k: v for k, v in future.items() if k != 'query_sha256'})
 rejects(lambda: s.evaluate_strategy_plugin(plugin, future, warehouse_root=root/'warehouse',
                                           policy=policy), 'H_BAR')
 drift = copy.deepcopy(q)
 drift['bars'][0]['volume'] += 1
 drift['query_sha256'] = digest({k: v for k, v in drift.items() if k != 'query_sha256'})
 rejects(lambda: s.evaluate_strategy_plugin(plugin, drift, warehouse_root=root/'warehouse',
                                           policy=policy), 'H_CORE_IMMUTABLE_REPLAY_DRIFT')
 partial = query_local(root/'warehouse', q['dataset_id'], q['version'], q['start_ms'],
                       q['end_exclusive_ms'], START + STEP + 2000,
                       required_source_sha256=q['source_bytes_sha256'],
                       require_complete=False, sqlite_immutable=True)
 unknown = s.evaluate_strategy_plugin(plugin, partial, warehouse_root=root/'warehouse', policy=policy)
 assert unknown['payload']['signal_counts']['UNKNOWN'] == N
 assert all(event['next_eligible_open_ms'] is None for event in unknown['payload']['events'])
 assert not (root/'secretary').exists()
 assert not any(name.startswith(('tools.scanner_strategy_e', 'tools.scanner_strategy_b',
     'tools.scanner_strategy_f.retrospective_policy', 'research_wp_r0.aql_factory_f_f2',
     'research_wp_r0.aql_p2_factory')) for name in sys.modules)
 assert deliver_generic_research_wait(**route)['status']=='WAIT_RESEARCH_REVIEW'
 print(json.dumps(dict(bars=len(q['bars']),signals=batch['payload']['signal_counts'],experimental=accept['status'],receipt=accept['receipt_sha256'],legacy='WAIT_RESEARCH_REVIEW')))
