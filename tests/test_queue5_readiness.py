"""Regression for native Windows capture bytes and interrupted short writes."""
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from research_wp_r0.aql_f1_decision_capture_v1 import CaptureError, write_original_candidate
from test_aql_f1_decision_capture_v1 import fixture
from research_wp_r0.aql_queue5_readiness_v1 import inspect_host_claim


def test_partial_write_is_preserved_and_rejected(tmp_path):
    record, registry = fixture()
    original = os.write
    path = tmp_path / "partial.jsonl"
    with patch("os.write", side_effect=lambda fd, data: original(fd, data[:-1])):
        with pytest.raises(CaptureError, match="DURABLE_SHORT_WRITE"):
            write_original_candidate(path, record, registry)
    assert path.exists() and path.read_bytes() and not path.read_bytes().endswith(b"\n")


def test_owner_host_claim_is_bounded_and_reverse_chronology_fails():
    import json
    claim = json.loads((Path(__file__).resolve().parents[1] /
        "docs/evidence/queue5-owner-reported-host.json").read_text())
    checked = inspect_host_claim(claim)
    assert checked["original_receipt_bytes_verified"] is False
    assert checked["automatic_fault_recovery"] == "UNVERIFIED"
    claim["next_segment"]["id"] = 1
    with pytest.raises(ValueError, match="QUEUE5_HOST_REPORTED_CHRONOLOGY"):
        inspect_host_claim(claim)
