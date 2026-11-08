"""H2 owner P0 exhaustive NON-CONSUMING multi-finding diagnostic.

No H2 original execution, one-shot claim, owner key creation, source/evidence
mutation, nor writes under the signed output. Each result has a stable ID and
explicit dependency status. Publisher and original Core reads are *optional*
within the already approved owner read-only readiness scope.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

from tools.atlas_h2_binance_public_lane_v1 import (
    TECH_FIELDS, LANE_SCHEMA, validate_native_manual_third_ast,
    verify_public_month, fetch_official,
)
from tools.atlas_h2_owner_identity_v2 import (
    ENVELOPE_SCHEMA, inspect_forward_owner_assertion,
)
from tools.atlas_h2_owner_local_one_shot_v1 import (
    sha_file, native_receipt_check, fingerprint, boundaries,
    verified_local_sqlite_snapshot,
)
from tools.atlas_h2_owner_personal_batch_v1 import scope_commitment
from tools.atlas_h2_owner_readiness_v2 import (
    verify_signed_parent, verify_overlay,
)
from tools.atlas_h2_owner_evidence_recovery_v2 import _real_core_dual
from tools.atlas_h2_private_batch_bootstrap_v1 import build_scope

SCHEMA="H2_PREFLIGHT_FINDINGS"
VERSION="aql.integration.h2.preflight-multifinding.v1"
FILES=("technical-intake.json","owner-personal-assertion.json",
       "core245-native-receipt.json","manual-third-ast.json")
STATES=("PASS","FAIL","BLOCKED_BY_DEPENDENCY",
        "NOT_RUN_REQUIRES_ORIGINAL_EXECUTION")
LIMITS={
    "technical-intake.json":250_000,
    "owner-personal-assertion.json":250_000,
    "core245-native-receipt.json":4*1024*1024,
    "manual-third-ast.json":250_000,
}
RESEARCH_COSTS={
    "fee_entry_bps":"10","fee_exit_bps":"10",
    "spread_entry_bps":"2","spread_exit_bps":"2",
    "slippage_entry_bps":"3","slippage_exit_bps":"3",
    "funding_bps_per_bar":"0",
}
SECTIONS=("EVIDENCE","OWNER","SOURCE","SCANNER","FACTORY",
          "OVERLAY","OUTPUT","AUTHORITY")
OWNERS={"EVIDENCE":"Integration","OWNER":"Integration",
        "SOURCE":"Core","SCANNER":"Scanner","FACTORY":"Factory",
        "OVERLAY":"Integration","OUTPUT":"Integration",
        "AUTHORITY":"PM"}
REPARSE=0x400

def _is_link(path,ls=None):
    p=Path(path)
    s=ls if ls is not None else p.lstat()
    return (stat.S_ISLNK(s.st_mode) or
            bool(getattr(s,"st_file_attributes",0) & REPARSE))

def _code(exc):
    # Never serialize exceptions that may carry private paths, content, URLs,
    # strategy parameters, HMAC or keys. Stable type only unless our own ID.
    return type(exc).__name__

class Findings:
    def __init__(self):
        self.entries=[]
        self.states={}
    def add(self,ident,section,state,reason=None,dependencies=(),
            evidence=None,regression=None,severity="P0"):
        if ident in self.states: raise ValueError("DUPLICATE_FINDING_ID")
        assert state in STATES and section in SECTIONS
        self.states[ident]=state
        data={"id":ident,"section":section,"owner":OWNERS[section],
              "severity":severity,"status":state,
              "dependencies":list(dependencies),
              "reason":reason or ("OK" if state=="PASS" else "UNVERIFIED"),
              "regression_test":regression or "test_h2_preflight_"+ident.lower()}
        if evidence is not None: data["evidence"]=evidence
        self.entries.append(data)
        return state=="PASS"
    def blocked(self,ident,section,deps,reason="UPSTREAM_NOT_VERIFIED"):
        return self.add(ident,section,"BLOCKED_BY_DEPENDENCY",reason,deps)
    def safe(self,ident,section,deps,func,reason="CONTRACT_OR_PROOF_INVALID",
             regression=None):
        if any(self.states.get(d)!="PASS" for d in deps):
            return self.blocked(ident,section,deps)
        try:
            value=func()
            if value is False: raise ValueError("INVARIANT_FALSE")
        except Exception as exc:
            self.add(ident,section,"FAIL",reason+":"+_code(exc),
                     deps,regression=regression)
            return False
        self.add(ident,section,"PASS",dependencies=deps,
                 regression=regression)
        return True
    def summary(self):
        counter=Counter(x["status"] for x in self.entries)
        ready=(counter["FAIL"]==0 and counter["BLOCKED_BY_DEPENDENCY"]==0)
        return {"schema":SCHEMA,"version":VERSION,
                "status":("READY_FOR_SEPARATE_OWNER_EXECUTION_APPROVAL"
                          if ready else "PREFLIGHT_FINDINGS_BLOCKED"),
                "counts":{k:counter[k] for k in STATES},
                "mandatory_ready":ready,
                "original_h2_executed":False,
                "one_use_claim_created":False,
                "independent_rights":"NOT_ATTESTED",
                "historical_pit":"NOT_ATTESTED",
                "g0_approved":False,
                "findings":self.entries}

def inspect_four(folder,findings):
    """All four independent lstat/size/shape findings, even on mixed failures."""
    root=Path(folder)
    payload={}
    if findings.safe("EVIDENCE_DIR","EVIDENCE",(),
        lambda:root.is_dir() and not root.is_symlink(),
        "EVIDENCE_DIRECTORY_MISSING_OR_LINK"):
        pass
    for name in FILES:
        ident="FILE_"+name.upper().replace("-","_").replace(".","_")
        path=root/name
        if findings.states["EVIDENCE_DIR"]!="PASS":
            findings.blocked(ident,"EVIDENCE",("EVIDENCE_DIR",))
            continue
        try:
            st=path.lstat()
            is_file=stat.S_ISREG(st.st_mode)
            linked=_is_link(path,st)
            limit=LIMITS[name]
            evidence={"basename":name,"byte_count":st.st_size,
                      "symlink_or_reparse":linked,
                      "limit_bytes":limit}
            reason=("UNSAFE_LINK_OR_REPARSE" if linked else
                    "NOT_REGULAR_FILE" if not is_file else
                    "EMPTY_FILE" if not st.st_size else
                    "OVERSIZE" if st.st_size>limit else "OK")
            ok=(reason=="OK")
            findings.add(ident,"EVIDENCE","PASS" if ok else "FAIL",
                         reason,evidence=evidence,
                         regression="test_four_file_boundary_and_reparse")
            if ok:
                with path.open("rb") as f:
                    raw=f.read(limit+1)
                if len(raw)>limit:
                    raise ValueError("CHANGED_DURING_BOUNDED_READ")
                payload[name]=json.loads(raw.decode("utf-8"))
        except FileNotFoundError:
            findings.add(ident,"EVIDENCE","FAIL","MISSING",
                         evidence={"basename":name,"byte_count":None,
                                   "symlink_or_reparse":False,
                                   "limit_bytes":LIMITS[name]},
                         regression="test_missing_one_of_four")
        except (ValueError,UnicodeError,OSError,TypeError) as exc:
            # File guard already PASS but JSON might be malformed: distinct ID.
            if ident not in findings.states:
                findings.add(ident,"EVIDENCE","FAIL","UNREADABLE_OR_UNSAFE_TYPE")
            payload.pop(name,None)
        jsonid="JSON_"+name.upper().replace("-","_").replace(".","_")
        dep=(ident,)
        if findings.states.get(ident)!="PASS":
            findings.blocked(jsonid,"EVIDENCE",dep)
        else:
            valid=type(payload.get(name)) is dict
            findings.add(jsonid,"EVIDENCE","PASS" if valid else "FAIL",
                         "OK" if valid else "INVALID_JSON_OR_NON_OBJECT",dep,
                         regression="test_bounded_safe_json_shape")
    return payload

def diagnose(evidence_dir,signed_output_dir,owner_key,repo,
             *, publisher=verify_public_month,fetcher=fetch_official,
             core_query=_real_core_dual,overlay_check=verify_overlay,
             include_original_read=True, scratch_root=None):
    """Never write to original/source/signed root. No user secret returned."""
    F=Findings()
    folder=Path(evidence_dir)
    out=Path(signed_output_dir)
    data=inspect_four(folder,F)
    tech=data.get("technical-intake.json")
    env=data.get("owner-personal-assertion.json")
    native=data.get("core245-native-receipt.json")
    ast=data.get("manual-third-ast.json")
    signed=None;claim=None;scope=None;proof=None;source=None;roots=None
    techdeps=("JSON_TECHNICAL_INTAKE_JSON",)
    envdeps=("JSON_OWNER_PERSONAL_ASSERTION_JSON",)
    natdeps=("JSON_CORE245_NATIVE_RECEIPT_JSON",)
    astdeps=("JSON_MANUAL_THIRD_AST_JSON",)
    F.safe("TECH_SCHEMA","EVIDENCE",techdeps,
           lambda:type(tech) is dict and set(tech)==TECH_FIELDS
           and tech.get("schema")==LANE_SCHEMA
           and tech.get("owner_authorization_ref")=="#271/6720832849",
           "TECHNICAL_INTAKE_SCHEMA_OR_OWNER_REF")
    F.safe("OWNER_KEY_FILE","OWNER",(),
           lambda:Path(owner_key).is_file()
           and not _is_link(owner_key)
           and 32<=Path(owner_key).stat().st_size<=4096,
           "OWNER_KEY_MISSING_OR_LINK")
    rev=Path(owner_key).parent/"owner-revocations.json"
    F.safe("OWNER_REVOCATIONS","OWNER",(),
           lambda:rev.is_file() and not _is_link(rev)
           and type(json.loads(rev.read_text("utf-8"))) is dict,
           "REVOCATION_REGISTRY_MISSING_OR_UNSAFE")
    F.safe("OWNER_V2_ENVELOPE","OWNER",envdeps,
           lambda:env.get("schema")==ENVELOPE_SCHEMA
           and type(env.get("identity")) is dict
           and type(env.get("assertion")) is dict,
           "OWNER_FORWARD_ONLY_ENVELOPE_INVALID")
    if all(F.states.get(i)=="PASS" for i in (
        "OWNER_KEY_FILE","OWNER_REVOCATIONS","OWNER_V2_ENVELOPE")):
        try:
            signed=inspect_forward_owner_assertion(
                env,owner_key_file=owner_key,
                revocation_registry=json.loads(rev.read_text("utf-8")))
            F.add("OWNER_MAC_TIME_CUSTODY","OWNER","PASS",
                  regression="test_owner_scope_cost_hmac_and_forward_time")
        except Exception as exc:
            F.add("OWNER_MAC_TIME_CUSTODY","OWNER","FAIL",
                  "OWNER_MAC_IDENTITY_OR_TIME:"+_code(exc),
                  regression="test_owner_scope_cost_hmac_and_forward_time")
    else:
        F.blocked("OWNER_MAC_TIME_CUSTODY","OWNER",
                  ("OWNER_KEY_FILE","OWNER_REVOCATIONS","OWNER_V2_ENVELOPE"))
    F.safe("SIGNED_OUTPUT_DIR","OUTPUT",(),
           lambda:out.is_dir() and not _is_link(out),
           "SIGNED_OUTPUT_MISSING_OR_REPARSE")
    F.safe("SIGNED_EXACT_ROOT","OWNER",
           ("OWNER_MAC_TIME_CUSTODY","TECH_SCHEMA","SIGNED_OUTPUT_DIR"),
           lambda:env["assertion"]["scope"]["owner_authorization_ref"]==
              scope_commitment(tech,out,identity_binding=
                 signed["identity_binding_sha256"]),
           "SIGNED_ROOT_OR_ROLE_PIN_MISMATCH")
    if F.states["OWNER_MAC_TIME_CUSTODY"]=="PASS":
        claim=env["assertion"]["scope"]
        F.safe("OWNER_TEST_COSTS","OWNER",("OWNER_MAC_TIME_CUSTODY",),
               lambda:env["assertion"]["cost_policy"]["costs"]==
                      RESEARCH_COSTS,
               "SEVEN_TEST_ONLY_SPOT_COSTS_DRIFT")
        F.safe("SIGNED_NONCE","OWNER",("OWNER_MAC_TIME_CUSTODY",),
               lambda:type(claim["one_use_nonce"]) is str
               and len(claim["one_use_nonce"])==32
               and all(x in "0123456789abcdef" for x in claim["one_use_nonce"]),
               "ONE_USE_NONCE_SHAPE")
        F.safe("NO_TRADING_AUTHORITY","AUTHORITY",("OWNER_MAC_TIME_CUSTODY",),
               lambda:signed["original_h2_execution_permitted"] is False
               and claim["historical_pit"]=="NOT_ATTESTED"
               and claim["research_class"]=="RETROSPECTIVE_NON_PIT"
               and env["assertion"]["independent_license_review_status"]==
                  "NOT_ATTESTED",
               "RESEARCH_ONLY_AUTHORITY_DRIFT")
    else:
        for id,area in [("OWNER_TEST_COSTS","OWNER"),
                        ("SIGNED_NONCE","OWNER"),
                        ("NO_TRADING_AUTHORITY","AUTHORITY")]:
            F.blocked(id,area,("OWNER_MAC_TIME_CUSTODY",))
    for id,path in (
        ("NO_EVIDENCE_ONE_USE",folder/"h2-personal-one-use-claim.json"),
        ("NO_SIGNED_OUTPUT_ONE_USE",out/"h2-personal-scope-claim.json"),
        ("PRIOR_READINESS_REPORT_PRESERVED",out/"h2-readiness-summary.json"),
    ):
        if id=="PRIOR_READINESS_REPORT_PRESERVED":
            F.safe(id,"OUTPUT",("SIGNED_OUTPUT_DIR",),
                   lambda:path.is_file() and not _is_link(path),
                   "PREVIOUS_BLOCKED_REPORT_ABSENT_OR_UNSAFE",
                   regression="test_no_overwrite_existing_readiness")
        else:
            deps=("SIGNED_OUTPUT_DIR",) if id=="NO_SIGNED_OUTPUT_ONE_USE" else ()
            F.safe(id,"OUTPUT",deps,
                   lambda:not path.exists() and not path.is_symlink(),
                   "ONE_USE_ALREADY_CONSUMED",
                   regression="test_no_one_use_claim")
    F.safe("NATIVE_FILE_SHA","EVIDENCE",("TECH_SCHEMA",)+natdeps,
           lambda:sha_file(folder/"core245-native-receipt.json")==
             tech["native_receipt_file_sha256"],
           "CORE245_RECEIPT_FILE_SHA_CHANGED")
    F.safe("AST_FILE_SHA","EVIDENCE",("TECH_SCHEMA",)+astdeps,
           lambda:sha_file(folder/"manual-third-ast.json")==
             tech["strategy_file_sha256"],
           "NATIVE_AST_FILE_SHA_CHANGED")
    F.safe("AST_NATIVE_SHAPE_AND_DIGEST","SCANNER",
           ("TECH_SCHEMA","AST_FILE_SHA"),
           lambda:validate_native_manual_third_ast(
               folder/"manual-third-ast.json",
               tech["strategy_definition_sha256"],tech["strategy_id"]) == tech["strategy_definition_sha256"],
           "MANUAL_NATIVE_AST_DIGEST_OR_SHAPE",
           regression="test_native_ast_not_scanner_plugin")
    F.safe("CORE245_SCHEMA_SEAL","SOURCE",("NATIVE_FILE_SHA","TECH_SCHEMA"),
           lambda:type(native)==dict and native.get("schema")==
             "aql.core.historical-price-custody-query.v1"
             and native.get("status")=="OK"
             and native.get("coverage")=="COMPLETE"
             and native.get("source_bytes_sha256")==tech["source_bytes_sha256"]
             and native.get("manifest_integrity_sha256")==
                 tech["manifest_integrity_sha256"],
           "NATIVE_CORE245_SCHEMA_OR_PARENTS")
    F.safe("SOURCE_CODE_REPO","OVERLAY",(),
           lambda:Path(repo).is_dir() and not _is_link(repo),
           "PINNED_GIT_CODE_UNAVAILABLE")
    F.safe("SCANNER_MANUAL_EFFECTIVE","SCANNER",
           ("AST_NATIVE_SHAPE_AND_DIGEST","OWNER_MAC_TIME_CUSTODY"),
           lambda:_scanner_effective(ast,env),
           "SCANNER_MANUAL_CONFIG_OR_EVALUATOR_DRIFT",
           regression="test_scanner_frozen_manual_third")
    F.safe("FACTORY_CODE_IDENTITY","FACTORY",("TECH_SCHEMA",),
           lambda:_factory_sha(tech),
           "FACTORY_SOURCE_SHA_DRIFT")
    F.safe("OUTPUT_EXACT_SCOPE","OUTPUT",
           ("SIGNED_EXACT_ROOT","TECH_SCHEMA"),
           lambda:_bounded_scope(tech,folder,out,owner_key,repo),
           "OUTPUT_WAREHOUSE_VAULT_BOUNDARY")
    # Safe independent Git-stage / role import check proceeds despite
    # evidence problems. Requires no owner original source.
    if F.states["SOURCE_CODE_REPO"]=="PASS":
        try:
            with tempfile.TemporaryDirectory(
                prefix="aql-h2-diagnose-code-",
                dir=scratch_root) as tmp:
                result=overlay_check(repo,tmp)
            if not result.get("scanner_f3_import_seam_sha256"):
                raise ValueError("SCANNER_SEAM_NOT_PRESENT")
            F.add("EXECUTION_FIVE_ROLE_OVERLAY","OVERLAY","PASS",
                  regression="test_actual_execution_import_stage")
        except Exception as exc:
            F.add("EXECUTION_FIVE_ROLE_OVERLAY","OVERLAY","FAIL",
                  "PINNED_OVERLAY_OR_SCANNER_IMPORT:"+_code(exc),
                  regression="test_actual_execution_import_stage")
    else:
        F.blocked("EXECUTION_FIVE_ROLE_OVERLAY","OVERLAY",
                  ("SOURCE_CODE_REPO",))
    if not include_original_read:
        for id,area in (
            ("PUBLISHER_BYTE_IDENTITY","SOURCE"),
            ("ORIGINAL_ZIP_IDENTITY","SOURCE"),
            ("SOURCE_DURABLE_FINGERPRINT","SOURCE"),
            ("CORE253_DUAL_COMPLETE","SOURCE"),
        ):
            F.blocked(id,area,("READ_ONLY_SOURCE_OPT_IN",),
                      "OWNER_READ_ONLY_SOURCE_OPT_IN_NOT_PROVIDED")
    else:
        deps=("TECH_SCHEMA",)
        if F.states["TECH_SCHEMA"]=="PASS":
            try:
                proof=publisher(tech["month"],fetcher=fetcher)
                assert proof["zip_bytes_sha256"]==tech["source_bytes_sha256"]
                assert proof["bar_count"]==2976
                assert proof["first_open_ms"]==tech["start_ms"]
                assert proof["end_exclusive_ms"]==tech["end_exclusive_ms"]
                F.add("PUBLISHER_BYTE_IDENTITY","SOURCE","PASS",
                      regression="test_publisher_signed_zip_checksum")
            except Exception as exc:
                F.add("PUBLISHER_BYTE_IDENTITY","SOURCE","FAIL",
                      "OFFICIAL_PROVIDER_UNAVAILABLE_OR_SOURCE_SHA_DRIFT:"+_code(exc),
                      regression="test_publisher_signed_zip_checksum")
        else:
            F.blocked("PUBLISHER_BYTE_IDENTITY","SOURCE",deps)
        if F.states["PUBLISHER_BYTE_IDENTITY"]=="PASS":
            try:
                source=Path(tech["local_source_zip"])
                assert source.is_file() and not _is_link(source)
                assert sha_file(source)==proof["zip_bytes_sha256"]
                F.add("ORIGINAL_ZIP_IDENTITY","SOURCE","PASS",
                      regression="test_archive_bytes_publisher_match")
            except Exception as exc:
                F.add("ORIGINAL_ZIP_IDENTITY","SOURCE","FAIL",
                      "ORIGINAL_ZIP_SHA_MISMATCH_OR_UNSAFE:"+_code(exc))
        else:
            F.blocked("ORIGINAL_ZIP_IDENTITY","SOURCE",
                      ("PUBLISHER_BYTE_IDENTITY",))
        deps=("OUTPUT_EXACT_SCOPE","ORIGINAL_ZIP_IDENTITY")
        if all(F.states.get(x)=="PASS" for x in deps):
            try:
                scope=build_scope(tech,folder,out)
                roots, _=boundaries(scope,owner_key,repo)
                before=[fingerprint(root) for root in roots]
                F.add("SOURCE_DURABLE_FINGERPRINT","SOURCE","PASS",
                      regression="test_original_source_pre_post_no_write")
            except Exception as exc:
                F.add("SOURCE_DURABLE_FINGERPRINT","SOURCE","FAIL",
                      "QUESCENT_SOURCE_FINGERPRINT_UNAVAILABLE:"+_code(exc))
        else:
            F.blocked("SOURCE_DURABLE_FINGERPRINT","SOURCE",deps)
        deps=("SOURCE_DURABLE_FINGERPRINT","CORE245_SCHEMA_SEAL")
        if all(F.states.get(x)=="PASS" for x in deps):
            try:
                with tempfile.TemporaryDirectory(
                    prefix="aql-h2-diagnose-core-",
                    dir=scratch_root) as tmp:
                    snapshot=verified_local_sqlite_snapshot(roots[0],tmp)
                    native2,core253,dataset,version,manifest=core_query(
                        snapshot,proof["zip_bytes_sha256"])
                assert native2["price_query_sha256"]==native["price_query_sha256"]
                assert core253["query_sha256"]==claim["core253_query_sha256"]
                assert (dataset,version,manifest)==(
                    tech["dataset_id"],tech["version"],
                    tech["manifest_integrity_sha256"])
                F.add("CORE253_DUAL_COMPLETE","SOURCE","PASS",
                      regression="test_bounded_core_dual_receipts")
            except Exception as exc:
                F.add("CORE253_DUAL_COMPLETE","SOURCE","FAIL",
                      "CORE253_READONLY_DUAL_PROOF:"+_code(exc))
        else:
            F.blocked("CORE253_DUAL_COMPLETE","SOURCE",deps)
    if roots is not None and before is not None:
        try:
            if before!=[fingerprint(root) for root in roots]:
                F.add("SOURCE_POSTREAD_UNCHANGED","SOURCE","FAIL",
                      "SOURCE_MUTATED_DURING_DIAGNOSTIC")
            else:
                F.add("SOURCE_POSTREAD_UNCHANGED","SOURCE","PASS")
        except Exception as exc:
            F.add("SOURCE_POSTREAD_UNCHANGED","SOURCE","FAIL",
                  "SOURCE_POSTREAD_UNAVAILABLE:"+_code(exc))
    else:
        F.blocked("SOURCE_POSTREAD_UNCHANGED","SOURCE",
                  ("SOURCE_DURABLE_FINGERPRINT",))
    for item in ("ORIGINAL_H2_EXECUTION","G0_APPROVAL","TRADING_AUTHORITY"):
        F.add(item,"AUTHORITY","NOT_RUN_REQUIRES_ORIGINAL_EXECUTION",
              "EXPLICIT_SEPARATE_OWNER_APPROVAL_REQUIRED",severity="P1")
    return F.summary()

def _scanner_effective(ast,envelope):
    from research_wp_r0.strategy_definition import StrategyDefinition
    from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2
    from tools.scanner_strategy_f import research_strategy_plugin as scanner
    from tools.strategy_service_offline.common import Frozen
    definition=StrategyDefinition.from_dict(ast,registry=IndicatorRegistryV2())
    scope=envelope["assertion"]["scope"]
    digest=scanner.manual_config_digest(ast)
    plugin=scanner.register_strategy_plugin(
        ast,config_digest=digest,origin="MANUAL")
    return (definition.digest==scope["strategy_definition_sha256"]
            and digest==scope["strategy_config_sha256"]
            and Frozen.restore(plugin).data["evaluator_code_sha256"]==
                scope["evaluator_code_sha256"])

def _factory_sha(tech):
    from research_wp_r0 import aql_factory_h_generic_signal_adapter_v1 as mod
    return sha_file(mod.__file__)==tech["factory_code_sha256"]

def _bounded_scope(tech,folder,out,key,repo):
    scope=build_scope(tech,folder,out)
    boundaries(scope,key,repo)
    return True

def write_private_report(report, diagnostics_dir):
    """Exclusive new diagnostics-only folder; NEVER inside signed owner root."""
    directory=Path(diagnostics_dir)
    if directory.exists() or directory.is_symlink():
        raise FileExistsError("DIAGNOSTIC_ROOT_MUST_BE_FRESH")
    directory.mkdir(mode=0o700)
    with (directory/"h2-preflight-findings.json").open("x",encoding="utf-8") as f:
        json.dump(report,f,sort_keys=True,indent=2)
    return directory/"h2-preflight-findings.json"

def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument("--evidence-dir",required=True)
    ap.add_argument("--signed-output-dir",required=True)
    ap.add_argument("--owner-key",required=True)
    ap.add_argument("--repo",required=True)
    ap.add_argument("--diagnostics-dir",required=True)
    ap.add_argument("--without-original-read",action="store_true")
    args=ap.parse_args(argv)
    diag=Path(args.diagnostics_dir).resolve(strict=False)
    signed=Path(args.signed_output_dir).resolve(strict=False)
    base=Path(os.environ.get("LOCALAPPDATA",""))/"ATLAS"/"H2-Local-Batch"
    if (not os.environ.get("LOCALAPPDATA") or
        diag == signed or signed in diag.parents or
        diag == base or base not in diag.parents or
        diag.exists() or diag.is_symlink()):
        raise SystemExit("DIAGNOSTIC_OUTPUT_NOT_FRESH_OR_NOT_ISOLATED")
    report=diagnose(args.evidence_dir,args.signed_output_dir,
                    args.owner_key,args.repo,
                    include_original_read=not args.without_original_read,
                    scratch_root=diag.parent)
    write_private_report(report,args.diagnostics_dir)
    # Minimal user-console output: IDs and status only, no private path/JSON.
    print(json.dumps({
        "schema":SCHEMA,"status":report["status"],
        "counts":report["counts"],
        "findings":[{"id":x["id"],"status":x["status"],
                     "reason":x["reason"]} for x in report["findings"]
                    if x["status"]!="PASS"],
        "NO_ORIGINAL_H2":True,"NO_ONE_USE_CLAIM":True
    },sort_keys=True))
    return 0 if report["mandatory_ready"] else 2

if __name__=="__main__":
    raise SystemExit(main())
