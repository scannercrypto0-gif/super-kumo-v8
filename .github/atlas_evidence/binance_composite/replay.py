"""Fresh offline joined acceptance of the pinned archive and live-feed adapters."""
import json
from pathlib import Path
import sys
from unittest.mock import patch

from tools.historical_source_qa import qa
from tools.historical_source_qa.test_qa import HistoricalQA, native
from tools.binance_live_feed import simulation
from tools.binance_live_feed.interface import check_contract
from tools.binance_live_feed import test_feed


PINS = {
    "304": "e0e08a8381a8cceaaa44d6ae2721e9cb0d004648",
    "305": "e440b91f05becc1a523e8249d341874d4c5f6434",
    "289": "1ff3d13a3dfd1337bae0659dd03550b764c8799c",
    "main": "90af9794880cbeb00e7e974bfa906ff5e9666183",
}


def replay(root):
    root.mkdir()
    archive = HistoricalQA()
    archive.root = root
    archive.start = 1707091200000
    end = archive.start + qa.FIXED["15m"]
    control = native(archive.start, qa.FIXED["15m"], volume="0.00000000000000000015", trades="15")
    admitted = archive.admission([control], interval="15m")
    derived = qa.derive(archive.admission(archive.minutes(15)), "15m", end)
    assert qa.compare_native_15m(derived, admitted)["status"] == "MATCH"
    historical = qa.validate_envelope(admitted["records"][0])
    assert historical["product"] == "BINANCE_VISION"
    assert historical["exchange_event_at_ms"] is None
    with test_feed.pytest.raises(ValueError):
        qa.derive(admitted, "1m", end)

    with patch.object(simulation, "END", end):
        live = simulation.run(root / "live")
    reference = json.loads(Path("tools/historical_source_qa/interface.json").read_text(encoding="utf-8"))
    for channel, envelope in live["source_envelopes"].items():
        check_contract(reference, envelope)
        assert envelope["market"] == historical["market"]
        assert envelope["source_manifest_sha256"] != historical["source_manifest_sha256"]
        assert envelope["product"] == "BINANCE_SPOT_WS"
        assert envelope["evidence_class"] == historical["evidence_class"] == "TEST_ONLY"
        assert envelope["pit"] == historical["pit"] == "NOT_ATTESTED"
        for field in ("publisher_first_available_at_ms", "actual_fill"):
            assert envelope[field] is historical[field] is None
        if channel in ("1m", "15m"):
            assert qa.validate_envelope(envelope)["is_final"]
            assert envelope["end_exclusive_ms"] == end
            assert end <= envelope["exchange_event_at_ms"] <= envelope["received_at_ms"] <= envelope["committed_at_ms"]
            with test_feed.pytest.raises(ValueError, match="UNSUPPORTED_EVIDENCE_PROMOTION"):
                qa.validate_envelope({**envelope, "actual_fill": "synthetic"})
            with test_feed.pytest.raises(ValueError, match="OFFLINE_CONTRACT_ONLY"):
                qa.validate_envelope({**envelope, "evidence_class": "RETROSPECTIVE_NON_PIT"})
    assert live["source_envelopes"]["15m"]["open_ms"] == historical["open_ms"]
    assert live["read_only_consumer"]["signal"] is None
    assert live["read_only_consumer"]["execution"] == "UNKNOWN"
    assert live["surge"]["rest_headroom_pct"] == 50

    witnesses = {
        "crash_ack": test_feed.test_hard_crash_after_data_commit,
        "shared_ip_429_418": test_feed.test_429_5xx_half_open_418_shared_and_persistent,
        "process_shared_ip": test_feed.test_separate_processes_share_one_ip_ledger,
    }
    session_checks = {
        "read_only_kernel": test_feed.test_native_scanner_factory_kernel_and_stale_guard,
        "gap_duplicate_reconnect": test_feed.test_trade_gap_recovery_and_fresh_generation,
        "late_final": test_feed.test_late_final_never_becomes_actionable,
        "revision": test_feed.test_revision_rejected_and_original_retained,
        "finality_and_stale": test_feed.test_finality_native_contract_and_stale,
    }
    for name, verify in {**witnesses, **session_checks}.items():
        path = root / name
        path.mkdir()
        if name in session_checks:
            quota = simulation.Quota(path / "quota.sqlite", simulation.Limits(40, connections=6, subscriptions=8))
            verify(simulation.Session(simulation.Feed(path / "feed"), quota))
        else:
            verify(path)
    archive.test_duplicate_reorder_revision_and_bytes()
    archive.test_gap_zero_trade_future_and_incomplete()
    result = dict(pins=PINS, status="PASS_COMBINED_OFFLINE", live_pilot="NOT_RUN",
                  historical_record_sha256=historical["sha256"], simulation=live,
                  witnesses=sorted([*witnesses, *session_checks, "archive_integrity", "archive_gap"]))
    receipt = simulation.canonical(result)
    (root / "receipt.json").write_bytes(receipt)
    return simulation.hash_bytes(receipt)


if __name__ == "__main__":
    output = Path(sys.argv[1])
    output.mkdir()
    first, second = (replay(output / name) for name in ("first", "second"))
    assert first == second
    print(f"PASS_COMBINED_OFFLINE SHA256={first} repeats=2 failures=0 skips=0")
