"""Stage7 exact-source research intake: no fabricated Scanner signal or ACK."""
import json
import time
from unittest.mock import patch

import pytest

from tools.atlas_stage6_durable import (
    AUTHORITY, CAP, ENDPOINT, STEP, TTL_MS, digest, record, write_document,
)
from research_wp_r0.aql_stage7_source_research_v1 import (
    build_wait_report, read_immutable_report, verify_wait_report,
    write_immutable_report,
)


@pytest.fixture
def source(tmp_path):
    rows = []
    for opened in (STEP, 2 * STEP):
        stamp = opened + STEP + 10
        candle = dict(s="BTCUSDT", i="15m", t=opened,
                      T=opened + STEP - 1, x=True, o="100", h="102",
                      l="99", c="101", v="2")
        raw = json.dumps(dict(e="kline", s="BTCUSDT",
                              E=opened + STEP, k=candle)).encode()
        with patch("time.time_ns", return_value=stamp * 1_000_000), \
             patch("time.time", return_value=stamp / 1000):
            rows.append(record(tmp_path, raw, stamp, stamp))
    plan = dict(endpoint=ENDPOINT, authority=AUTHORITY, target_count=2,
                byte_cap=CAP, ttl_ms=TTL_MS,
                expires_ms=time.time_ns() // 1_000_000 + TTL_MS)
    write_document(tmp_path / "plan.json", plan)
    body = dict(plan_sha256=digest(plan), records=rows,
                decision_ms=rows[-1]["g1_ack"]["commit_return_observed_at_ms"] + 1000)
    pin = digest(body)
    write_document(tmp_path / "manifest.json", {**body, "sha256": pin})
    return tmp_path, pin


def test_exact_source_to_research_wait_immutable_readback(source, tmp_path):
    root, pin = source
    before = {p.name: p.read_bytes() for p in root.iterdir() if p.suffix in (".frame", ".json")}
    a = build_wait_report(root, expected_manifest_sha256=pin)
    b = build_wait_report(root, expected_manifest_sha256=pin)
    assert a == b
    assert a["scanner_opportunity_sha256"] is None
    assert a["factory_consumer_ack_sha256"] is None
    assert a["secretary"] == "WAIT" and a["orders"] == 0
    assert a["source_count"] == 2
    reports = tmp_path / "reports"
    reports.mkdir()
    path = reports / "stage7-research.json"
    assert write_immutable_report(a, path, expected_manifest_sha256=pin) == a["sha256"]
    assert write_immutable_report(a, path, expected_manifest_sha256=pin) == a["sha256"]
    assert read_immutable_report(path, expected_manifest_sha256=pin) == a
    assert before == {p.name: p.read_bytes() for p in root.iterdir() if p.suffix in (".frame", ".json")}


def test_wrong_manifest_denied(source):
    root, _ = source
    with pytest.raises(ValueError, match="EXTERNAL_MANIFEST_PIN"):
        build_wait_report(root, expected_manifest_sha256="0" * 64)


def test_expired_source_denied(source):
    root, pin = source
    path = root / "plan.json"
    plan = json.loads(path.read_text())
    plan["expires_ms"] = 0
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="RETENTION_EXPIRED"):
        build_wait_report(root, expected_manifest_sha256=pin)


def test_fabricated_approval_denied(source):
    root, pin = source
    report = build_wait_report(root, expected_manifest_sha256=pin)
    report["secretary_approval_sha256"] = "a" * 64
    with pytest.raises(ValueError, match="REPORT_SEAL"):
        verify_wait_report(report, expected_manifest_sha256=pin)
    report["sha256"] = digest({k: v for k, v in report.items() if k != "sha256"})
    with pytest.raises(ValueError, match="AUTHORITY_OR_SOURCE_DRIFT"):
        verify_wait_report(report, expected_manifest_sha256=pin)


def test_immutable_conflict_denied(source, tmp_path):
    root, pin = source
    report = build_wait_report(root, expected_manifest_sha256=pin)
    path = tmp_path / "report.json"
    path.write_text("not the report")
    with pytest.raises(ValueError, match="IMMUTABLE_CONFLICT"):
        write_immutable_report(report, path, expected_manifest_sha256=pin)
