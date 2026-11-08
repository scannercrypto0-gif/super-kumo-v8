"""Opt-in official Binance Vision archive provenance lane (research only).

Unlike the legacy custodian HMAC branch this version can independently verify
publisher-hosted ZIP/.CHECKSUM and bind them to a retained local ZIP *after*
documented license/owner permission. No publisher signature, PIT or legal
clearance is inferred from ZIP checksums, and no E: access occurs before gates.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import hmac
import io
import os
import json
from pathlib import Path
import re
import ssl
import urllib.error
import urllib.request
import zipfile

from tools.atlas_h2_private_batch_bootstrap_v1 import (
    Blocked, build_scope, single_report, write_report, _key,
)
from tools.atlas_h2_owner_local_one_shot_v1 import (
    SCHEMA, OWNER_LIMITED_COSTS, canonical, digest, execute, sha_file,
    contained, verify_owner,
)

LANE_SCHEMA = "aql.integration.h2.official-binance-archive-intake.v1"
LICENSE_SCHEMA = "aql.integration.h2.historical-license-evidence.v1"
ROOT = "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/15m/"
TERMS_URL = "https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md"
ZIP_MAX = 60 * 1024 * 1024
CHECKSUM_MAX = 1024
PATTERN = re.compile(r"^20\d\d-(0[1-9]|1[0-2])$")
SHA = re.compile(r"^[a-f0-9]{64}$")
TECH_FIELDS = {
    "schema", "owner_authorization_ref", "one_time_scope_authorized",
    "warehouse_root", "vault_root", "local_source_zip",
    "dataset_id", "version", "month", "start_ms", "end_exclusive_ms",
    "decision_cutoff_ms", "source_bytes_sha256",
    "manifest_integrity_sha256", "native_receipt_file_sha256",
    "strategy_file_sha256", "strategy_definition_sha256",
    "strategy_id", "factory_code_sha256", "experiment_id",
}
LIC_FIELDS = {
    "schema", "issuer", "terms_url", "terms_sha256",
    "applies_to_download_year", "download_year",
    "intended_use", "permitted_use", "status",
    "issued_at_utc", "signed_by", "signature_ref",
}
PUBLIC_REQUIRED = {
    "technical-intake.json", "historical-license-evidence.json",
    "historical-license-evidence.mac", "historical-terms.txt",
    "core245-native-receipt.json", "manual-third-ast.json",
}


def fail(condition, reason):
    if not condition:
        raise Blocked(reason)


def filename_for_month(month):
    fail(type(month) is str and PATTERN.fullmatch(month) is not None,
         "OFFICIAL_MONTH_FORMAT")
    return "BTCUSDT-15m-" + month + ".zip"


def checksum_parse(blob, filename):
    """Accept one Binance .CHECKSUM digest, bound to the precise ZIP basename."""
    fail(type(blob) is bytes and len(blob) <= CHECKSUM_MAX,
         "OFFICIAL_CHECKSUM_LENGTH")
    try:
        s = blob.decode("ascii").strip()
    except UnicodeError:
        raise Blocked("OFFICIAL_CHECKSUM_ENCODING") from None
    parts = s.split()
    fail(len(parts) == 2 and SHA.fullmatch(parts[0].lower()) is not None
         and parts[1].lstrip("*") == filename
         and "/" not in parts[1] and "\\" not in parts[1],
         "OFFICIAL_CHECKSUM_CONTENT_MISMATCH")
    return parts[0].lower()


def safe_zip(blob, filename, month):
    """Inspect public monthly kline CSV, reject ZIP bombs and wrong symbol."""
    fail(type(blob) is bytes and 0 < len(blob) <= ZIP_MAX,
         "OFFICIAL_ZIP_SIZE")
    member_name = filename[:-4] + ".csv"
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            contents = zf.infolist()
            fail(len(contents) == 1 and contents[0].filename == member_name
                 and not contents[0].is_dir()
                 and contents[0].file_size <= 200 * 1024 * 1024
                 and contents[0].compress_size <= ZIP_MAX
                 and contents[0].file_size <= max(1, contents[0].compress_size) * 100,
                 "OFFICIAL_ZIP_MEMBER_UNSAFE")
            # Full CSV content is intentionally not exposed to reports/logs.
            with zf.open(contents[0]) as stream:
                total = 0
                first = None
                last = None
                for raw in stream:
                    total += 1
                    fail(total <= 4096 and len(raw) <= 8192,
                         "OFFICIAL_KLINE_CSV_LIMIT")
                    row = raw.decode("ascii").strip().split(",")
                    fail(len(row) == 12, "OFFICIAL_KLINE_CSV_SHAPE")
                    try:
                        open_ms = int(row[0])
                    except ValueError:
                        raise Blocked("OFFICIAL_KLINE_TIME_INVALID") from None
                    if first is None:
                        first = open_ms
                    if last is not None:
                        fail(open_ms == last + 900000,
                             "OFFICIAL_KLINE_GAP_OR_DUPLICATE")
                    last = open_ms
                fail(total > 0, "OFFICIAL_KLINE_EMPTY")
    except (zipfile.BadZipFile, EOFError, UnicodeError, RuntimeError):
        raise Blocked("OFFICIAL_ZIP_INVALID") from None
    start = datetime.fromtimestamp(first/1000, timezone.utc)
    end = datetime.fromtimestamp(last/1000, timezone.utc)
    next_month = (datetime(start.year + 1, 1, 1, tzinfo=timezone.utc)
                  if start.month == 12 else
                  datetime(start.year, start.month + 1, 1, tzinfo=timezone.utc))
    fail(start.strftime("%Y-%m") == month and end.strftime("%Y-%m") == month
         and start.day == 1 and start.hour == 0 and start.minute == 0
         and first == int(start.timestamp() * 1000)
         and last + 900000 == int(next_month.timestamp() * 1000),
         "OFFICIAL_NOT_COMPLETE_CALENDAR_MONTH")
    return {"bar_count": total, "first_open_ms": first,
            "end_exclusive_ms": last + 900000}


def fetch_official(url, limit):
    """Fixed origin, HTTPS, no redirects to arbitrary third-party domains."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            raise Blocked("OFFICIAL_REDIRECT_REFUSED")
    fail(url.startswith(ROOT) and ".." not in url and
         (url.endswith(".zip") or url.endswith(".zip.CHECKSUM")),
         "OFFICIAL_URL_NOT_PINNED")
    opener = urllib.request.build_opener(
        NoRedirect(), urllib.request.HTTPSHandler(
            context=ssl.create_default_context()))
    try:
        with opener.open(urllib.request.Request(url, headers={
            "User-Agent": "ATLAS-H2-public-provenance/1.0",
            "Accept": "application/octet-stream",
        }), timeout=30) as res:
            fail(res.status == 200, "OFFICIAL_HTTP_STATUS")
            blob = res.read(limit + 1)
            fail(len(blob) <= limit, "OFFICIAL_DOWNLOAD_TOO_LARGE")
            return blob
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise Blocked("OFFICIAL_PROVIDER_UNAVAILABLE") from None


def verify_public_month(month, fetcher=fetch_official):
    name = filename_for_month(month)
    checksum_bytes = fetcher(ROOT + name + ".CHECKSUM", CHECKSUM_MAX)
    publisher_sha = checksum_parse(checksum_bytes, name)
    archive = fetcher(ROOT + name, ZIP_MAX)
    observed_sha = hashlib.sha256(archive).hexdigest()
    fail(hmac.compare_digest(publisher_sha, observed_sha),
         "OFFICIAL_ZIP_CHECKSUM_MISMATCH")
    grid = safe_zip(archive, name, month)
    return {
        "schema": "aql.integration.h2.official-public-archive-proof.v1",
        "publisher_host": "data.binance.vision",
        "filename": name,
        "month": month,
        "publisher_checksum_sha256": publisher_sha,
        "zip_bytes_sha256": observed_sha,
        "checksum_response_sha256": hashlib.sha256(checksum_bytes).hexdigest(),
        **grid,
        # Content matching != publisher signature or legal license.
        "publisher_cryptographic_signature": "NOT_PRESENT",
        "historical_known_at": "NOT_ATTESTED",
    }


def verified_license(license_doc, download_year):
    """Rights evidence check; no owner self-declaration promoted to legal grant."""
    fail(type(license_doc) is dict and set(license_doc) == LIC_FIELDS
         and license_doc["schema"] == LICENSE_SCHEMA,
         "WAIT_LICENSE_EVIDENCE")
    fail(license_doc["issuer"] == "BINANCE_DATASET_RIGHTS_AUTHORITY"
         and license_doc["terms_url"] == TERMS_URL
         and type(license_doc["terms_sha256"]) is str
         and SHA.fullmatch(license_doc["terms_sha256"]) is not None
         and type(license_doc["download_year"]) is int
         and license_doc["download_year"] == download_year
         and type(license_doc["applies_to_download_year"]) is int
         and license_doc["applies_to_download_year"] == download_year
         and license_doc["intended_use"] == "PERSONAL_NONCOMMERCIAL_RESEARCH"
         and license_doc["permitted_use"] == "PERSONAL_NONCOMMERCIAL_RESEARCH"
         and license_doc["status"] == "INDEPENDENTLY_VERIFIED"
         and type(license_doc["issued_at_utc"]) is str
         and type(license_doc["signed_by"]) is str
         and license_doc["signed_by"] not in ("", "OWNER", "OPERATOR")
         and type(license_doc["signature_ref"]) is str
         and license_doc["signature_ref"].startswith("verified-external:"),
         "WAIT_LICENSE_EVIDENCE")
    # A JSON label is NOT itself cryptographic authentication of a license.
    # This must be checked by a separate local rights reviewer and is never
    # treated as autonomous license clearance by this module.
    return digest(license_doc)


def technical_intake(folder):
    root = Path(folder).resolve(strict=True)
    fail(root.is_dir() and not root.is_symlink(),
         "PRIVATE_EVIDENCE_DIR_INVALID")
    missing = sorted(n for n in PUBLIC_REQUIRED if not (root/n).is_file())
    fail(not missing, "MISSING_PUBLIC_LANE_EVIDENCE:" + ",".join(missing))
    technical_file = root / "technical-intake.json"
    fail(technical_file.stat().st_size <= 100_000,
         "TECHNICAL_INTAKE_TOO_LARGE")
    try:
        tech = json.loads(technical_file.read_text("utf-8"))
        lic = json.loads((root/"historical-license-evidence.json").read_text("utf-8"))
    except (UnicodeError, ValueError):
        raise Blocked("PRIVATE_EVIDENCE_INVALID_JSON") from None
    fail(type(tech) is dict and set(tech) == TECH_FIELDS and
         tech["schema"] == LANE_SCHEMA
         and tech["owner_authorization_ref"] == "#205/6718325330"
         and tech["one_time_scope_authorized"] is True,
         "UNTRUSTED_TECHNICAL_INTAKE")
    for name, column in (
        ("core245-native-receipt.json", "native_receipt_file_sha256"),
        ("manual-third-ast.json", "strategy_file_sha256"),
    ):
        fail(type(tech[column]) is str
             and sha_file(root/name) == tech[column],
             "PRIVATE_EVIDENCE_HASH_DRIFT")
    return tech, lic, root


def check_license_signature(root, reviewer_key, owner_key, license_doc):
    """Fresh rights reviewer identity is separate from source publisher SHA.

    A MAC verifies possession of independently retained reviewer key, not that
    terms are necessarily legally sound; custodian HMAC is NOT required.
    """
    fail(reviewer_key is not None, "WAIT_LICENSE_REVIEWER_KEY")
    fail(owner_key is not None, "WAIT_OWNER_SIGNING_KEY")
    reviewer = Path(reviewer_key).resolve(strict=True)
    signer = Path(owner_key).resolve(strict=True)
    fail(reviewer != signer and not contained(reviewer, root)
         and not contained(signer, root),
         "SEPARATE_OUT_OF_BAND_KEYS_REQUIRED")
    key = _key(reviewer)
    raw = (root / "historical-license-evidence.json").read_bytes()
    mac = (root / "historical-license-evidence.mac").read_text("ascii").strip()
    fail(len(mac) == 64 and hmac.compare_digest(
        hmac.new(key, raw, hashlib.sha256).hexdigest(), mac),
        "WAIT_LICENSE_INDEPENDENT_SIGNATURE")
    lic_digest = verified_license(license_doc, 2024)
    # An external review must pin the actual retained terms bytes, not just
    # display an arbitrary 64-character terms identifier in JSON.
    terms_file = root / "historical-terms.txt"
    fail(terms_file.is_file() and not terms_file.is_symlink()
         and 0 < terms_file.stat().st_size <= 512 * 1024
         and sha_file(terms_file) == license_doc["terms_sha256"],
         "WAIT_HISTORICAL_TERMS_BYTES_AND_SHA")
    return lic_digest


def run_public_batch(evidence_dir, output_dir, *, fetcher=fetch_official,
                     reviewer_key=None, owner_key=None,
                     git_repo=None, confirm_one_run=False):
    """One conditional local source read after official + license + scope gates."""
    reasons = []
    details = {"lane": "OFFICIAL_BINANCE_ARCHIVE_NONCOMMERCIAL"}
    invoked = False
    try:
        tech, lic, root = technical_intake(evidence_dir)
        proof = verify_public_month(tech["month"], fetcher=fetcher)
        details["official_zip_sha256"] = proof["zip_bytes_sha256"]
        details["official_checksum_sha256"] = proof["checksum_response_sha256"]
        details["public_bar_count"] = proof["bar_count"]
        fail(tech["start_ms"] == proof["first_open_ms"]
             and tech["end_exclusive_ms"] == proof["end_exclusive_ms"]
             and tech["decision_cutoff_ms"] == proof["end_exclusive_ms"]
             and tech["source_bytes_sha256"] == proof["zip_bytes_sha256"],
             "OFFICIAL_ARCHIVE_RANGE_OR_SOURCE_SHA_MISMATCH")
        # No original source read before independent, signed license review.
        lic_sha = check_license_signature(
            root, reviewer_key, owner_key, lic)
        details["license_review_sha256"] = lic_sha
        fail(confirm_one_run is True, "EXPLICIT_OWNER_ONE_RUN_CONFIRMATION_REQUIRED")
        fail(git_repo is not None, "PINNED_GIT_REPO_REQUIRED")
        fail(type(tech["local_source_zip"]) is str,
             "LOCAL_ARCHIVE_PATH_UNVERIFIED")
        # This local ZIP is examined only after official publisher and
        # independently authenticated reviewer rights evidence pass.
        local = Path(tech["local_source_zip"]).resolve(strict=True)
        fail(local.is_file() and not local.is_symlink()
             and local.name == proof["filename"],
             "OWNER_ORIGINAL_BINANCE_ZIP_MISSING_OR_WRONG_FILENAME")
        fail(sha_file(local) == proof["zip_bytes_sha256"],
             "OWNER_ORIGINAL_ZIP_DIFFERS_FROM_OFFICIAL_PUBLISHER")
        details["owner_zip_publisher_match"] = True

        # Reuse existing operator/queries and private source fingerprint
        # WITHOUT requiring historical third-party custodian-HMAC fiction.
        scope = build_scope(tech, root, output_dir)
        fail(not contained(owner_key, tech["warehouse_root"])
             and not contained(owner_key, tech["vault_root"])
             and not contained(owner_key, git_repo)
             and not contained(reviewer_key, tech["warehouse_root"])
             and not contained(reviewer_key, tech["vault_root"]),
             "SIGNER_KEY_IN_ORIGINAL_SOURCE_OR_CODE")
        scope["source_rights_attested"] = True
        owner_secret = _key(owner_key)
        mac = hmac.new(owner_secret,
                       canonical({"schema": SCHEMA, "scope": scope}),
                       hashlib.sha256).hexdigest()
        manifest = {"schema": SCHEMA, "scope": scope, "owner_approval_mac": mac}
        verify_owner(manifest, owner_key)
        claim_file = root / "h2-public-lane-one-use-claim.json"
        fail(not claim_file.exists(), "ONE_RUN_ALREADY_RESERVED")
        fd = os.open(claim_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"scope_sha256": digest(scope),
                       "official_sha256": proof["zip_bytes_sha256"],
                       "license_review_sha256": lic_sha,
                       "state": "ONE_ATTEMPT_NO_AUTOREPLAY"}, handle)
        invoked = True
        operator_result = execute(
            manifest, key_file=owner_key, repo=git_repo, allow_local_run=True)
        # Original local source archive is outside Warehouse/RawVault in some
        # older owner downloads; explicitly recheck it after the experiment.
        fail(sha_file(local) == proof["zip_bytes_sha256"],
             "OWNER_ORIGINAL_ZIP_CHANGED_DURING_RESEARCH")
        details["operator_receipt_sha256"] = operator_result["sha256"]
        details["operator_status"] = operator_result["status"]
        fail(operator_result["status"] == "EXPERIMENT_ENGINEERING_PASS",
             "OPERATOR_" + operator_result["reason"])
        for key in ("native_core245_sha256", "bounded_core253_sha256",
                    "coverage", "required_bars", "observed_bars", "missing_bars",
                    "scanner_sha256", "factory_package_sha256",
                    "lab_sha256", "secretary_sha256", "replay",
                    "cost_policy_sha256", "isolated_code_sha256",
                    "source_no_write_sha256"):
            if key in operator_result:
                details[key] = operator_result[key]
        return single_report("PASS_ENGINEERING_ONLY", [], details=details)
    except (Blocked, OSError, KeyError, TypeError, ValueError) as exc:
        reasons.append(str(exc) if isinstance(exc, Blocked)
                       else "PUBLIC_LANE_EVIDENCE_UNVERIFIABLE")
    return single_report("BLOCKED", reasons, details=details,
                         operator_invoked=invoked)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Official Binance provenance + gated H2")
    ap.add_argument("--private-evidence-dir", required=True)
    ap.add_argument("--isolated-output-dir", required=True)
    ap.add_argument("--license-reviewer-key")
    ap.add_argument("--owner-signing-key")
    ap.add_argument("--pinned-git-repo")
    ap.add_argument("--confirm-one-run", action="store_true")
    args = ap.parse_args(argv)
    existing = Path(args.isolated_output_dir) / "h2-batch-summary.json"
    if existing.exists():
        print(json.dumps({"status": "BLOCKED", "reason": "REPORT_ALREADY_EXISTS"}))
        return 2
    report = run_public_batch(
        args.private_evidence_dir, args.isolated_output_dir,
        reviewer_key=args.license_reviewer_key,
        owner_key=args.owner_signing_key,
        git_repo=args.pinned_git_repo, confirm_one_run=args.confirm_one_run)
    dest = write_report(args.isolated_output_dir, report)
    print(json.dumps({"status": report["status"], "reasons": report["reasons"],
                      "summary_filename": dest.name}, sort_keys=True))
    return 0 if report["status"] == "PASS_ENGINEERING_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
