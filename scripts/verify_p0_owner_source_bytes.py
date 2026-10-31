"""Fail-closed identity check for owner-supplied P0 historical evidence.

Run locally or in an authorized runner ONLY when the exact owner outer ZIP and
standalone manifest.json are present. This does not fetch or synthesize inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

from research_wp_r0.aql_p0_c1_source import (
    OUTER_ZIP_SHA256, MANIFEST_SHA256, C1SourceRejected,
)


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_owner_evidence(outer_zip: Path, manifest_path: Path) -> dict:
    if not outer_zip.is_file() or not manifest_path.is_file():
        raise C1SourceRejected("OWNER_SOURCE_FILES_NOT_PRESENT")
    outer_sha = _sha(outer_zip)
    manifest_sha = _sha(manifest_path)
    if outer_sha != OUTER_ZIP_SHA256:
        raise C1SourceRejected("OWNER_OUTER_ZIP_SHA256_MISMATCH")
    if manifest_sha != MANIFEST_SHA256:
        raise C1SourceRejected("OWNER_MANIFEST_SHA256_MISMATCH")
    with zipfile.ZipFile(outer_zip) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise C1SourceRejected("OWNER_OUTER_ZIP_CRC_MISMATCH")
        entries = [name for name in archive.namelist() if not name.endswith("/")]
        inner = [name for name in entries if name.lower().endswith(".zip")]
        if len(inner) != 7:
            raise C1SourceRejected("OWNER_EXPECTED_SEVEN_DAILY_ZIPS")
        # Verify CRC for each nested daily ZIP without writing any input to disk.
        import io
        for name in inner:
            with zipfile.ZipFile(io.BytesIO(archive.read(name))) as nested:
                if nested.testzip() is not None:
                    raise C1SourceRejected("OWNER_INNER_ZIP_CRC_MISMATCH")
    # Parse standalone manifest only after exact bytes have been verified.
    with manifest_path.open("r", encoding="utf-8") as stream:
        manifest = json.load(stream)
    if not isinstance(manifest, dict):
        raise C1SourceRejected("OWNER_MANIFEST_INVALID_SHAPE")
    return {
        "status": "OWNER_SOURCE_BYTES_VERIFIED",
        "source_bytes_sha256": outer_sha,
        "manifest_sha256": manifest_sha,
        "inner_daily_zip_count": len(inner),
        "limitations": "Byte identity and ZIP integrity only; no historical receipt/PIT attestation.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outer-zip", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    result = verify_owner_evidence(args.outer_zip, args.manifest)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    # Receipt is written only after successful verification.
    args.receipt.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
