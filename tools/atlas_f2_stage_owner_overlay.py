"""Offline-only pinned overlay assembler used by owner PowerShell worktrees.

All writes are in a NEW isolated checkout. Never operate on a user's E:
diagnostic-runner, RawVault, Warehouse or Recovery originals. No merge.
"""
from __future__ import annotations
import argparse
from hashlib import sha1,sha256
import json
from pathlib import Path
from shutil import copyfile
import subprocess

from tools.atlas_e_combined_gate_manifest import PINS
from tools.atlas_f_research_diagnostic_operator import verify_pinned_modules

EXTRAS={
    "scanner_c":"1659713c80d1934f3c08af1af422b89cd5706360",
    "scanner_b":"30c37ae56851488b882998c7fa0085ec51dbfc92",
    "scanner227":"b9c9ff8602e79c534402f44bce83c56ec2fa6bb9",
    "raw_windows_lock":"e368dd491a0d80618bdc6c6e8f731a195d763dda",
}
EXACT={**PINS,**EXTRAS}
ORDER=(
    "core_f","scanner_f","discoverer_f","core_e","core_d",
    "scanner_e","scanner_d","scanner_c","scanner_b",
    "discoverer_e","discoverer_base","work235","raw211","scanner227",
)
AUTHORITATIVE={
    "core_f":(
        "research_wp_r0/aql_core_f_bulk_source_v1.py",
        "research_wp_r0/aql_core_f5_secretary_authority_v1.py",
        "research_wp_r0/aql_core_f_research_diagnostic_query_v1.py",
        "research_wp_r0/aql_core_f_recovery_readonly_v1.py",
        "research_wp_r0/aql_core_backbone_local_v1.py",
        "research_wp_r0/aql_core_dual_query_identity_map_v1.py",
    ),
    "scanner_f":(
        "tools/scanner_strategy_f/retrospective_policy.py",
        "tools/scanner_strategy_f/research_e2e_diagnostic.py",
        "tools/scanner_strategy_f/recovery_diagnostic_adapter.py",
        "tools/scanner_strategy_f/frozen_diagnostic_contracts.py",
    ),
    "factory_e":(
        "research_wp_r0/aql_factory_e_research_results_store_v1.py",
        "research_wp_r0/aql_factory_f_research_e2e_diagnostic_v1.py",
        "research_wp_r0/aql_factory_f_f2_recovery_diagnostic_v1.py",
        "research_wp_r0/aql_factory_historical_rule_projection.py",
        "research_wp_r0/strategy_definition.py",
    ),
    "scanner_e":(
        "tools/scanner_strategy_e/historical_policy_approval_request.py",
    ),
}


def need(ok,code):
    if not ok:
        raise ValueError("AQL_OWNER_STAGE_"+code)


def _gitsha(root):
    return subprocess.check_output(
        ["git","-C",str(root),"rev-parse","HEAD"],
        text=True,stderr=subprocess.DEVNULL).strip()


def _copy_checked(src,dst):
    need(src.is_file() and not src.is_symlink(),"SOURCE_MODULE")
    need(not dst.is_symlink(),"DEST_SYMLINK")
    dst.parent.mkdir(parents=True,exist_ok=True)
    copyfile(src,dst)
    need(sha256(src.read_bytes()).digest()==sha256(dst.read_bytes()).digest(),
         "MODULE_BYTES_DRIFT")


def stage(root):
    root=Path(root).absolute()
    target=root/"operator"
    need(target.is_dir() and not target.is_symlink(),
         "NEW_ISOLATED_OPERATOR_WORKTREE")
    for key,sha in EXACT.items():
        path=root/("_pinned_"+key)
        need(path.is_dir() and not path.is_symlink() and
             _gitsha(path)==sha,"OWNER_HEAD_PIN_"+key.upper())
    # Repo tree is pinned separately by owner PowerShell to exact Integration.
    for key in ORDER:
        owner=root/("_pinned_"+key)
        for folder in ("research_wp_r0","tools","src"):
            source=owner/folder
            if not source.is_dir():
                continue
            for src in source.rglob("*.py"):
                dest=target/folder/src.relative_to(source)
                if not dest.exists():
                    _copy_checked(src,dest)
    for key,names in AUTHORITATIVE.items():
        for relative in names:
            _copy_checked(root/("_pinned_"+key)/relative,target/relative)
    # Factory owns its entire F recovery modules and their dependencies.
    fac=root/"_pinned_factory_e"/"research_wp_r0"
    for name in (
        "aql_factory_e_research_results_store_v1.py",
        "aql_factory_e_discoverer_consumer_v1.py",
        "aql_factory_e_historical_source_boundary_v1.py",
        "aql_factory_e_core_scanner_historical_wait_v1.py",
        "aql_factory_e_durable_discoverer_consumer_v1.py",
        "aql_factory_f_batch_ledger_v1.py",
        "aql_factory_f_scanner_bulk_consumer_v1.py",
        "aql_factory_f_private_original_cohort_v1.py",
        "aql_factory_f_role_authority_v1.py",
        "aql_factory_f_research_e2e_diagnostic_v1.py",
        "aql_factory_f_f2_recovery_diagnostic_v1.py",
        "aql_factory_f_f2_recovery_research_v2.py",
    ):
        _copy_checked(fac/name,target/"research_wp_r0"/name)
    base=root/"_pinned_raw211"/"tools/raw_vault_offline"
    fixed=root/"_pinned_raw_windows_lock"/"tools/raw_vault_offline"
    for name in ("__init__.py","schema.py"):
        need((base/name).read_bytes()==(fixed/name).read_bytes(),
             "RAW_VAULT_PACKAGE_DRIFT")
    # Verify exact Git blob bytes, not a Windows checkout's text-filtered
    # working copy. A CRLF-converted checkout is NOT a valid raw-byte pin.
    v=fixed/"vault.py"
    original=subprocess.check_output([
        "git","-C",str(fixed),"cat-file","blob",
        "6b5bcc1d684088934f5ed7110064380b8d2bc0cd"])
    blob=sha1(b"blob "+str(len(original)).encode()+b"\0"+
              original).hexdigest()
    need(blob=="6b5bcc1d684088934f5ed7110064380b8d2bc0cd",
         "RAW_VAULT_WINDOWS_FIX_GIT_BLOB")
    for name in ("__init__.py","schema.py"):
        _copy_checked(fixed/name,target/"tools/raw_vault_offline"/name)
    dst=target/"tools/raw_vault_offline/vault.py"
    need(not dst.is_symlink(),"DEST_SYMLINK")
    dst.parent.mkdir(parents=True,exist_ok=True)
    dst.write_bytes(original)
    need(dst.read_bytes()==original,"RAW_VAULT_WINDOWS_FIX_BYTES")
    src=root/"_pinned_work235"/(
        "tools/strategy_service_offline/fixtures/strategies.json")
    dst=target/"tools/strategy_service_offline/fixtures/strategies.json"
    _copy_checked(src,dst)
    fixture_blob=sha1(b"blob "+str(src.stat().st_size).encode()+b"\0"+
                      src.read_bytes()).hexdigest()
    need(fixture_blob=="c27eb5aa70a6d671791ba1e55e9b078a272b611f",
         "FROZEN_WORK235_FIXTURE_BLOB")
    # The original F2 operator's three unchanged owner modules still have
    # frozen Git-blob pins; this check refuses silent overlay shadowing.
    pins=verify_pinned_modules()
    need(len(pins)==3,"HISTORICAL_F2_OPERATOR_MODULE_BLOBS")
    for name in ("atlas_f2_owner_provenance_v1.py",
                 "atlas_f2_owner_factory_packet_v1.py",
                 "atlas_f2_owner_execute.py",
                 "atlas_f2_recovery_research_operator.py"):
        need((target/"tools"/name).is_file(),
             "INTEGRATION_OPERATOR_FILE_MISSING")
    return {"status":"PINNED_ISOLATED_OVERLAY_ASSEMBLED",
            "owner_heads_verified":len(EXACT),
            "original_f2_reconstructed":False,
            "trading_authority":"NONE"}


def _bounded_stage_code(exc):
    # Never print exception text, private paths or source bytes.
    message=str(exc)
    if message.startswith("AQL_OWNER_STAGE_"):
        return message
    if message.startswith("AQL_DIAG_"):
        return "PINNED_F2_OPERATOR_MODULE_SHA_MISMATCH"
    if isinstance(exc, (ImportError, ModuleNotFoundError)):
        return "PINNED_OVERLAY_MODULE_IMPORT_MISSING"
    if isinstance(exc, FileNotFoundError):
        return "PINNED_OVERLAY_REQUIRED_MODULE_MISSING"
    return "PINNED_OVERLAY_ASSEMBLY_FAILED"


def main():
    a=argparse.ArgumentParser()
    a.add_argument("--root",required=True)
    args=a.parse_args()
    try:
        print(json.dumps(stage(args.root),sort_keys=True))
    except Exception as exc:
        print(json.dumps({"status":"PRIVATE_WAIT",
                          "code":_bounded_stage_code(exc),
                          "trading_authority":"NONE"},sort_keys=True))
        raise SystemExit(2)


if __name__=="__main__":
    main()
