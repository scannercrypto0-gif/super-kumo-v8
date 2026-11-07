"""Run every independent pinned Integration CI suite and emit ONE bounded issue report.

No first-failure exit. Captured raw test stdout/stderr are NEVER printed,
stored or included in report; failures carry only static suite IDs.
"""
from __future__ import annotations
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

SCHEMA="aql.integration.collect-all-suite-gate.v1"
SUITES=(
    ("G01", "python -m unittest discover -s tests -p 'test_aql_factory_d_canonical_consumer_v1.py' -v"),
    ("G02", "python -m unittest discover -s tests -p 'test_aql_factory_e_research_results_store_v1.py' -v"),
    ("G03", "python -m unittest discover -s tests -p 'test_aql_factory_e_discoverer_consumer_v1.py' -v"),
    ("G04", "python -m unittest discover -s tests -p 'test_aql_core_e_historical_boundary_v1.py' -v"),
    ("G05", "python -m unittest discover -s tests -p 'test_aql_factory_e_historical_source_boundary_v1.py' -v"),
    ("G06", "python -m unittest discover -s tests -p 'test_aql_factory_e_core_scanner_historical_wait_v1.py' -v"),
    ("G07", "python -m unittest discover -s tests -p 'test_aql_factory_e_durable_discoverer_consumer_v1.py' -v"),
    ("G08", "python -m unittest discover -s tests -p 'test_aql_factory_e_migration_v1.py' -v"),
    ("G09", "python -m unittest discover -s tests -p 'test_aql_factory_f_batch_ledger_v1.py' -v"),
    ("G10", "python -m unittest discover -s tests -p 'test_aql_factory_f_scanner_bulk_consumer_v1.py' -v"),
    ("G11", "python -m unittest discover -s tests -p 'test_aql_factory_f_private_original_cohort_v1.py' -v"),
    ("G12", "python -m unittest discover -s tests -p 'test_aql_factory_f_role_authority_v1.py' -v"),
    ("G13", "python -m unittest tools.scanner_strategy_f.test_bulk_census -v"),
    ("G14", "python -m unittest tools.scanner_strategy_f.test_independent_policy_verification -v"),
    ("G15", "python -m unittest tools.scanner_strategy_f.test_source_bound_intake -v"),
    ("G16", "python -m unittest tools.scanner_strategy_f.test_secretary_factory_handoff -v"),
    ("G17", "python -m unittest tools.scanner_strategy_f.test_strategy_specific_decision -v"),
    ("G18", "python -m unittest tools.scanner_strategy_f.test_independent_evaluator_nomination -v"),
    ("G19", "python -m unittest tools.scanner_strategy_f.test_private_operator_bundle -v"),
    ("G20", "python -m unittest tools.scanner_strategy_f.test_research_e2e_diagnostic -v"),
    ("G21", "python -m unittest discover -s tests -p 'test_aql_core_f_research_diagnostic_query_v1.py' -v"),
    ("G22", "python -m unittest discover -s tests -p 'test_aql_factory_f_research_e2e_diagnostic_v1.py' -v"),
    ("G23", "python -m unittest discover -s tests -p 'test_atlas_f_research_diagnostic_operator.py' -v"),
    ("G24", "python -m unittest discover -s tests -p 'test_atlas_f2_recovery_evidence_v1.py' -v"),
    ("G25", "python -m unittest discover -s tests -p 'test_atlas_f2_recovery_research_operator.py' -v"),
    ("G26", "python -m unittest discover -s tests -p 'test_aql_factory_f_f2_recovery_research_v2.py' -v"),
    ("G27", "python -m unittest discover -s tests -p 'test_atlas_f2_owner_execute_v1.py' -v"),
    ("G28", "python -m unittest discover -s tests -p 'test_atlas_integration_comprehensive_preflight.py' -v"),
    ("G29", "python -m tools.atlas_integration_comprehensive_preflight"),
    ("G30", "python -m compileall -q tools/atlas_f2_owner_provenance_v1.py tools/atlas_f2_owner_factory_packet_v1.py tools/atlas_f2_owner_execute.py tools/atlas_f2_stage_owner_overlay.py"),
    ("G31", "python -m unittest discover -s tests -p 'test_aql_core_f_recovery_readonly_v1.py' -v"),
    ("G32", "python -m unittest tools.scanner_strategy_f.test_recovery_diagnostic_adapter -v"),
    ("G33", "python -m unittest discover -s tests -p 'test_aql_factory_f_f2_recovery_diagnostic_v1.py' -v"),
    ("G34", "python -m unittest discover -s tests -p 'test_aql_core_f5_secretary_authority_v1.py' -v"),
    ("G35", "python -m unittest discover -s tests -p 'test_aql_factory_e_bounded_perf_v1.py' -v"),
    ("G36", "python -m pytest tools/strategy_discoverer_offline/tests/test_package_e_durable_checkpoint.py -q"),
    ("G37", "python -m unittest discover -s tests -p 'test_aql_core_e_status_evidence_v1.py' -v"),
    ("G38", "python -m unittest tools.scanner_strategy_e.test_historical_research_policy -v"),
    ("G39", "python tools/atlas_factory_e_bounded_perf.py --strategies 12 --symbols 8 --per-pair 4 --max-seconds 30 --max-peak-mib 96 --output e-factory-performance.json"),
    ("G40", "python -m unittest tools.scanner_strategy_e.test_historical_core_screening -v"),
    ("G41", "python -m pytest tools/strategy_discoverer_offline/tests/test_package_e_membership.py -q"),
    ("G42", "python tools/atlas_e_combined_gate_manifest.py"),
)
def collect(run=None):
    if run is None:
        def run(command):
            return subprocess.run(shlex.split(command), stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, check=False, timeout=180).returncode
    rows=[]
    for suite_id,command in SUITES:
        try:
            code=run(command)
            status="PASS" if code == 0 else "FAIL"
        except subprocess.TimeoutExpired:
            status="TIMEOUT"
        except Exception:
            status="ERROR"
        rows.append({"suite_id":suite_id,"status":status})
        print("AQL_SUITE",suite_id,status,flush=True)
    return {"schema":SCHEMA,"suites":rows,
            "counts":{status:sum(r["status"]==status for r in rows)
                      for status in ("PASS","FAIL","TIMEOUT","ERROR")},
            "source":"SYNTHETIC_OR_PUBLIC_CI_ONLY",
            "original_f2_reconstructed":False,
            "f5":"BLOCKED_EXTERNAL_INPUT",
            "trading_authority":"NONE"}

def main():
    report=collect()
    target=Path("aql-comprehensive-suite-report.json")
    target.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("AQL_COLLECT_ALL_REPORT="+json.dumps(report,sort_keys=True),flush=True)
    if any(report["counts"][x] for x in ("FAIL","TIMEOUT","ERROR")):
        raise SystemExit(1)

if __name__=="__main__":
    main()
