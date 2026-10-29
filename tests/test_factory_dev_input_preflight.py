"""Synthetic-only tests for exact first-run input preflight and result persistence."""
from hashlib import sha256
from io import BytesIO, StringIO
import csv, json, zipfile
import pytest
from research_wp_r0.historical_dev_exits_v1 import Config, digest, replay
from research_wp_r0.dev_input_preflight import InputGateRejected, validate_historical_dev_inputs
from research_wp_r0.dev_result_bundle import persist_bundle, verify_bundle
START=1704067200000
END=1704153600000
def bars():
    return [{"open_ms":START+i*60000,"close_ms":START+(i+1)*60000-1,"open":100.0,"high":101.0,"low":99.0,"close":100.5,"volume":1.0,"available_ms":START+(i+1)*60000+1000,"modeled_quote":True} for i in range(1440)]
def archive_bytes(rows):
    out=BytesIO(); text=StringIO(); w=csv.writer(text,lineterminator="\n")
    for b in rows:
        w.writerow([b["open_ms"],b["open"],b["high"],b["low"],b["close"],b["volume"],b["close_ms"],"0",1,"0","0",0])
    with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as z: z.writestr("BTCUSDT-1m-2024-01-01.csv",text.getvalue())
    return out.getvalue()
def inputs():
    rows=bars(); raw=archive_bytes(rows); normalized=[[b[k] for k in ("open_ms","close_ms","open","high","low","close","volume")] for b in rows]
    nb=json.dumps(normalized,separators=(",",":"),allow_nan=False).encode()
    receipt={"schema":"aql-work152-artifact-handoff-receipt-1","scope":"SYNTHETIC_TEST_ONLY","status":"SYNTHETIC_FIXTURE_NOT_ISSUED","source_id":"fixture:synthetic","receipt_id":"fixture-receipt","strategy_execution":"NOT_PERFORMED","real_pit_accepted":False,"verified_source_timing":False,"acquisition":{"archive":{"sha256":sha256(raw).hexdigest(),"size_bytes":len(raw)}},"normalization":{"bars":1440,"normalization":"binance12-to-7-tuple-python-float-json-v1","normalized_sha256":sha256(nb).hexdigest(),"normalized_size_bytes":len(nb)}}
    issued=json.dumps(receipt,sort_keys=True,separators=(",",":")).encode()
    source={"version":"synthetic-b0","reference":"fixture:input-preflight","archive_sha256":sha256(raw).hexdigest(),"rows_sha256":digest(rows),"availability_evidence":"UNKNOWN","correction_evidence":"PINNED_VERSION_ONLY"}
    commitment={"issued_receipt_sha256":sha256(issued).hexdigest(),"symbol":"BTCUSDT","interval_ms":60000,"start_ms":START,"end_exclusive_ms":END,"code_sha":"20928693f30b1730f0693a293bbf4a1f8ab21c88","policy_id":"DEV-B0-v1","scenario_id":"S00","warmup_bars":252,"source_kind":"SYNTHETIC_TEST_FIXTURE"}
    return raw,issued,rows,source,commitment
def run(args):
    raw,issued,rows,source,commitment=args
    return validate_historical_dev_inputs(archive_bytes=raw,issued_receipt_bytes=issued,bars=rows,source=source,config=Config(warmup_bars=252,latency_ms=1000,quantity=0.001),commitment=commitment)
def test_exact_one_day_preflight_returns_non_authorizing_manifest():
    out=run(inputs())
    assert out["status"]=="INPUT_BYTES_AND_NORMALIZED_ROWS_VALID_NOT_STUDY_AUTHORITY"
    assert out["bar_count"]==1440 and out["warmup_bars"]==252
    assert out["receipt_authenticity"]=="NOT_AUTHENTICATED_BY_THIS_GATE"
def test_wrong_run_contract_fails_closed():
    for field,value,error in [("symbol","ETHUSDT","UNEXPECTED_SYMBOL"),("interval_ms",300000,"UNEXPECTED_INTERVAL"),("warmup_bars",22,"EXPLICIT_252_WARMUP_REQUIRED"),("start_ms",START+60000,"UNEXPECTED_WINDOW")]:
        args=list(inputs()); args[4]=dict(args[4]); args[4][field]=value
        with pytest.raises(InputGateRejected,match=error): run(tuple(args))
def test_wrong_archive_or_issued_receipt_digest_fails_closed():
    args=list(inputs()); args[0]=args[0]+b"tampered"
    with pytest.raises(InputGateRejected,match="ORIGINAL_ARCHIVE_SHA_MISMATCH"): run(tuple(args))
    args=list(inputs()); args[1]=args[1]+b"tampered"
    with pytest.raises(InputGateRejected,match="ISSUED_RECEIPT_SHA_MISMATCH"): run(tuple(args))
def test_missing_bar_and_corrupt_archive_fail_closed():
    args=list(inputs()); args[2]=args[2][:-1]
    with pytest.raises(InputGateRejected,match="ENGINE_BAR_COUNT_MISMATCH"): run(tuple(args))
    args=list(inputs()); args[0]=b"not a zip archive"
    with pytest.raises(InputGateRejected,match="ORIGINAL_ARCHIVE_SHA_MISMATCH"): run(tuple(args))
def test_row_tampering_fails_closed():
    args=list(inputs()); args[2]=list(args[2]); args[2][100]=dict(args[2][100],open_ms=args[2][100]["open_ms"]+1)
    with pytest.raises(InputGateRejected,match="ARCHIVE_TO_ENGINE_ROW_MISMATCH"): run(tuple(args))
def test_validated_preflight_is_saved_and_reverified_with_result_bundle(tmp_path):
    raw,issued,rows,source,commitment=inputs(); config=Config(warmup_bars=252,latency_ms=1000,quantity=0.001)
    preflight=validate_historical_dev_inputs(archive_bytes=raw,issued_receipt_bytes=issued,bars=rows,source=source,config=config,commitment=commitment)
    receipt=replay(rows,source=source,config=config)
    evidence={"policy_id":"DEV-B0-v1","policy_sha256":digest({"policy_id":"DEV-B0-v1","engine_config":receipt["config"]}),"source_zip_sha256":source["archive_sha256"],"issued_receipt_sha256":commitment["issued_receipt_sha256"],"code_sha":commitment["code_sha"],"input_prefix_sha256":digest(receipt["input_rows"]),"scenario_id":"S00","warmup_bars":252,"experiment_id":"AQL-DEV-FIRST-01"}
    manifest=persist_bundle(str(tmp_path),run_id="preflighted-run",receipt=receipt,evidence=evidence,input_preflight=preflight)
    assert "input_preflight.json" in manifest["files"] and verify_bundle(str(tmp_path),"preflighted-run")
    saved=json.loads((tmp_path/"preflighted-run"/"input_preflight.json").read_text())
    assert saved["archive_sha256"]==source["archive_sha256"] and saved["bar_count"]==1440
def test_preflight_mismatch_fails_before_creating_run_directory(tmp_path):
    raw,issued,rows,source,commitment=inputs(); config=Config(warmup_bars=252,latency_ms=1000,quantity=0.001)
    preflight=validate_historical_dev_inputs(archive_bytes=raw,issued_receipt_bytes=issued,bars=rows,source=source,config=config,commitment=commitment)
    receipt=replay(rows,source=source,config=config)
    evidence={"policy_id":"DEV-B0-v1","policy_sha256":digest({"policy_id":"DEV-B0-v1","engine_config":receipt["config"]}),"source_zip_sha256":source["archive_sha256"],"issued_receipt_sha256":"f"*64,"code_sha":commitment["code_sha"],"input_prefix_sha256":digest(receipt["input_rows"]),"scenario_id":"S00","warmup_bars":252,"experiment_id":"AQL-DEV-FIRST-02"}
    with pytest.raises(ValueError,match="INPUT_PREFLIGHT_RECEIPT_BINDING_MISMATCH"): persist_bundle(str(tmp_path),run_id="mismatched-run",receipt=receipt,evidence=evidence,input_preflight=preflight)
    assert not (tmp_path/"mismatched-run").exists()

@pytest.mark.parametrize("field,value,error", [
    ("code_sha", "a"*40, "UNPINNED_ENGINE_CODE_SHA"),
    ("policy_id", "DEV-B0-UNREVIEWED", "UNAPPROVED_POLICY_ID"),
    ("scenario_id", "S12", "UNAPPROVED_SCENARIO_ID"),
])
def test_unpinned_engine_or_unapproved_policy_scenario_fails_closed(field,value,error):
    args=list(inputs()); args[4]=dict(args[4]); args[4][field]=value
    with pytest.raises(InputGateRejected,match=error): run(tuple(args))


@pytest.mark.parametrize("field,value", [
    ("code_sha", "a"*40),
    ("policy_id", "DEV-B0-UNREVIEWED"),
    ("scenario_id", "S12"),
])
def test_result_bundle_refuses_forged_preflight_pin_before_creating_run(tmp_path,field,value):
    raw,issued,rows,source,commitment=inputs()
    config=Config(warmup_bars=252,latency_ms=1000,quantity=0.001)
    preflight=validate_historical_dev_inputs(archive_bytes=raw,issued_receipt_bytes=issued,bars=rows,source=source,config=config,commitment=commitment)
    receipt=replay(rows,source=source,config=config)
    evidence={"policy_id":"DEV-B0-v1","policy_sha256":digest({"policy_id":"DEV-B0-v1","engine_config":receipt["config"]}),"source_zip_sha256":source["archive_sha256"],"issued_receipt_sha256":commitment["issued_receipt_sha256"],"code_sha":commitment["code_sha"],"input_prefix_sha256":digest(receipt["input_rows"]),"scenario_id":"S00","warmup_bars":252,"experiment_id":"AQL-DEV-FIRST-01"}
    preflight[field]=value
    with pytest.raises(ValueError,match="UNPINNED_ENGINE_OR_UNAPPROVED_POLICY_SCENARIO"):
        persist_bundle(str(tmp_path),run_id="forged-preflight",receipt=receipt,evidence=evidence,input_preflight=preflight)
    assert not (tmp_path/"forged-preflight").exists()
