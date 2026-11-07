"""Single owner-private F2 recovery research execution (isolated overlay only).

1. Independently derive missing provenance from protected source, 2. source
replay/Scanner on genuine data, 3. build Factory packet only from real
ledger, cost policy, and frozen Work235, 4. run isolated SQLite v2 replay.
Missing dependencies produce ONE sanitized missing-field manifest, never a
fictitious private PASS or public OHLCV/path leak.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

from tools.atlas_f2_owner_provenance_v1 import collect_recovery_source
from tools.atlas_f2_owner_factory_packet_v1 import (
    build_factory_packet, policy_missing,
)
from tools.atlas_f2_recovery_research_operator import (
    run as run_research_operator,
)
from tools.atlas_f_research_diagnostic_operator import verify_pinned_modules
from tools.strategy_service_offline.common import Frozen
from tools.scanner_strategy_f.frozen_diagnostic_contracts import (
    load_frozen_work235_contracts,
)
from tools.scanner_strategy_f.recovery_diagnostic_adapter import (
    diagnostic_from_verified_recovery,
)
from tools.atlas_f2_recovery_evidence_v1 import EXPECTED_RECOVERY_FILE_SHA256

SCHEMA="aql.integration.owner-local-f2-one-command.v1"
KEYS={
    "schema","owner_operator_authorized","warehouse_root","vault_root",
    "recovery_file","policy_file","trial_ledger_file",
    "inventory_receipts_file","isolated_workspace",
}
MISSING_FIELDS=("policy_file",)
FULL_INPUTS=("warehouse_root","vault_root","recovery_file")


def _resolved_input(value):
    if type(value) is not str or not value:
        return None
    p=Path(value).absolute()
    # Reject reparse/symlink redirection, including an existing parent.
    if any(x.is_symlink() for x in (p,*p.parents)):
        return None
    return p


def _load_optional(path):
    p=_resolved_input(path)
    if p is None or not p.is_file() or p.stat().st_size > 50_000_000:
        return None
    try:
        return json.loads(p.read_bytes())
    except (ValueError, UnicodeError):
        return None


def _safe_write(path, value):
    assert not path.exists() and not path.is_symlink()
    path.write_text(json.dumps(value,sort_keys=True,ensure_ascii=True,
                     separators=(",",":"),allow_nan=False)+"\n",
                    encoding="utf-8")


def _sanitized_wait(missing):
    return {"schema":"aql.integration.owner-local-missing-fields.v1",
            "status":"PRIVATE_WAIT",
            "missing_fields":sorted(set(missing)),
            "source_original_f2_reconstructed":False,
            "f5":"BLOCKED_EXTERNAL_INPUT",
            "trading_authority":"NONE"}


def run(manifest):
    if (type(manifest) is not dict or set(manifest)!=KEYS or
        manifest.get("schema")!=SCHEMA or
        manifest.get("owner_operator_authorized") is not True):
        return _sanitized_wait(["operator.manifest_or_authorization"])
    missing=[]
    for field in FULL_INPUTS:
        p=_resolved_input(manifest[field])
        if p is None or not (
            p.is_dir() if field in ("warehouse_root","vault_root")
            else p.is_file()):
            missing.append(field)
    root=_resolved_input(manifest["isolated_workspace"])
    if root is None or not root.is_dir() or root.is_symlink():
        missing.append("isolated_workspace")
    # Optional Factory-specific inputs are checked AFTER actual source
    # derivation. Even when policy is missing, the independently proven
    # 10-row mapping is collected and saved in this isolated workspace.
    # Collect ALL unavailable v2 policy fields in one batch,
    # but still derive provenance when the genuine sources are accessible.
    docs={key:_load_optional(manifest[key]) for key in MISSING_FIELDS}
    optional_needed=policy_missing(docs["policy_file"])
    if missing:
        return _sanitized_wait(missing+optional_needed)

    warehouse=_resolved_input(manifest["warehouse_root"])
    vault=_resolved_input(manifest["vault_root"])
    recovery=_resolved_input(manifest["recovery_file"])
    protected=(warehouse,vault,recovery.parent)
    if (len(set(protected))<3 or
        any(root==p or p in root.parents or root in p.parents
            for p in protected)):
        return _sanitized_wait(["isolated_workspace_outside_private_sources"])
    targets=(
        root/"f2-ten-month-mapping.json",
        root/"f2-factory-recovery-input.json",
        root/"f2-results-fresh-v2.sqlite",
        root/"f2-sanitized-output.json",
    )
    if any(p.exists() or p.is_symlink() for p in targets):
        return _sanitized_wait(["isolated_fresh_outputs_required"])

    # Staging was done in a distinct Git worktree; do NOT assume main=PR.
    verify_pinned_modules()
    mapping,original=collect_recovery_source(warehouse,vault,recovery)
    _safe_write(targets[0],mapping)
    work=Path(__file__).resolve().parents[1] / (
        "tools/strategy_service_offline/fixtures/strategies.json")
    frozen=load_frozen_work235_contracts(work)
    scanner=diagnostic_from_verified_recovery(
        warehouse_root=warehouse,
        verified_recovery_readbacks=original,
        recovery_file_sha256=EXPECTED_RECOVERY_FILE_SHA256,
        work_specs=frozen["work_specs"])
    policy=docs["policy_file"]
    if optional_needed:
        # Mapping was independently derived; do not invent cost policy.
        return _sanitized_wait(optional_needed)
    factory=build_factory_packet(
        original=original, scanner_receipt=scanner,
        work_specs=frozen["work_specs"],policy=policy,
        ledger=None,inventory=None)
    _safe_write(targets[1],factory)
    run_manifest={
        "schema":"aql.integration.f2-recovery-research-operator.v1",
        "owner_operator_authorized":True,
        "warehouse_root":str(warehouse),
        "vault_root":str(vault),
        "recovery_file":str(recovery),
        "recovery_mapping_file":str(targets[0]),
        "frozen_work235_file":str(work),
        "factory_recovery_input_file":str(targets[1]),
        "fresh_results_store":str(targets[2]),
        "sanitized_output":str(targets[3]),
    }
    result=run_research_operator(run_manifest)
    if (result["status"]!="RESEARCH_E2E_DIAGNOSTIC_PASS" or
        result["f5"]!="BLOCKED_EXTERNAL_INPUT" or
        result["trading_authority"]!="NONE"):
        raise ValueError("AQL_F2_OWNER_DIAGNOSTIC_AUTHORITY_DRIFT")
    return {"schema":"aql.integration.owner-local-f2-one-command-result.v1",
            "status":result["status"],"sanitized_sha256":result["sha256"],
            "original_bars":result["original_bars"],
            "attempts":result["attempts"],
            "scanner_evaluated":result["scanner_evaluated"],
            "feb_aug_unknown":result["feb_aug_unknown"],
            "immutable_replay":result["immutable_replay"],
            "f5":result["f5"],"trading_authority":"NONE"}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--operator-manifest",required=True)
    args=parser.parse_args()
    try:
        m=_load_optional(args.operator_manifest)
        if m is None:
            outcome=_sanitized_wait(["operator.manifest_file"])
        else:
            outcome=run(m)
        print(json.dumps(outcome,sort_keys=True))
        if outcome["status"]=="PRIVATE_WAIT":
            raise SystemExit(2)
    except SystemExit:
        raise
    except Exception as exc:
        # Never print private paths, market bars or raw JSON. Only bounded
        # already-source-code-defined error classes can pass through.
        msg=str(exc)
        allowed=("CORE_F2_RECOVERY_","F2_RECOVERY_","F2_OWNER_FACTORY_",
                 "AQL_DIAG_","FACTORY_DIAGNOSTIC_","F_DIAG_")
        code=msg if any(msg.startswith(x) for x in allowed) else (
            "OWNER_PRIVATE_SOURCE_OR_PACKET_VALIDATION_ERROR")
        print(json.dumps({**_sanitized_wait(["private_source_or_packet"]),
                          "code":code},sort_keys=True))
        raise SystemExit(2)


if __name__=="__main__":
    main()
