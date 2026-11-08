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
    fail(start.strftime("%Y-%m") == month and end.strftime("%Y-%m") == month,
         "OFFICIAL_KLINE_WRONG_MONTH")
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
    fail(type(tech["download_year"]) is int if "download_year" in tech else True,
         "TECHNICAL_YEAR_INVALID")
    return tech, lic, root


def public_gate(folder, fetcher=fetch_official):
    """Read only named private INTAKE files; never open original market store."""
    tech, lic, root = technical_intake(folder)
    # Import the legacy shape validator only after publisher proof, without
    # reusing its independent-custodian HMAC authority requirement.
    month = tech["month"]
    proof = verify_public_month(month, fetcher=fetcher)
    fail(tech["start_ms"] == proof["first_open_ms"]
         and tech["end_exclusive_ms"] == proof["end_exclusive_ms"]
         and tech["decision_cutoff_ms"] == proof["end_exclusive_ms"]
         and proof["bar_count"] <= 4096,
         "OFFICIAL_ARCHIVE_RANGE_OR_COVERAGE_MISMATCH")
    # The exact 2024-era rights terms are presently not evidenced.
    # A purported signer label is not a signature: do not execute original
    # data until an independent license authority is verifiable.
    lic_sha = verified_license(lic, 2024)
    raise Blocked("WAIT_LICENSE_INDEPENDENT_AUTHORITY_VERIFICATION")


def run_public_batch(evidence_dir, output_dir, *, fetcher=fetch_official):
    """Current safe phase: true publisher verification, then rights stop."""
    reasons = []
    details = {"lane": "OFFICIAL_BINANCE_ARCHIVE_NONCOMMERCIAL"}
    try:
        tech, lic, root = technical_intake(evidence_dir)
        proof = verify_public_month(tech["month"], fetcher=fetcher)
        details["official_zip_sha256"] = proof["zip_bytes_sha256"]
        details["official_checksum_sha256"] = proof["checksum_response_sha256"]
        details["public_bar_count"] = proof["bar_count"]
        fail(tech["start_ms"] == proof["first_open_ms"]
             and tech["end_exclusive_ms"] == proof["end_exclusive_ms"]
             and tech["decision_cutoff_ms"] == proof["end_exclusive_ms"],
             "OFFICIAL_ARCHIVE_RANGE_OR_COVERAGE_MISMATCH")
        verified_license(lic, 2024)
        # The signer label of a private JSON is not a signature. The external
        # authority and historically applicable rights must be independently
        # authenticated before ORIGINAL E: is accessed by a future phase.
        raise Blocked("WAIT_LICENSE_INDEPENDENT_AUTHORITY_VERIFICATION")
    except (Blocked, OSError, KeyError, TypeError, ValueError) as exc:
        reasons.append(str(exc) if isinstance(exc, Blocked)
                       else "PUBLIC_LANE_EVIDENCE_UNVERIFIABLE")
    return single_report("BLOCKED", reasons, details=details)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Official Binance ZIP SHA; no E: IO")
    ap.add_argument("--private-evidence-dir", required=True)
    ap.add_argument("--isolated-output-dir", required=True)
    args = ap.parse_args(argv)
    report = run_public_batch(args.private_evidence_dir, args.isolated_output_dir)
    dest = write_report(args.isolated_output_dir, report)
    print(json.dumps({"status": report["status"],
                      "reasons": report["reasons"],
                      "summary_filename": dest.name}, sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
