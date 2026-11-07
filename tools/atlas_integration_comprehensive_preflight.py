"""ATLAS Integration C — privacy-safe collect-all *static* cross-owner preflight.

Runs independent contract checks; dependent checks are BLOCKED, never PASS.
This is not an owner-private E: source run, F2 reconstruction or F5 gate.
"""
from __future__ import annotations

import argparse
import inspect
import json
from pathlib import Path
import re

SCHEMA = "aql.integration.comprehensive-preflight.v1"
ORDER = (
    "PIN_MANIFEST", "SCANNER_COHORT_SIGNATURE", "SCANNER_PHASE_CONTRACT",
    "SCANNER_MONTH_SCOPE", "WORK235_FROZEN_IDENTITIES",
    "CORE_IMMUTABLE_QUERY_CONTRACT", "FACTORY_REAL_KERNEL_CONTRACT",
    "OWNER_SCANNER_CALLBACK", "OWNER_PRIVACY_SANITIZER",
    "ORIGINAL_PRIVATE_SOURCE",
)
DEPENDENCIES = {
    "SCANNER_COHORT_SIGNATURE": ("PIN_MANIFEST",),
    "SCANNER_PHASE_CONTRACT": ("SCANNER_COHORT_SIGNATURE",),
    "SCANNER_MONTH_SCOPE": ("SCANNER_COHORT_SIGNATURE",),
    "WORK235_FROZEN_IDENTITIES": ("PIN_MANIFEST",),
    "CORE_IMMUTABLE_QUERY_CONTRACT": ("PIN_MANIFEST",),
    "FACTORY_REAL_KERNEL_CONTRACT": ("PIN_MANIFEST",),
    "OWNER_SCANNER_CALLBACK": ("SCANNER_PHASE_CONTRACT",),
    "OWNER_PRIVACY_SANITIZER": ("OWNER_SCANNER_CALLBACK",),
}
# Fixed identifiers only: never leak exception text, paths, OHLCV or hashes.
def _checks():
    from tools.atlas_e_combined_gate_manifest import PINS
    from tools.atlas_f2_owner_execute import SAFE_STAGES, run
    from tools.scanner_strategy_f import research_e2e_diagnostic as cohort
    from tools.scanner_strategy_f import recovery_diagnostic_adapter as adapter
    from tools.scanner_strategy_f.frozen_diagnostic_contracts import FROZEN
    from research_wp_r0 import aql_core_backbone_local_v1 as core
    from research_wp_r0 import aql_factory_f_research_e2e_diagnostic_v1 as factory
    return {
        "PIN_MANIFEST": lambda: all(
            type(v) is str and re.fullmatch("[0-9a-f]{40}", v)
            for v in PINS.values()
        ) and {"core_f","scanner_f","factory_e","work235"} <= set(PINS),
        "SCANNER_COHORT_SIGNATURE": lambda: (
            "phase_callback" in inspect.signature(cohort.diagnostic_original_cohort).parameters
            and "month_queries" in inspect.signature(cohort.diagnostic_original_cohort).parameters
        ),
        "SCANNER_PHASE_CONTRACT": lambda: (
            len(cohort.SAFE_COHORT_PHASES) >= 10
            and cohort.SAFE_COHORT_PHASES <= adapter.SAFE_COHORT_PHASES
            and cohort.SAFE_COHORT_PHASES <= SAFE_STAGES
        ),
        "SCANNER_MONTH_SCOPE": lambda: (
            len(cohort.ADMITTED) == 10
            and len(set(cohort.ADMITTED)) == 10
            and "2024-02" not in cohort.ADMITTED
            and "2024-08" not in cohort.ADMITTED
        ),
        "WORK235_FROZEN_IDENTITIES": lambda: (
            set(FROZEN) == {"test_momentum","test_reversion"}
            and all(len(x["definition_digest"]) == 64 for x in FROZEN.values())
        ),
        "CORE_IMMUTABLE_QUERY_CONTRACT": lambda: (
            "sqlite_immutable" in inspect.signature(core.query_local).parameters
        ),
        "FACTORY_REAL_KERNEL_CONTRACT": lambda: (
            callable(factory.validate_diagnostic_input)
            and callable(cohort._eval_strategy)
        ),
        "OWNER_SCANNER_CALLBACK": lambda: (
            "phase_callback" in inspect.signature(adapter.diagnostic_from_verified_recovery).parameters
            and "manifest" in inspect.signature(run).parameters
        ),
        "OWNER_PRIVACY_SANITIZER": lambda: (
            "COHORT_SCOPE_VERIFY" in SAFE_STAGES
            and "COHORT_FACTORY_KERNEL" in SAFE_STAGES
        ),
    }


def collect(checks=None, *, private_source_available=False):
    checks = _checks() if checks is None else checks
    rows = []
    status = {}
    for key in ORDER:
        parents = DEPENDENCIES.get(key, ())
        if key == "ORIGINAL_PRIVATE_SOURCE":
            state = "BLOCKED_EXTERNAL_INPUT"
        elif any(status.get(parent) != "PASS" for parent in parents):
            state = "BLOCKED_DEPENDENCY"
        elif key not in checks:
            state = "FAIL"
        else:
            try:
                state = "PASS" if checks[key]() is True else "FAIL"
            except Exception:
                state = "FAIL"
        status[key] = state
        rows.append({"check_id":key, "status":state})
    return {
        "schema":SCHEMA,
        "checks":rows,
        "counts":{key:sum(row["status"] == key for row in rows)
                  for key in ("PASS","FAIL","BLOCKED_DEPENDENCY","BLOCKED_EXTERNAL_INPUT")},
        "original_f2_reconstructed":False,
        "f5":"BLOCKED_EXTERNAL_INPUT",
        "historical_pit":"NOT_ATTESTED",
        "trading_authority":"NONE",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", help="Fresh output path outside private source")
    args = parser.parse_args()
    report = collect()
    if args.output:
        target = Path(args.output).absolute()
        if target.exists() or target.is_symlink():
            raise SystemExit("PREFLIGHT_FRESH_OUTPUT_REQUIRED")
        target.write_text(json.dumps(report, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(1 if report["counts"]["FAIL"] else 0)


if __name__ == "__main__":
    main()
