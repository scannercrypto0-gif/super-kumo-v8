"""Core #253: bounded, private, opt-in native Binance monthly 15m acquisition.

One new BTCUSDT Spot 15m month, excluding previously pinned Feb/Aug 2024.
No downloads on import or by default. No data bytes/CSV in GitHub/CI.
This is a local private-source staging preflight, NOT a PIT attestation
or proof of RAW Vault ingestion. The actual Core #226 ingest/query remains
the canonical existing implementation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import urllib.request
from zipfile import ZipFile

MAX_ZIP_BYTES = 8_000_000
MAX_CHECKSUM_BYTES = 512
MAX_CSV_BYTES = 16_000_000
INTERVAL_MS = 900_000
SCHEMA = "aql.core.bounded-monthly-15m-source-preflight.v1"
MONTH = re.compile(r"^2024-(0[1-9]|1[0-2])$")
SHA = re.compile(r"^[0-9a-f]{64}$")


class SourcePreflightError(ValueError):
    pass


def _need(ok, code):
    if not ok:
        raise SourcePreflightError(code)


def month_window(month):
    _need(isinstance(month, str) and MONTH.fullmatch(month) is not None,
          "MONTH_OUTSIDE_APPROVED_2024_SCOPE")
    _need(month not in ("2024-02", "2024-08"),
          "ALREADY_PINNED_ORIGINAL_MONTH_REFUSED")
    y, m = map(int, month.split("-"))
    start = int(datetime(y, m, 1, tzinfo=timezone.utc).timestamp()*1000)
    end = int(datetime(y+(m==12), (m%12)+1, 1,
                       tzinfo=timezone.utc).timestamp()*1000)
    return start, end


def source_urls(month):
    month_window(month)
    name=f"BTCUSDT-15m-{month}.zip"
    base="https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/15m/"
    return {"archive_name":name, "archive_url":base+name,
            "checksum_name":name+".CHECKSUM",
            "checksum_url":base+name+".CHECKSUM"}


def _hash(blob):
    return hashlib.sha256(blob).hexdigest()


def verify_native_month(month, raw_zip, checksum, *, provenance):
    start, end = month_window(month)
    u=source_urls(month)
    _need(type(raw_zip) is bytes and 0<len(raw_zip)<=MAX_ZIP_BYTES,
          "ZIP_SIZE_OUTSIDE_BOUND")
    _need(type(checksum) is bytes and 0<len(checksum)<=MAX_CHECKSUM_BYTES,
          "CHECKSUM_SIZE_OUTSIDE_BOUND")
    _need(isinstance(provenance,str) and 0<len(provenance)<=256,
          "SOURCE_PROVENANCE_REQUIRED")
    _need(checksum.strip()==(_hash(raw_zip)+"  "+u["archive_name"]).encode(),
          "PUBLISHER_CHECKSUM_MISMATCH")
    try:
        with ZipFile(io.BytesIO(raw_zip)) as z:
            names=z.namelist()
            _need(names==[u["archive_name"][:-4]+".csv"],
                  "UNEXPECTED_ZIP_MEMBERS")
            info=z.infolist()[0]
            _need(info.file_size<=MAX_CSV_BYTES and
                  info.compress_size<=MAX_ZIP_BYTES,
                  "CSV_DECOMPRESSION_BOUND")
            _need(not info.flag_bits & 1, "ENCRYPTED_ZIP_REFUSED")
            csv=z.read(names[0])
            _need(z.testzip() is None, "ZIP_CRC_FAILURE")
    except (OSError, ValueError, RuntimeError, EOFError) as exc:
        if isinstance(exc,SourcePreflightError):
            raise
        raise SourcePreflightError("ZIP_FORMAT_OR_CRC_FAILURE") from exc
    # Binance original native 12-column kline CSV; validate grid and
    # chronology, do not normalize/relabel source or compute fake PIT.
    rows=csv.splitlines()
    expected=(end-start)//INTERVAL_MS
    _need(len(rows)==expected and 2688<=expected<=2976,
          "MISSING_OR_EXTRA_NATIVE_BARS")
    first=None
    last=None
    seen=set()
    for i,row in enumerate(rows):
        parts=row.split(b",")
        _need(len(parts)==12 and parts[0].isdigit() and
              parts[6].isdigit(),"NATIVE_12_COLUMN_CSV_REQUIRED")
        open_ms=int(parts[0])
        close_ms=int(parts[6])
        _need(open_ms==start+i*INTERVAL_MS and
              close_ms==open_ms+INTERVAL_MS-1 and
              open_ms not in seen,"GAP_DUPLICATE_OR_CLOSE_DRIFT")
        seen.add(open_ms)
        if first is None:
            first=open_ms
        last=open_ms
    body={
        "schema":SCHEMA,"source_class":"OWNER_PRIVATE_RETROSPECTIVE_NON_PIT",
        "publisher_signature_verified":False,
        "historical_known_at_ms":None,"historical_pit":"NOT_ATTESTED",
        "scientific_result":"INSUFFICIENT_EVIDENCE",
        "trading_authority":"NONE",
        "month":month,"exchange":"BINANCE","market":"SPOT",
        "symbol":"BTCUSDT","interval":"15m",
        "archive_name":u["archive_name"],
        "checksum_name":u["checksum_name"],
        "archive_url":u["archive_url"],
        "checksum_url":u["checksum_url"],
        "source_provenance":provenance,
        "archive_sha256":_hash(raw_zip),
        "checksum_file_sha256":_hash(checksum),
        "csv_member_sha256":_hash(csv),
        "archive_bytes":len(raw_zip),
        "checksum_bytes":len(checksum),
        "csv_bytes":len(csv),
        "start_ms":start,"end_exclusive_ms":end,
        "expected_bars":expected,"observed_bars":len(rows),
        "missing_bar_count":0,"duplicate_bar_count":0,
        "first_bar_open_ms":first,"last_bar_open_ms":last,
        "coverage":"COMPLETE",
        "vault_ingestion":"NOT_EXECUTED_BY_PREFLIGHT",
        "core_query":"NOT_EXECUTED_BY_PREFLIGHT",
    }
    seal=json.dumps(body,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    return {**body,"preflight_receipt_sha256":_hash(seal)}


def _download(url, limit):
    request=urllib.request.Request(url,headers={
        "User-Agent":"AQL-Core-253-Private-Source-Preflight/1.0"})
    with urllib.request.urlopen(request,timeout=25) as response:
        _need(response.status==200,"SOURCE_HTTP_NOT_200")
        content_length=response.headers.get("Content-Length")
        if content_length is not None:
            _need(int(content_length)<=limit,"REMOTE_SOURCE_TOO_LARGE")
        blob=response.read(limit+1)
    _need(0<len(blob)<=limit,"SOURCE_DOWNLOAD_SIZE_LIMIT")
    return blob


def stage_one_month(month, private_dir, *, allow_network=False):
    """Opt-in one month, source bytes only in caller's private local directory."""
    u=source_urls(month)
    root=Path(private_dir)
    _need(root.is_dir(),"PRIVATE_STAGING_DIRECTORY_REQUIRED")
    archive=root/u["archive_name"]
    checksum=root/u["checksum_name"]
    _need(not archive.exists() and not checksum.exists(),
          "CREATE_ONLY_SOURCE_ALREADY_PRESENT")
    _need(allow_network is True,"NETWORK_OPT_IN_REQUIRED")
    # Fetch small checksum first; fail closed before large archive.
    cs=_download(u["checksum_url"],MAX_CHECKSUM_BYTES)
    raw=_download(u["archive_url"],MAX_ZIP_BYTES)
    receipt=verify_native_month(month,raw,cs,provenance="BINANCE_VISION_FETCHED_NOW")
    # Atomic create-only files. No overwrite; no source bytes in stdout.
    created=[]
    try:
        for path,blob in ((archive,raw),(checksum,cs)):
            with path.open("xb") as fh:
                fh.write(blob)
            created.append(path)
        receipt_path=root/(u["archive_name"]+".preflight.json")
        with receipt_path.open("x",encoding="utf-8") as fh:
            json.dump(receipt,fh,sort_keys=True,indent=2)
        return receipt
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--month",required=True)
    p.add_argument("--private-dir",required=True)
    p.add_argument("--allow-network",action="store_true")
    args=p.parse_args()
    # Default is preflight only. Explicit opt-in to one bounded download.
    if not args.allow_network:
        print(json.dumps({"status":"READY_FOR_SOURCE",
                          "scope":source_urls(args.month),
                          "max_zip_bytes":MAX_ZIP_BYTES,
                          "network":"NOT_USED"},sort_keys=True))
        return
    print(json.dumps(stage_one_month(args.month,args.private_dir,
                                     allow_network=True),sort_keys=True))


if __name__=="__main__":
    main()
