"""H2 opt-in OWNER PERSONAL RESEARCH lane, distinct from licensed official lane.

No claim of independent rights clearance. Owner attests own personal research
scope with a preexisting independently retained private key and separately
MAC-authenticated costs. All technical publisher/source/Core/AST gates remain.
No owner private original file is read before these source-use gates.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path

from tools.atlas_h2_owner_research_authority_v1 import (
    AUTHORITY, COST_KEYS, AuthorityBlocked, _canonical,
    _digest, inspect_owner_assertion,
)
from tools.atlas_h2_binance_public_lane_v1 import (
    Blocked, LANE_SCHEMA, TECH_FIELDS, validate_native_manual_third_ast,
    verify_public_month, fetch_official, fail,
)
from tools.atlas_h2_owner_local_one_shot_v1 import (
    SCHEMA as OPERATOR_SCHEMA, OWNER_LIMITED_COSTS, PINS,
    canonical, contained, digest, execute, native_receipt_check, sha_file,
    verify_owner,
)
from tools.atlas_h2_private_batch_bootstrap_v1 import (
    build_scope, single_report, write_report, _key,
)

REQUIRED = frozenset((
    "technical-intake.json", "owner-personal-assertion.json",
    "core245-native-receipt.json", "manual-third-ast.json",
))
SCHEMA = "aql.integration.h2.owner-personal-batch.v1"


def _load_intake(folder):
    root = Path(folder).resolve(strict=True)
    fail(root.is_dir() and not root.is_symlink(), "PERSONAL_EVIDENCE_ROOT_INVALID")
    missing = sorted(x for x in REQUIRED if not (root / x).is_file())
    fail(not missing, "MISSING_OWNER_PERSONAL_EVIDENCE:" + ",".join(missing))
    for filename in REQUIRED:
        file = root / filename
        fail(not file.is_symlink() and file.stat().st_size <= 250_000,
             "PERSONAL_EVIDENCE_FILE_UNSAFE")
    try:
        tech = json.loads((root / "technical-intake.json").read_text("utf-8"))
        packet = json.loads((root / "owner-personal-assertion.json").read_text("utf-8"))
    except (ValueError, UnicodeError, OSError):
        raise Blocked("PERSONAL_EVIDENCE_INVALID_JSON") from None
    fail(type(tech) is dict and set(tech) == TECH_FIELDS
         and tech["schema"] == LANE_SCHEMA
         and tech["owner_authorization_ref"] == "#205/6718325330"
         and tech["one_time_scope_authorized"] is True,
         "PERSONAL_TECHNICAL_INTAKE_INVALID")
    for name,field in (("core245-native-receipt.json","native_receipt_file_sha256"),
                       ("manual-third-ast.json","strategy_file_sha256")):
        fail(type(tech[field]) is str
             and sha_file(root / name) == tech[field],
             "PERSONAL_RECEIPT_FILE_SHA_DRIFT")
    # This guard is before original ZIP/source read, not a strategy approval.
    validate_native_manual_third_ast(
        root/"manual-third-ast.json",
        tech["strategy_definition_sha256"],tech["strategy_id"])
    return tech, packet, root


def scope_commitment(tech, output_root):
    """Only a pre-approved owner MAC binding concrete root+full tech+pins works."""
    output = str(Path(output_root).absolute())
    return "OWNER_PERSONAL_EXACT_INTAKE_SHA256:" + _digest({
        "technical_intake": tech,
        "output_root": output,
        "frozen_role_pins": PINS,
        "research_authority": AUTHORITY,
    })


def run_owner_personal_batch(evidence_dir, output_dir, *,
                             owner_key=None, git_repo=None,
                             confirm_one_run=False, fetcher=fetch_official,
                             operator=execute):
    details = {"lane":"OWNER_PERSONAL_NONCOMMERCIAL_RESEARCH_ASSERTED",
               "independent_license_review":"NOT_ATTESTED",
               "historical_pit":"NOT_ATTESTED",
               "third_party_rights":"UNVERIFIED",
               "research_only":True}
    invoked=False
    try:
        tech,packet,root=_load_intake(evidence_dir)
        fail(owner_key is not None, "OWNER_EXISTING_SIGNING_KEY_REQUIRED")
        try:
            signed=inspect_owner_assertion(
                packet,trusted_owner_verifier_key=owner_key)
        except (AuthorityBlocked, OSError, ValueError):
            raise Blocked("OWNER_PERSONAL_SCOPE_OR_COST_MAC_UNVERIFIED") from None
        assert signed["original_h2_execution_permitted"] is False
        scope=packet["scope"]
        policy=packet["cost_policy"]
        fail(scope["owner_authorization_ref"] ==
             scope_commitment(tech,output_dir),
             "OWNER_PERSONAL_TECH_ROOT_OR_PIN_DRIFT")
        fail(scope["source_bytes_sha256"] == tech["source_bytes_sha256"]
             and scope["manifest_integrity_sha256"] ==
                 tech["manifest_integrity_sha256"]
             and scope["dataset_id"] == tech["dataset_id"]
             and scope["version"] == tech["version"]
             and scope["month"] == tech["month"]
             and scope["start_ms"] == tech["start_ms"]
             and scope["end_exclusive_ms"] == tech["end_exclusive_ms"]
             and scope["decision_cutoff_ms"] == tech["decision_cutoff_ms"]
             and scope["strategy_id"] == tech["strategy_id"]
             and scope["strategy_definition_sha256"] ==
                 tech["strategy_definition_sha256"]
             and scope["experiment_id"] == tech["experiment_id"],
             "OWNER_PERSONAL_SIGNED_SCOPE_VS_INTAKE_MISMATCH")
        fail(policy["costs"] == OWNER_LIMITED_COSTS,
             "OWNER_ENGINEERING_COST_POLICY_MISMATCH")
        fail(scope["research_class"] == "RETROSPECTIVE_NON_PIT"
             and scope["historical_pit"] == "NOT_ATTESTED"
             and scope["publisher_pit_attested"] is False,
             "OWNER_PERSONAL_RESEARCH_ONLY")
        fail(confirm_one_run is True and git_repo is not None,
             "OWNER_PERSONAL_ONE_RUN_CONFIRMATION_OR_CODE_MISSING")
        # Publisher HTTPS + exact month checksum is real technical provenance,
        # never a digital signature or external license attestation.
        proof=verify_public_month(tech["month"],fetcher=fetcher)
        details["publisher_zip_sha256"]=proof["zip_bytes_sha256"]
        details["publisher_checksum_response_sha256"]=proof["checksum_response_sha256"]
        fail(proof["bar_count"] == 2976
             and proof["first_open_ms"] == tech["start_ms"]
             and proof["end_exclusive_ms"] == tech["end_exclusive_ms"]
             and proof["zip_bytes_sha256"] == tech["source_bytes_sha256"],
             "PERSONAL_PUBLISHER_SOURCE_OR_MONTH_MISMATCH")
        # Owner/private E: access starts only AFTER real preexisting owner
        # scope AND independent purpose-specific cost MAC verification.
        local=Path(tech["local_source_zip"]).resolve(strict=True)
        fail(local.is_file() and not local.is_symlink()
             and local.name == proof["filename"],
             "PERSONAL_ORIGINAL_ZIP_LOCATION_INVALID")
        fail(sha_file(local)==proof["zip_bytes_sha256"],
             "PERSONAL_ORIGINAL_ZIP_NOT_PUBLISHER_IDENTICAL")
        details["original_zip_publisher_match"]=True
        root_warehouse=Path(tech["warehouse_root"]).resolve(strict=True)
        root_vault=Path(tech["vault_root"]).resolve(strict=True)
        out=Path(output_dir).absolute()
        fail(root_warehouse.is_dir() and root_vault.is_dir()
             and root_warehouse != root_vault
             and not contained(out,root_warehouse)
             and not contained(out,root_vault)
             and not contained(out,root)
             and not contained(root,out)
             and not contained(root,root_warehouse)
             and not contained(root,root_vault)
             and not contained(local,out)
             and not contained(owner_key,root_warehouse)
             and not contained(owner_key,root_vault)
             and not contained(owner_key,git_repo),
             "PERSONAL_SOURCE_OUTPUT_OR_OWNER_KEY_OVERLAP")
        fail(out.is_dir() and not out.is_symlink(),
             "PERSONAL_OUTPUT_ROOT_MISSING_OR_UNSAFE")
        # Legacy one-shot internal scope is signed only after both distinct
        # preexisting owner MACs and exact signed binding were checked.
        # Here source_rights_attested means OWNER ASSERTED, never external.
        opscope=build_scope(tech,root,out)
        fail(opscope["costs"]==policy["costs"],
             "PERSONAL_OPERATOR_COST_SCOPE_DRIFT")
        opscope["source_rights_attested"]=True
        native=json.loads((root/"core245-native-receipt.json").read_text("utf-8"))
        native_sha=native_receipt_check(opscope,native)
        details["core245_native_sha256"]=native_sha
        # These SHA references are not native proofs by themselves; worker
        # rechecks them on real data and stops if Core253 is incomplete.
        fail(native_sha==scope["core245_native_receipt_sha256"],
             "PERSONAL_CORE245_OWNER_SIGNED_PARENT_MISMATCH")
        fail(opscope["source_bytes_sha256"] == scope["source_bytes_sha256"],
             "PERSONAL_SOURCE_SIGNED_PARENT_DRIFT")
        key=_key(owner_key)
        owner_mac=hmac.new(key,canonical({
            "schema":OPERATOR_SCHEMA,"scope":opscope
        }),hashlib.sha256).hexdigest()
        legacy={"schema":OPERATOR_SCHEMA,"scope":opscope,
                "owner_approval_mac":owner_mac}
        verify_owner(legacy,owner_key)
        claim=root/"h2-personal-one-use-claim.json"
        fail(not claim.exists() and not claim.is_symlink(),
             "PERSONAL_ONE_RUN_ALREADY_CLAIMED")
        fd=os.open(claim,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as handle:
            json.dump({"schema":SCHEMA,"scope_sha256":_digest(scope),
                       "cost_sha256":_digest(policy),
                       "publisher_zip_sha256":proof["zip_bytes_sha256"],
                       "rights_status":"OWNER_ASSERTED_EXTERNAL_UNVERIFIED",
                       "state":"ONE_ATTEMPT_RESERVED_NO_AUTOREPLAY"},handle)
        invoked=True
        result=operator(legacy,key_file=owner_key,repo=git_repo,
                        allow_local_run=True)
        fail(sha_file(local)==proof["zip_bytes_sha256"],
             "PERSONAL_ORIGINAL_ZIP_CHANGED_DURING_RUN")
        details["operator_receipt_sha256"]=result["sha256"]
        details["operator_status"]=result["status"]
        fail(result["status"]=="EXPERIMENT_ENGINEERING_PASS",
             "PERSONAL_OPERATOR_"+result["reason"])
        for k in ("native_core245_sha256","bounded_core253_sha256",
                  "coverage","required_bars","observed_bars","missing_bars",
                  "scanner_sha256","factory_package_sha256","lab_sha256",
                  "secretary_sha256","replay","cost_policy_sha256",
                  "isolated_code_sha256","source_no_write_sha256"):
            if k in result:
                details[k]=result[k]
        return single_report("PASS_ENGINEERING_ONLY",[],
                             details=details,operator_invoked=True)
    except (Blocked, OSError, KeyError, TypeError, ValueError) as e:
        return single_report("BLOCKED",[
            str(e) if isinstance(e,Blocked)
            else "PERSONAL_EVIDENCE_OR_OPERATOR_UNVERIFIABLE"
        ],details=details,operator_invoked=invoked)


def main(argv=None):
    ap=argparse.ArgumentParser(description="H2 owner-personal research ONLY")
    ap.add_argument("--private-evidence-dir",required=True)
    ap.add_argument("--isolated-output-dir",required=True)
    ap.add_argument("--owner-signing-key")
    ap.add_argument("--pinned-git-repo")
    ap.add_argument("--confirm-one-run",action="store_true")
    args=ap.parse_args(argv)
    out=Path(args.isolated_output_dir)
    if (out/"h2-batch-summary.json").exists():
        print(json.dumps({"status":"BLOCKED","reasons":["REPORT_ALREADY_EXISTS"]}))
        return 2
    report=run_owner_personal_batch(
        args.private_evidence_dir,args.isolated_output_dir,
        owner_key=args.owner_signing_key,git_repo=args.pinned_git_repo,
        confirm_one_run=args.confirm_one_run)
    dest=write_report(args.isolated_output_dir,report)
    print(json.dumps({"status":report["status"],"reasons":report["reasons"],
                      "summary_filename":dest.name},sort_keys=True))
    return 0 if report["status"]=="PASS_ENGINEERING_ONLY" else 2


if __name__=="__main__":
    raise SystemExit(main())
