"""Changed-seam synthetic custody, corruption and cold-read regression checks."""
from copy import deepcopy
import json
from pathlib import Path
import time
from unittest.mock import patch

import pytest
from tools.atlas_stage6_durable import (
    AUTHORITY, CAP, ENDPOINT, STEP, TTL_MS, digest, parse_frame, record, replay,
    write_document,
)


def frame(opened, **changes):
    kline = dict(s="BTCUSDT", i="15m", t=opened, T=opened+STEP-1,
                 x=True, o="100", h="102", l="99", c="101", v="2")
    kline.update(changes)
    return json.dumps(dict(e="kline", s="BTCUSDT", E=opened+STEP, k=kline)).encode()


@pytest.fixture
def retained(tmp_path):
    records = []
    for opened in (STEP, 2*STEP):
        stamp = opened+STEP+10
        with patch("time.time_ns", return_value=stamp*1_000_000), patch("time.time", return_value=stamp/1000):
            records.append(record(tmp_path, frame(opened), stamp, stamp))
    plan = dict(endpoint=ENDPOINT, authority=AUTHORITY, target_count=2, byte_cap=CAP,
                ttl_ms=TTL_MS, expires_ms=time.time_ns()//1_000_000+TTL_MS)
    write_document(tmp_path/"plan.json", plan)
    body = dict(plan_sha256=digest(plan), records=records,
                decision_ms=records[-1]["g1_ack"]["commit_return_observed_at_ms"]+1000)
    write_document(tmp_path/"manifest.json", {**body, "sha256":digest(body)})
    return tmp_path


def test_native_cold_read_is_deterministic_and_waits_for_clock(retained):
    before = {p.name:p.read_bytes() for p in retained.iterdir() if p.suffix in (".frame",".json")}
    first, second = replay(retained), replay(retained)
    assert first == second
    assert first["native_consumer"]["source_checksums"]
    assert first["native_consumer"]["ready"] is False
    assert first["orders"] == 0 and first["secretary"] == "WAIT"
    assert before == {p.name:p.read_bytes() for p in retained.iterdir() if p.suffix in (".frame",".json")}


def test_raw_tamper_fails(retained):
    (retained/f"{STEP}.frame").write_bytes(b"{}")
    with pytest.raises(ValueError, match="RETAINED_FRAME_DIGEST"):
        replay(retained)


def test_source_swap_and_nonfinite_are_rejected():
    with pytest.raises(ValueError,match="SOURCE_IDENTITY"):
        parse_frame(frame(STEP,s="ETHUSDT"),2*STEP+10)
    with pytest.raises(ValueError,match="PRICE_QUALITY"):
        parse_frame(frame(STEP,c="NaN"),2*STEP+10)


def test_conflicting_duplicate_retains_first_bytes(retained):
    path=retained/f"{STEP}.frame"
    before=path.read_bytes()
    with pytest.raises(ValueError,match="FRAME_CONFLICT"):
        record(retained,frame(STEP,c="100.5"),2*STEP+10,1)
    assert path.read_bytes()==before


def test_expired_retention_refuses_read(retained):
    path=retained/"plan.json"
    plan=json.loads(path.read_text());plan["expires_ms"]=0
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError,match="RETENTION_EXPIRED"):
        replay(retained)


def test_manifest_reseal_cannot_change_ack(retained):
    path=retained/"manifest.json"
    doc=json.loads(path.read_text())
    doc["records"][0]["g1_ack"]["content_digest"]="0"*64
    row=doc["records"][0];row["sha256"]=digest({k:v for k,v in row.items() if k!="sha256"})
    doc["sha256"]=digest({k:v for k,v in doc.items() if k!="sha256"})
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError,match="RETAINED_ACK_IDENTITY"):
        replay(retained)
