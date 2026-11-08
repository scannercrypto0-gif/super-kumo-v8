"""Read-only H2 personal owner execution-readiness, NEVER execute original H2.

The signed exact OutputDir is reused from the successful owner R2 preparation;
the owner has NOT approved original H2 execution. No one-use claim, results
SQLite, Secretary, H2 audit, private Git upload or owner key enrollment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from tools.atlas_h2_owner_identity_v2 import (
    ENVELOPE_SCHEMA, inspect_forward_owner_assertion,
)
from tools.atlas_h2_owner_research_authority_v1 import AuthorityBlocked
from tools.atlas_h2_owner_personal_batch_v1 import (
    _load_intake, scope_commitment,
)
from tools.atlas_h2_owner_local_one_shot_v1 import (
    OWNER_LIMITED_COSTS, PINS, boundaries, build_scope,
    fingerprint, isolated_overlay, native_receipt_check, sha_file, Stop,
)
from tools.atlas_h2_binance_public_lane_v1 import (
    Blocked, verify_public_month, fetch_official,
)
from tools.atlas_h2_owner_evidence_recovery_v2 import _real_core_dual

SCHEMA="aql.integration.h2.owner-readiness.v2"
SHAS=("source_bytes_sha256","manifest_integrity_sha256",
      "strategy_definition_sha256")
FIELDS=("dataset_id","version","month","start_ms","end_exclusive_ms",
        "decision_cutoff_ms","strategy_id","strategy_definition_sha256",
        "experiment_id","source_bytes_sha256","manifest_integrity_sha256")


def require(ok,reason):
    if not ok:
        raise Blocked(reason)


def verify_signed_parent(tech,envelope,owner_key,output_dir):
    """No source access; owner identity, exact output, cost, nonce, native pins."""
    require(type(envelope) is dict and envelope.get("schema")==ENVELOPE_SCHEMA,
            "READINESS_FORWARD_V2_PACKET_REQUIRED")
    registry=Path(owner_key).parent/"owner-revocations.json"
    require(registry.is_file() and not registry.is_symlink(),
            "READINESS_OWNER_REVOCATION_REGISTRY_MISSING")
    rev=json.loads(registry.read_text("utf-8"))
    verified=inspect_forward_owner_assertion(
        envelope,owner_key_file=owner_key,revocation_registry=rev)
    claim=envelope["assertion"]["scope"]
    policy=envelope["assertion"]["cost_policy"]
    require(
        claim["owner_authorization_ref"]==
        scope_commitment(tech,output_dir,
                         identity_binding=verified["identity_binding_sha256"]),
        "READINESS_SIGNED_OUTPUT_ROOT_OR_CODE_PINS_DRIFT")
    require(all(claim[k]==tech[k] for k in FIELDS),
            "READINESS_SIGNED_SOURCE_OR_STRATEGY_PARENT_DRIFT")
    require(
        type(claim["one_use_nonce"]) is str
        and len(claim["one_use_nonce"])==32
        and all(c in "0123456789abcdef" for c in claim["one_use_nonce"]),
        "READINESS_SIGNED_NONCE_INVALID")
    require(policy["costs"]==OWNER_LIMITED_COSTS
            and claim["research_class"]=="RETROSPECTIVE_NON_PIT"
            and claim["historical_pit"]=="NOT_ATTESTED"
            and claim["publisher_pit_attested"] is False,
            "READINESS_OWNER_COST_OR_RESEARCH_CLASS_DRIFT")
    require(verified["original_h2_execution_permitted"] is False,
            "READINESS_NO_IMPLICIT_EXECUTION_AUTHORITY")
    return claim,policy,verified


def verify_overlay(repo,workspace):
    """Import real pinned worker parents in subprocess, no owner source needed."""
    root=Path(workspace)/"operator-overlay"
    root.mkdir()
    raw=isolated_overlay(repo,root)
    from tools.atlas_h2_scanner_import_seam_v2 import apply_import_seam
    seam=apply_import_seam(root)
    script=r"""
import importlib,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(root))
for mod in (
    'tools.scanner_strategy_f.research_strategy_plugin',
    'research_wp_r0.aql_core_backbone_local_v1',
    'research_wp_r0.aql_factory_h_generic_signal_adapter_v1',
    'research_wp_r0.aql_factory_lab_experiment_index_v1',
    'research_wp_r0.aql_core_h_research_secretary_v1',
    'tools.atlas_h_generic_secretary_bridge',
):
    module=importlib.import_module(mod)
    if not Path(module.__file__).resolve().is_relative_to(root):
        raise AssertionError('PINNED_IMPORT_OUTSIDE_OVERLAY')
"""
    proc=subprocess.run([sys.executable,"-I","-c",script,str(root)],
                         capture_output=True,text=True,timeout=120)
    require(proc.returncode==0,"READINESS_EXECUTION_OVERLAY_IMPORT_FAILED")
    return {"sha256":raw,
            "scanner_f3_import_seam_sha256":[
                x["isolated_seam_sha256"] for x in seam["changed_modules"]]}


def validate_owner_readiness(evidence_dir,output_dir,owner_key,git_repo,
                             *,fetcher=fetch_official,
                             publisher=verify_public_month,
                             core_query=_real_core_dual,
                             overlay_check=verify_overlay):
    """Fail closed, never reserve one-use. Return sanitized status/reason."""
    report={"schema":SCHEMA,"status":"BLOCKED","reason":"UNVERIFIED",
            "original_h2_executed":False,
            "one_use_claim_created":False,
            "g0_approved":False,
            "independent_rights":"NOT_ATTESTED",
            "historical_pit":"NOT_ATTESTED",
            "approved_to_trade":False}
    roots=None
    before=None
    try:
        tech,envelope,folder=_load_intake(evidence_dir)
        out=Path(output_dir).absolute()
        require(out.is_dir() and not out.is_symlink(),
                "READINESS_SIGNED_OUTPUT_ROOT_NOT_FOUND")
        require(git_repo is not None and Path(git_repo).is_dir(),
                "READINESS_PINNED_CODE_REPO_MISSING")
        claim,policy,verified=verify_signed_parent(
            tech,envelope,owner_key,out)
        require(all(tech[x] and type(tech[x]) is str for x in SHAS),
                "READINESS_MISSING_SOURCE_PARENTS")
        require(not any((folder/x).exists() for x in (
            "h2-personal-one-use-claim.json","h2-single-use-claim.json")),
            "READINESS_ONE_USE_CLAIM_ALREADY_EXISTS")
        require(not any((out/x).exists() for x in (
            "h2-personal-scope-claim.json","h2-batch-summary.json",
            "results.sqlite","secretary","h2-audit.json")),
            "READINESS_OUTPUT_ALREADY_CLAIMED")
        opscope=build_scope(tech,folder,out)
        roots,_=boundaries(opscope,owner_key,Path(git_repo).resolve())
        native=json.loads((folder/"core245-native-receipt.json").read_text("utf-8"))
        native_sha=native_receipt_check(opscope,native)
        require(native_sha==claim["core245_native_receipt_sha256"],
                "READINESS_CORE245_SIGNED_SHA_DRIFT")
        from research_wp_r0.strategy_definition import StrategyDefinition
        from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2
        from tools.scanner_strategy_f import research_strategy_plugin as scanner
        from tools.strategy_service_offline.common import Frozen
        definition=json.loads((folder/"manual-third-ast.json").read_text("utf-8"))
        strategy=StrategyDefinition.from_dict(
            definition,registry=IndicatorRegistryV2())
        require(strategy.digest==claim["strategy_definition_sha256"]
                and strategy.spec["strategy_id"]=="h_manual_distinct_test",
                "READINESS_MANUAL_AST_DRIFT")
        config=scanner.manual_config_digest(definition)
        plugin=scanner.register_strategy_plugin(
            definition,config_digest=config,origin="MANUAL")
        require(config==claim["strategy_config_sha256"]
                and Frozen.restore(plugin).data["evaluator_code_sha256"]==
                    claim["evaluator_code_sha256"],
                "READINESS_MANUAL_SCANNER_CODE_DRIFT")
        from research_wp_r0 import aql_factory_h_generic_signal_adapter_v1 as factory
        require(sha_file(factory.__file__)==tech["factory_code_sha256"],
                "READINESS_FACTORY_PINNED_SOURCE_DRIFT")
        # No E: source access before full identity/cost/native/strategy checks.
        proof=publisher(tech["month"],fetcher=fetcher)
        require(
            proof["zip_bytes_sha256"]==tech["source_bytes_sha256"]
            and proof["bar_count"]==2976
            and proof["first_open_ms"]==tech["start_ms"]
            and proof["end_exclusive_ms"]==tech["end_exclusive_ms"],
            "READINESS_OFFICIAL_PUBLISHER_SOURCE_DRIFT")
        zip_path=Path(tech["local_source_zip"]).resolve(strict=True)
        require(zip_path.is_file() and not zip_path.is_symlink()
                and zip_path.name==proof["filename"]
                and sha_file(zip_path)==proof["zip_bytes_sha256"],
                "READINESS_ORIGINAL_ZIP_PUBLISHER_MISMATCH")
        before=[fingerprint(root) for root in roots]
        with tempfile.TemporaryDirectory(prefix="aql-h2-ready-",dir=out) as d:
            from tools.atlas_h2_owner_local_one_shot_v1 import (
                verified_local_sqlite_snapshot,
            )
            snapshot=verified_local_sqlite_snapshot(roots[0],d)
            rebuilt,local,dataset,version,manifest=core_query(
                snapshot,proof["zip_bytes_sha256"])
            require(
                rebuilt["price_query_sha256"]==native_sha
                and local["query_sha256"]==claim["core253_query_sha256"]
                and (dataset,version,manifest)==(
                    tech["dataset_id"],tech["version"],
                    tech["manifest_integrity_sha256"]),
                "READINESS_CORE245_CORE253_PARENTS_DRIFT")
            code=overlay_check(Path(git_repo),d)
        require(before==[fingerprint(root) for root in roots]
                and sha_file(zip_path)==proof["zip_bytes_sha256"],
                "READINESS_ORIGINAL_SOURCE_CHANGED_STOP")
        report.update({
            "status":"READY_FOR_SEPARATE_OWNER_EXECUTION_APPROVAL",
            "reason":None,
            "source_parent_sha256":proof["zip_bytes_sha256"],
            "native_core245_sha256":native_sha,
            "bounded_core253_sha256":local["query_sha256"],
            "strategy_definition_sha256":strategy.digest,
            "strategy_config_sha256":config,
            "operator_overlay_sha256":code["sha256"],
            "isolated_scanner_seam_sha256":code["scanner_f3_import_seam_sha256"],
            "one_use_nonce_sha256":hashlib.sha256(
                claim["one_use_nonce"].encode("ascii")).hexdigest(),
            "owner_identity_key_id":verified["key_id"],
            "owner_custody":"CONFIRM_INDEPENDENT_BACKUP_BEFORE_EXECUTION",
            "additional_owner_permission":"REQUIRED_FOR_ORIGINAL_H2",
        })
    except Exception as exc:
        allowed=(Blocked,AuthorityBlocked,Stop)
        reason=str(exc) if isinstance(exc,allowed) else (
            "READINESS_PRIVATE_PROOF_OR_RUNTIME_"+type(exc).__name__)
        report["reason"]="BLOCKED_"+reason
    finally:
        if roots is not None and before is not None:
            try:
                if [fingerprint(x) for x in roots]!=before:
                    report["status"]="BLOCKED"
                    report["reason"]="BLOCKED_READINESS_ORIGINAL_SOURCE_DRIFT"
            except Exception:
                report["status"]="BLOCKED"
                report["reason"]="BLOCKED_READINESS_SOURCE_READBACK_UNAVAILABLE"
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description="Read-only owner H2 readiness; NO RUN")
    p.add_argument("--private-evidence-dir",required=True)
    p.add_argument("--signed-output-dir",required=True)
    p.add_argument("--owner-signing-key",required=True)
    p.add_argument("--pinned-git-repo",required=True)
    args=p.parse_args(argv)
    out=Path(args.signed_output_dir).absolute()
    report=validate_owner_readiness(
        args.private_evidence_dir,out,args.owner_signing_key,args.pinned_git_repo)
    # Persist only sanitized decision in the *already owner-signed* output
    # directory. No one-shot claim, no results SQLite or Secretary artifacts.
    dest=out/"h2-readiness-summary.json"
    if dest.exists() or dest.is_symlink() or not out.is_dir():
        print(json.dumps({"status":"BLOCKED",
                          "reason":"BLOCKED_READINESS_REPORT_ALREADY_EXISTS"}))
        return 2
    with dest.open("x",encoding="utf-8") as f:
        json.dump(report,f,sort_keys=True,indent=2)
    print(json.dumps({"status":report["status"],"reason":report["reason"],
                      "summary_filename":dest.name},sort_keys=True))
    return 0 if report["status"]=="READY_FOR_SEPARATE_OWNER_EXECUTION_APPROVAL" else 2


if __name__=="__main__":
    raise SystemExit(main())
