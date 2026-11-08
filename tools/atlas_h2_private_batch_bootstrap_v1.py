"""H2 owner-local single-batch intake; never scans original source to find authority.

All metadata is derived from an independently MAC-authenticated, already
provisioned private custody packet. If missing: one sanitized BLOCKED report.
No operator-self-generated right, issuer PIT proof, strategy or owner key.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import sys

from tools.atlas_h2_owner_local_one_shot_v1 import (
    SCHEMA, PINS, OWNER_LIMITED_COSTS, canonical, digest, sha_file,
    verify_owner, execute, contained,
)

INTAKE_SCHEMA = "aql.integration.h2.private-custody-intake.v1"
REPORT_SCHEMA = "aql.integration.h2.private-batch-report.v1"
INTAKE_FIELDS = {
    "schema", "owner_authorization_ref", "one_time_scope_authorized",
    "custodian_rights_asserted", "rights_evidence_file_sha256",
    "warehouse_root", "vault_root", "dataset_id", "version", "month",
    "start_ms", "end_exclusive_ms", "decision_cutoff_ms",
    "source_bytes_sha256", "manifest_integrity_sha256",
    "native_receipt_file_sha256", "strategy_file_sha256",
    "strategy_definition_sha256", "strategy_id",
    "factory_code_sha256", "experiment_id",
}
REQUIRED = {
    "custody-intake.json", "custody-intake.mac", "rights-evidence.bin",
    "core245-native-receipt.json", "manual-third-ast.json",
}


class Blocked(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise Blocked(reason)


def single_report(status, reasons, *, code_head=None, details=None,
                  operator_invoked=False):
    payload = {
        "schema": REPORT_SCHEMA, "status": status,
        "reasons": sorted(set(reasons)),
        "code_head": code_head,
        # An operator may have begun a read before it blocks. Never report
        # false NO_SOURCE_IO for a failed invocation that passed prior gates.
        "source_read": (True if status == "PASS_ENGINEERING_ONLY"
                        else None if operator_invoked else False),
        "source_read_status": ("CONFIRMED" if status == "PASS_ENGINEERING_ONLY"
                               else "POSSIBLE_AFTER_GATES" if operator_invoked
                               else "NOT_ATTEMPTED"),
        "historical_pit": "NOT_ATTESTED",
        "economic_approval": "NOT_GRANTED",
        "trading_authority": "NONE",
        "f5": "BLOCKED_EXTERNAL_INPUT",
        "holdout": "SEALED_UNOPENED",
        "details": details or {},
    }
    return {**payload, "sha256": digest(payload)}


def _key(path):
    require(path is not None, "INDEPENDENT_CUSTODIAN_VERIFIER_KEY_REQUIRED")
    p = Path(path).resolve(strict=True)
    require(p.is_file() and not p.is_symlink()
            and 32 <= p.stat().st_size <= 4096,
            "INVALID_INDEPENDENT_CUSTODIAN_KEY")
    return p.read_bytes()


def inspect_private_intake(directory, trusted_key):
    """Only explicitly selected intake directory is accessed, not E:/source."""
    path = Path(directory).resolve(strict=True)
    require(path.is_dir() and not path.is_symlink(),
            "PRIVATE_INTAKE_DIRECTORY_MISSING")
    absent = sorted(x for x in REQUIRED if not (path / x).is_file())
    require(not absent, "MISSING_PRIVATE_EVIDENCE:" + ",".join(absent))
    key = _key(trusted_key)
    data = (path / "custody-intake.json").read_bytes()
    require(len(data) <= 100_000, "INTAKE_TOO_LARGE")
    mac = (path / "custody-intake.mac").read_text("ascii").strip()
    actual = hmac.new(key, data, hashlib.sha256).hexdigest()
    require(len(mac) == 64 and hmac.compare_digest(mac, actual),
            "CUSTODIAN_SIGNATURE_UNVERIFIED")
    try:
        claim = json.loads(data)
    except (UnicodeError, ValueError):
        raise Blocked("CUSTODY_INTAKE_INVALID_JSON") from None
    require(type(claim) is dict and set(claim) == INTAKE_FIELDS
            and claim["schema"] == INTAKE_SCHEMA,
            "CUSTODY_INTAKE_FIELDS_INVALID")
    require(claim["owner_authorization_ref"] == "#205/6718325330"
            and claim["one_time_scope_authorized"] is True
            and claim["custodian_rights_asserted"] is True,
            "SIGNED_CUSTODY_RIGHTS_OR_OWNER_SCOPE_NOT_ESTABLISHED")
    expected = {
        "rights-evidence.bin": "rights_evidence_file_sha256",
        "core245-native-receipt.json": "native_receipt_file_sha256",
        "manual-third-ast.json": "strategy_file_sha256",
    }
    for name, column in expected.items():
        require(type(claim[column]) is str
                and len(claim[column]) == 64
                and sha_file(path / name) == claim[column],
                "SIGNED_EVIDENCE_FILE_SHA_DRIFT:" + name)
    require(type(claim["dataset_id"]) is str
            and claim["dataset_id"].startswith("BINANCE-SPOT-BTCUSDT-15M-"),
            "SIGNED_DATASET_ID_INVALID")
    for name in ("source_bytes_sha256", "manifest_integrity_sha256",
                 "strategy_definition_sha256", "factory_code_sha256"):
        value = claim[name]
        require(type(value) is str and len(value) == 64
                and all(ch in "0123456789abcdef" for ch in value),
                "SIGNED_SHA_INVALID:" + name)
    start = claim["start_ms"]
    end = claim["end_exclusive_ms"]
    cutoff = claim["decision_cutoff_ms"]
    require(all(type(n) is int for n in (start, end, cutoff))
            and start >= 0 and 0 < end-start <= 4096 * 900000
            and start % 900000 == 0 and end % 900000 == 0
            and end <= cutoff,
            "SIGNED_15M_BOUNDS_INVALID")
    require(type(claim["month"]) is str
            and datetime.fromtimestamp(start/1000, timezone.utc).strftime("%Y-%m")
                == claim["month"]
            and datetime.fromtimestamp((end-1)/1000, timezone.utc).strftime("%Y-%m")
                == claim["month"], "SIGNED_MONTH_INVALID")
    require(type(claim["version"]) is int and claim["version"] > 0
            and type(claim["strategy_id"]) is str
            and claim["strategy_id"] not in ("", "f2")
            and type(claim["experiment_id"]) is str
            and claim["experiment_id"].startswith("RESEARCH-H-GENERIC-"),
            "SIGNED_VERSION_OR_STRATEGY_INVALID")
    return claim, path, actual


def build_scope(claim, directory, output):
    """No user-authored manifest. All source facts come from authenticated intake."""
    out = Path(output).absolute()
    required_outputs = ("results.sqlite", "secretary", "h2-audit.json")
    dest = [out / n for n in required_outputs]
    roots = [Path(claim[k]).absolute() for k in ("warehouse_root", "vault_root")]
    require(out.is_dir() and not out.is_symlink(),
            "FRESH_PRIVATE_OUTPUT_DIRECTORY_REQUIRED")
    require(not any(d.exists() or d.is_symlink() for d in dest),
            "SINGLE_USE_RESULTS_OR_AUDIT_ALREADY_EXISTS")
    require(not any(contained(out, r) or contained(r, out) for r in roots),
            "OUTPUT_OVERLAPS_SOURCE")
    require(not contained(out, directory)
            and not contained(directory, out),
            "OUTPUT_OVERLAPS_PRIVATE_INTAKE")
    scope = {
        "single_use": True, "explicit_readonly_no_export": True,
        "source_rights_attested": True,
        "research_class": "RETROSPECTIVE_NON_PIT",
        "publisher_pit_attested": False,
        "owner_cost_authorized": True,
        "exact_heads": PINS.copy(),
        "month": claim["month"], "start_ms": claim["start_ms"],
        "end_exclusive_ms": claim["end_exclusive_ms"],
        "decision_cutoff_ms": claim["decision_cutoff_ms"],
        "dataset_id": claim["dataset_id"], "version": claim["version"],
        "strategy_id": claim["strategy_id"],
        "strategy_definition_sha256": claim["strategy_definition_sha256"],
        "source_bytes_sha256": claim["source_bytes_sha256"],
        "manifest_integrity_sha256": claim["manifest_integrity_sha256"],
        "native_receipt_sha256": claim["native_receipt_file_sha256"],
        "native_receipt_file": str(directory / "core245-native-receipt.json"),
        "strategy_definition_file": str(directory / "manual-third-ast.json"),
        "warehouse_root": claim["warehouse_root"],
        "vault_root": claim["vault_root"],
        "results_sqlite": str(dest[0]), "secretary_root": str(dest[1]),
        "evidence_json": str(dest[2]),
        "experiment_id": claim["experiment_id"],
        "factory_code_sha256": claim["factory_code_sha256"],
        "costs": OWNER_LIMITED_COSTS.copy(),
    }
    return scope


def run_batch(directory, verifier_key, owner_key, output, git_repo,
              confirm_one_run=False):
    """One result. Authenticated metadata before any source read or mutation."""
    reasons = []
    details = {}
    try:
        claim, intake_path, intake_digest = inspect_private_intake(
            directory, verifier_key)
        details["custodian_packet_sha256"] = intake_digest
        require(confirm_one_run is True, "EXPLICIT_ONE_TIME_LOCAL_CONFIRMATION_REQUIRED")
        require(owner_key is not None, "INDEPENDENT_OWNER_HMAC_KEY_REQUIRED")
        owner_secret = _key(owner_key)
        scope = build_scope(claim, intake_path, output)
        require(Path(owner_key).resolve() != Path(verifier_key).resolve(),
                "OWNER_SIGNING_KEY_MUST_BE_DISTINCT_FROM_CUSTODIAN_KEY")
        require(not contained(owner_key, scope["warehouse_root"])
                and not contained(owner_key, scope["vault_root"])
                and not contained(owner_key, git_repo),
                "PRIVATE_KEY_NOT_ISOLATED")
        mac = hmac.new(
            owner_secret, canonical({"schema": SCHEMA, "scope": scope}),
            hashlib.sha256).hexdigest()
        signed = {"schema": SCHEMA, "scope": scope, "owner_approval_mac": mac}
        # This is a local ceremony using an externally provisioned owner's key:
        # it does not authenticate legal rights beyond the signed custodian intake.
        verify_owner(signed, owner_key)
        output_dir = Path(output)
        # Reserve against the authenticated intake, not an arbitrary new
        # output directory, so changing output cannot silently rerun the
        # same one-time owner source-use authorization.
        claim_file = intake_path / "h2-single-use-claim.json"
        require(not claim_file.exists(), "SINGLE_USE_ALREADY_CLAIMED")
        # Reserve one invocation even if downstream source gate fails.
        fd = os.open(claim_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"authorization_digest": digest(scope),
                       "custodian_packet_sha256": intake_digest,
                       "state": "ONE_ATTEMPT_RESERVED_NO_AUTOMATIC_REPLAY"}, stream)
        operator_result = execute(
            signed, key_file=owner_key, repo=git_repo,
            allow_local_run=True)
        details["operator_receipt_sha256"] = operator_result["sha256"]
        details["operator_status"] = operator_result["status"]
        if operator_result["status"] != "EXPERIMENT_ENGINEERING_PASS":
            reasons.append("OPERATOR_" + operator_result["reason"])
            return single_report("BLOCKED", reasons, details=details,
                                 operator_invoked=True)
        # Avoid publishing any source paths, key material or source rows.
        for k in ("native_core245_sha256", "bounded_core253_sha256",
                  "coverage", "required_bars", "observed_bars", "missing_bars",
                  "scanner_sha256", "factory_package_sha256", "lab_sha256",
                  "secretary_sha256", "replay", "cost_policy_sha256",
                  "isolated_code_sha256", "source_no_write_sha256"):
            if k in operator_result:
                details[k] = operator_result[k]
        return single_report("PASS_ENGINEERING_ONLY", [], details=details)
    except (Blocked, OSError, ValueError, KeyError, TypeError) as exc:
        reasons.append(str(exc) if isinstance(exc, Blocked)
                       else "PRIVATE_BOOTSTRAP_INPUT_OR_PATH_UNVERIFIABLE")
        return single_report("BLOCKED", reasons, details=details)


def write_report(output, report):
    path = Path(output)
    # This is the one sanitized external report, never an owner-private input.
    path.mkdir(parents=True, exist_ok=True)
    final = path / "h2-batch-summary.json"
    if final.exists():
        raise Blocked("BATCH_SUMMARY_ALREADY_EXISTS_NO_REPLAY")
    with final.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return final


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--private-evidence-dir", required=True)
    p.add_argument("--trusted-custodian-key")
    p.add_argument("--owner-signing-key")
    p.add_argument("--isolated-output-dir", required=True)
    p.add_argument("--pinned-git-repo", required=True)
    p.add_argument("--confirm-one-run", action="store_true")
    args = p.parse_args(argv)
    existing = Path(args.isolated_output_dir) / "h2-batch-summary.json"
    if existing.exists():
        print(json.dumps({"status": "BLOCKED",
                          "reasons": ["BATCH_SUMMARY_ALREADY_EXISTS_NO_REPLAY"],
                          "summary_filename": existing.name}, sort_keys=True))
        return 2
    result = run_batch(
        args.private_evidence_dir, args.trusted_custodian_key,
        args.owner_signing_key, args.isolated_output_dir,
        args.pinned_git_repo, args.confirm_one_run)
    target = write_report(args.isolated_output_dir, result)
    print(json.dumps({"status": result["status"], "reasons": result["reasons"],
                      "summary_filename": target.name}, sort_keys=True))
    return 0 if result["status"] == "PASS_ENGINEERING_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
