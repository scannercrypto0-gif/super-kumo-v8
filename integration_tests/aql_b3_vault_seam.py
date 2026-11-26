"""B3 exact original TEST_ONLY Core container -> actual Vault -> Factory consumer.

Pinned, read-only imports from separate Core/Factory worktrees. No old B1/B2
tests, market replay, positive external-witness callback or F1 identity rewrite.
"""
from __future__ import annotations

import argparse
import copy
import importlib
import json
import subprocess
import sys
import types
from pathlib import Path

from tools.raw_vault_offline.b3_handoff import (
    admit_core_container, canonical, require, sha, verify_local_readback,
)

CORE_PIN = '83d44ef23392b9ca9628d18d0f6fc909cd98e4ff'
FACTORY_PIN = 'ac7f160005672140a3254eb2ed82f4d586432b69'


def pinned_modules(core_root, factory_root):
    # These paths and full commit identities are explicit inputs, not an implicit
    # import from an unrelated installed module or a mutable branch checkout.
    paths=[]
    for root,pin in ((factory_root,FACTORY_PIN),(core_root,CORE_PIN)):
        root=Path(root).resolve()
        actual=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
        require(actual == pin, 'READ_ONLY_DEPENDENCY_HEAD_DRIFT')
        # Tracked modifications would defeat the commit pin even if HEAD matched.
        require(subprocess.run(['git','-C',str(root),'diff','--quiet','HEAD','--','research_wp_r0']).returncode == 0,
                'READ_ONLY_DEPENDENCY_SOURCE_DIRTY')
        paths.append(str(root/'research_wp_r0'))
    namespace='_aql_b3_pinned_research'
    package=types.ModuleType(namespace); package.__path__=paths
    sys.modules[namespace]=package
    consumer=importlib.import_module(namespace+'.aql_w1_f1_prospective_consumer')
    core=importlib.import_module(namespace+'.aql_f1_decision_capture_v1')
    parent=importlib.import_module(namespace+'.aql_f1_parent_witness_v1')
    return consumer,core,parent


def verify_loaded_sources():
    sources={}
    for name,module in tuple(sys.modules.items()):
        if not name.startswith('_aql_b3_pinned_research.'):
            continue
        path=Path(module.__file__).resolve()
        root=path.parents[1]
        pin=CORE_PIN if path.name.startswith('aql_f1_') else FACTORY_PIN
        require(subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip() == pin,
                'IMPORTED_MODULE_WRONG_OWNER_OR_HEAD')
        expected=subprocess.check_output(['git','-C',str(root),'show','HEAD:research_wp_r0/'+path.name])
        require(expected == path.read_bytes(), 'IMPORTED_MODULE_BYTES_DRIFT')
        sources[path.name]=dict(commit=pin,sha256=sha(expected))
    return sources


def project_readback(vault_root, receipt, modules, mutate=None):
    consumer,validator,parent=modules
    # Consume exactly the freshly checked Vault readback, not a parallel caller
    # candidate list; hashes/manifest are rechecked before JSON is interpreted.
    raw=verify_local_readback(vault_root,receipt)
    core=json.loads(raw)
    records=copy.deepcopy(core['original_candidates_test_only'])
    if mutate is not None:
        mutate(records,validator)  # test-only adversarial branch, never CLI input
    schedule=core['schedule']
    by_pair={s['pair_id']:raw for s in schedule}
    meta={s['pair_id']:receipt['manifest_entry'] for s in schedule}
    # Container metadata is NOT market-source metadata. We pass the actual
    # local chain but no absent market derivative or independent proof, so the
    # existing real Factory parent gate must fail closed. No g1->0 mapping.
    result=consumer.project_parent_authenticated_f1_slots(
        schedule,records,parent_bytes_by_pair=by_pair,manifest_by_pair=meta,
        derived_bars_by_pair={},derived_evidence_by_pair={},
        indicator_registry=core['indicator_registry'],
        verify_parent_manifest=None,verify_derivation=None,
        verify_external_receipt=None,proof_verifier=None)
    require(result['scheduled_total'] == 2 and result['arm_slots'] == 4
            and result['outcome_rows'] == 12, 'N_2N_6N_LOSS')
    require(len({(r['pair_id'],r['arm'],r['horizon_ms']) for r in result['outcomes']}) == 12,
            'DUPLICATE_OR_MISSING_HORIZON')
    require(all(r['capture_status'] != 'RECORDED' and r['coverage_status'] == 'UNKNOWN'
                and r['max_favorable'] is None and r['max_adverse'] is None
                and r['no_fill_or_pnl_inference'] is True for r in result['outcomes']),
            'UNSUPPORTED_SOURCE_OR_DIRECTION_PROMOTION')
    return result


def run(core_bytes, vault_root, out, modules):
    out=Path(out); out.mkdir(parents=True,exist_ok=False)
    receipt,restored,manifest=admit_core_container(core_bytes,vault_root)
    projection=project_readback(vault_root,receipt,modules)
    report=dict(schema='aql.b3.vault-local-factory-seam.v1',
        project_id='AQL-CRYPTO-RESEARCH-001',
        verdict='LOCAL_VAULT_SOFTWARE_SEAM_PASS_EXTERNAL_SOURCE_JOIN_BLOCKED',
        core_sha=CORE_PIN,factory_sha=FACTORY_PIN,
        core_input_sha256=sha(core_bytes),readback_receipt_sha256=receipt['receipt_sha256'],
        exact_manifest_bytes_sha256=sha(manifest),
        n=2,arm_slots_2n=4,outcome_rows_6n=12,
        capture_statuses=projection['capture_status_counts'],
        seams=dict(core_original_TEST_ONLY_container_to_actual_vault_admit_read='PASS',
            actual_readback_to_factory_parent_consumer='PASS_FAIL_CLOSED_4_UNVERIFIED_12_UNKNOWN',
            original_F1_market_source_parent_to_verified_factory='BLOCKED_ORIGINAL_SOURCE_PARENT_NOT_SUPPLIED',
            external_issuer_custody_clock='BLOCKED_EXTERNAL_EVIDENCE',
            actual_monitor_to_outcomes='NOT_CONNECTED',
            real_prospective_producer_preF3='NOT_CONNECTED'),
        blockers=['Core claimed source SHA aaaa... is a fixture identity, not the capture-container SHA',
                  'Original source bytes/immutable issuer manifest and parent transformation lineage not supplied',
                  'Core correction generation g1 preserved; container generation0 is a separate local object identity',
                  'Source/correction publication clocks UNKNOWN; local admission clock is not source availability',
                  'No independent issuer/custodian/clock/freeze witness; no synthetic True verifier used'],
        factory_projection=projection,original_f1_links=receipt['original_f1_links'],
        executed_readonly_sources=verify_loaded_sources(),
        original_2024_strategy_signal=False,operational_pit=False,
        strategy_efficacy_or_pnl=False,g0_or_deployment_authorized=False)
    for name,data in (('readback-receipt.json',canonical(receipt)),
                      ('parent-manifest.jsonl',manifest),('original-core-container.json',restored),
                      ('system-integrity.json',canonical(report))):
        (out/name).write_bytes(data)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('core-json','core-root','factory-root','vault-root','out'):
        p.add_argument('--'+arg,type=Path,required=True)
    args=p.parse_args()
    modules=pinned_modules(args.core_root,args.factory_root)
    report=run(args.core_json.read_bytes(),args.vault_root,args.out,modules)
    print('B3_VERDICT='+report['verdict'])
    print('N=2 2N=4 6N=12; '+str(report['capture_statuses']))
    for path in sorted(args.out.iterdir()):
        print(sha(path.read_bytes())+'  '+path.name)


if __name__ == '__main__':
    main()
