"""Fail-closed input preflight for the pinned first historical DEV window.
Validates original bytes, the issued handoff receipt, CSV-to-normalized rows and
normalized rows-to-engine bars. Input validation only; no issuer/PIT/study authority.
"""
from __future__ import annotations
from hashlib import sha256
from io import BytesIO, StringIO
import csv, json, math, re, zipfile
from .historical_dev_exits_v1 import Config, digest, _validate as validate_engine_inputs
_SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\\Z")
_REQUIRED = frozenset({"issued_receipt_sha256","symbol","interval_ms","start_ms","end_exclusive_ms","code_sha","policy_id","scenario_id","warmup_bars","source_kind"})
START_MS, END_MS = 1704067200000, 1704153600000
RAW_SHA = "4ec2915e610ab4e9a4d5e86a5ada1c15bbf6b5db343cdb385681d6ac97166a4e"
ISSUED_SHA = "ffce2bbe7890414d84360be80a0ac478795ae8d1a28085f8bb34075faca83386"
SOURCE_ID = "binance-vision:spot:BTCUSDT:1m:2024-01-01"
RECEIPT_ID = "AQL-CORE-WORK152-BTCUSDT-20240101-001"
MEMBER = "BTCUSDT-1m-2024-01-01.csv"
class InputGateRejected(ValueError): pass
def sha256_hex(raw: bytes) -> str: return sha256(raw).hexdigest()
def _require(condition, reason):
    if not condition: raise InputGateRejected(reason)
def _parse_archive(archive_bytes):
    try:
        with zipfile.ZipFile(BytesIO(archive_bytes)) as z:
            names=z.namelist()
            _require(names == [MEMBER], "UNEXPECTED_ARCHIVE_MEMBERS")
            _require(z.testzip() is None, "ARCHIVE_CRC_FAILURE")
            text=z.read(MEMBER).decode("utf-8")
    except (zipfile.BadZipFile, UnicodeDecodeError, KeyError) as exc:
        raise InputGateRejected("INVALID_OR_CORRUPT_ARCHIVE") from exc
    rows=[]
    try:
        for i,row in enumerate(csv.reader(StringIO(text))):
            _require(len(row)==12, "INVALID_CSV_COLUMN_COUNT")
            t,ct=int(row[0]),int(row[6]); o,h,l,c,v=(float(row[j]) for j in (1,2,3,4,5))
            _require(all(math.isfinite(x) for x in (o,h,l,c,v)), "NONFINITE_OHLCV")
            _require(t==START_MS+i*60000, "CSV_GRID_GAP_OR_DUPLICATE")
            _require(ct==t+59999, "CSV_CLOSE_TIME_MISMATCH")
            _require(min(o,h,l,c)>0 and v>=0 and h>=max(o,c,l) and l<=min(o,c), "INVALID_CSV_OHLCV")
            rows.append([t,ct,o,h,l,c,v])
    except (ValueError, OverflowError) as exc:
        if isinstance(exc, InputGateRejected): raise
        raise InputGateRejected("INVALID_CSV_ROW_VALUE") from exc
    _require(len(rows)==1440, "EXPECTED_EXACTLY_1440_ONE_MINUTE_ROWS")
    normalized=json.dumps(rows,separators=(",",":"),allow_nan=False).encode()
    return rows,sha256_hex(normalized),len(normalized)
def validate_historical_dev_inputs(*,archive_bytes: bytes,issued_receipt_bytes: bytes,bars: list[dict],source: dict,config: Config,commitment: dict) -> dict:
    _require(isinstance(archive_bytes,bytes) and bool(archive_bytes), "MISSING_ORIGINAL_ARCHIVE_BYTES")
    _require(isinstance(issued_receipt_bytes,bytes) and bool(issued_receipt_bytes), "MISSING_ISSUED_RECEIPT_BYTES")
    _require(isinstance(commitment,dict) and set(commitment)==_REQUIRED, "MISSING_OR_EXTRA_INPUT_COMMITMENT")
    for k in ("code_sha","policy_id","scenario_id"): _require(isinstance(commitment[k],str) and _SAFE.fullmatch(commitment[k]), "INVALID_"+k.upper())
    _require(commitment["symbol"]=="BTCUSDT", "UNEXPECTED_SYMBOL")
    _require(commitment["interval_ms"]==60000 and config.interval_ms==60000, "UNEXPECTED_INTERVAL")
    _require((commitment["start_ms"],commitment["end_exclusive_ms"])==(START_MS,END_MS), "UNEXPECTED_WINDOW")
    _require(commitment["warmup_bars"]==252 and config.warmup_bars==252, "EXPLICIT_252_WARMUP_REQUIRED")
    _require(commitment["source_kind"] in ("ORIGINAL_LOCAL_PAIR","SYNTHETIC_TEST_FIXTURE"), "UNSUPPORTED_SOURCE_KIND")
    archive_sha=sha256_hex(archive_bytes); receipt_sha=sha256_hex(issued_receipt_bytes)
    _require(commitment["issued_receipt_sha256"]==receipt_sha, "ISSUED_RECEIPT_SHA_MISMATCH")
    _require(source.get("archive_sha256")==archive_sha, "ORIGINAL_ARCHIVE_SHA_MISMATCH")
    try: receipt=json.loads(issued_receipt_bytes)
    except (ValueError,UnicodeDecodeError) as exc: raise InputGateRejected("INVALID_ISSUED_RECEIPT_JSON") from exc
    _require(isinstance(receipt,dict), "INVALID_ISSUED_RECEIPT_SHAPE")
    norm=receipt.get("normalization",{}); acq=receipt.get("acquisition",{}).get("archive",{})
    _require(norm.get("bars")==1440 and norm.get("normalization")=="binance12-to-7-tuple-python-float-json-v1", "RECEIPT_NORMALIZATION_SCHEMA_MISMATCH")
    _require(acq.get("sha256")==archive_sha, "RECEIPT_ARCHIVE_SHA_MISMATCH")
    _require(acq.get("size_bytes")==len(archive_bytes), "RECEIPT_ARCHIVE_SIZE_MISMATCH")
    if commitment["source_kind"]=="ORIGINAL_LOCAL_PAIR":
        _require(archive_sha==RAW_SHA and len(archive_bytes)==68923, "ORIGINAL_ARCHIVE_PIN_MISMATCH")
        _require(receipt_sha==ISSUED_SHA and len(issued_receipt_bytes)==4203, "ORIGINAL_ISSUED_RECEIPT_PIN_MISMATCH")
        _require(receipt.get("source_id")==SOURCE_ID and receipt.get("receipt_id")==RECEIPT_ID, "ORIGINAL_SOURCE_RECEIPT_ID_MISMATCH")
        _require(receipt.get("scope")=="REAL_SOURCE_DEV_ONLY" and receipt.get("strategy_execution")=="NOT_PERFORMED" and receipt.get("real_pit_accepted") is False and receipt.get("verified_source_timing") is False, "RECEIPT_SCOPE_OR_TRUST_STATUS_CHANGED")
    normalized,normalized_sha,normalized_size=_parse_archive(archive_bytes)
    _require(norm.get("normalized_sha256")==normalized_sha, "RECEIPT_NORMALIZED_SHA_MISMATCH")
    _require(norm.get("normalized_size_bytes")==normalized_size, "RECEIPT_NORMALIZED_SIZE_MISMATCH")
    _require(isinstance(bars,list) and len(bars)==len(normalized), "ENGINE_BAR_COUNT_MISMATCH")
    for i,(b,n) in enumerate(zip(bars,normalized)):
        got=[b.get(k) for k in ("open_ms","close_ms","open","high","low","close","volume")]
        _require(got==n, "ARCHIVE_TO_ENGINE_ROW_MISMATCH_"+str(i))
    try: validate_engine_inputs(bars,source,config)
    except (ValueError,TypeError,KeyError,AttributeError) as exc: raise InputGateRejected("ENGINE_INPUT_VALIDATION:"+str(exc)) from exc
    _require(source.get("rows_sha256")==digest(bars), "NORMALIZED_ROWS_DIGEST_MISMATCH")
    return {"schema":"sf-dev-input-preflight-v1","status":"INPUT_BYTES_AND_NORMALIZED_ROWS_VALID_NOT_STUDY_AUTHORITY","symbol":"BTCUSDT","interval_ms":60000,"start_ms":START_MS,"end_exclusive_ms":END_MS,"bar_count":1440,"warmup_bars":252,"archive_sha256":archive_sha,"issued_receipt_sha256":receipt_sha,"normalized_rows_sha256":digest(bars),"raw_normalized7_sha256":normalized_sha,"code_sha":commitment["code_sha"],"policy_id":commitment["policy_id"],"scenario_id":commitment["scenario_id"],"source_kind":commitment["source_kind"],"source_id":receipt.get("source_id"),"receipt_id":receipt.get("receipt_id"),"receipt_authenticity":"NOT_AUTHENTICATED_BY_THIS_GATE","point_in_time_provenance":"NOT_ESTABLISHED_BY_THIS_GATE"}