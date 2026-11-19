"""Stage 7 bounded research consumer for an already-authorized Stage 6 source.

This is a truthful WAIT/NO_ORDER research intake, not a strategy result, a
Scanner opportunity, scientific PIT/OOS evidence, or trading permission.
No acquisition, retention extension, service modification, or original data
copy is performed. The caller must be within the original retention window.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from aql.observation.contracts import digest
from tools.atlas_stage6_durable import replay

SCHEMA = "aql.factory.stage7.source-intake-wait.v1"


def _need(ok, code):
    if not ok:
        raise ValueError("STAGE7_" + code)


def _sealed(body):
    return {**body, "sha256": digest(body)}


def build_wait_report(source_dir, *, expected_manifest_sha256):
    """Read native Stage6 G1/Core evidence, then report missing strategy truthfully."""
    _need(isinstance(expected_manifest_sha256, str)
          and len(expected_manifest_sha256) == 64
          and all(c in "0123456789abcdef" for c in expected_manifest_sha256),
          "EXTERNAL_MANIFEST_PIN_REQUIRED")
    source = replay(Path(source_dir), expected_manifest_sha256=expected_manifest_sha256)
    consumer = source["native_consumer"]
    _need(source["source_count"] == 2
          and len(source["source_digests"]) == 2
          and len(set(source["source_digests"])) == 2
          and source["manifest_sha256"] == expected_manifest_sha256
          and source["secretary"] == "WAIT" and source["orders"] == 0
          and consumer["ready"] is False
          and len(consumer["source_checksums"]) == 2
          and source["clock"] == "LOCAL_OS_UNVERIFIED",
          "SOURCE_NOT_FAIL_CLOSED")
    # Scanner's native explicit-opportunity issuer requires a genuine sealed
    # independent strategy decision. Stage6 evidence does not contain one.
    # Never call that issuer with a fabricated decision or approval.
    body = {
        "schema": SCHEMA,
        "source_manifest_sha256": expected_manifest_sha256,
        "source_readback_sha256": source["sha256"],
        "source_count": 2,
        "source_digests": source["source_digests"],
        "g1_core_source_checksums": consumer["source_checksums"],
        "scanner_route": "WAIT_EXPLICIT_STRATEGY_DECISION_ABSENT",
        "scanner_opportunity_sha256": None,
        "strategy_decision_sha256": None,
        "secretary": "WAIT",
        "secretary_approval_sha256": None,
        "factory_research_status": "SOURCE_INTAKE_ONLY_NO_STRATEGY_RESULT",
        "factory_consumer_ack_sha256": None,
        "orders": 0,
        "trading_authority": "NONE",
        "historical_pit": "NOT_ATTESTED",
        "source_authenticity": source["source_authenticity"],
        "clock": source["clock"],
    }
    return _sealed(body)


def verify_wait_report(report, *, expected_manifest_sha256):
    _need(type(report) is dict and report.get("schema") == SCHEMA
          and report.get("sha256") == digest({
              k: v for k, v in report.items() if k != "sha256"
          }), "REPORT_SEAL")
    _need(report["source_manifest_sha256"] == expected_manifest_sha256
          and report["source_count"] == 2
          and len(report["source_digests"]) == 2
          and len(report["g1_core_source_checksums"]) == 2
          and report["scanner_route"] == "WAIT_EXPLICIT_STRATEGY_DECISION_ABSENT"
          and report["scanner_opportunity_sha256"] is None
          and report["strategy_decision_sha256"] is None
          and report["secretary"] == "WAIT"
          and report["secretary_approval_sha256"] is None
          and report["factory_research_status"] == "SOURCE_INTAKE_ONLY_NO_STRATEGY_RESULT"
          and report["factory_consumer_ack_sha256"] is None
          and report["orders"] == 0
          and report["trading_authority"] == "NONE"
          and report["historical_pit"] == "NOT_ATTESTED",
          "AUTHORITY_OR_SOURCE_DRIFT")
    return report


def write_immutable_report(report, destination, *, expected_manifest_sha256):
    """Create a separate research-only report, never modify source custody."""
    verify_wait_report(report, expected_manifest_sha256=expected_manifest_sha256)
    path = Path(destination)
    raw = (json.dumps(report, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")
    if path.exists():
        _need(path.is_file() and not path.is_symlink()
              and path.read_bytes() == raw, "IMMUTABLE_CONFLICT")
    else:
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    _need(path.read_bytes() == raw, "REPORT_READBACK")
    return report["sha256"]


def read_immutable_report(destination, *, expected_manifest_sha256):
    path = Path(destination)
    _need(path.is_file() and not path.is_symlink()
          and path.stat().st_size < 65536, "REPORT_PATH_OR_BOUND")
    return verify_wait_report(json.loads(path.read_bytes()),
                              expected_manifest_sha256=expected_manifest_sha256)
