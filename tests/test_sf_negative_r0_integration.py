"""Negative-only interop: rejected Core data cannot create synthetic R0 trades."""
import copy

from research_wp_r0.factory_exam import freeze_manifest, freeze_protocol, run_route
from research_wp_r0.factory_exam_example import fixture
from research_wp_r0.pre_indicator_boundary import block_unproven_opportunities


def test_blocked_core_revision_preserves_r0_slots_and_never_trades():
    dna, events, cfg = fixture()
    # A missing/unverified Core evidence envelope blocks every externally
    # scheduled slot. This is deliberately negative-only (no Core imports).
    schedule = [
        {"event_id": event["event_id"], "version_id": "unverified-" + event["event_id"]}
        for event in events
    ]
    report = block_unproven_opportunities(
        scheduled=schedule, envelope={}, pinned_digest="a"*64,
        cutoff_ms=events[0]["cutoff_ms"])
    assert report["scheduled_total"] == len(events)
    assert report["blocked_total"] == len(events)
    assert all(item["indicator_features"] is None for item in report["slots"])
    assert all(item["execution_request"] is None for item in report["slots"])

    withheld = copy.deepcopy(events)
    assert [x["event_id"] for x in withheld] == [x["event_id"] for x in events]
    for event in withheld:
        event["features"] = None
    manifest = freeze_manifest(dna, withheld)
    assert len(manifest.spec["rows"]) == len(events)
    assert all(row["decision"] is None for row in manifest.spec["rows"])
    protocol = freeze_protocol(manifest, expected_manifest_digest=manifest.digest, config=cfg)
    for arm in ("ALWAYS", "REGIME"):
        outcome = run_route(manifest, protocol,
                            expected_manifest_digest=manifest.digest,
                            expected_protocol_digest=protocol.digest, arm=arm).spec
        assert len(outcome["outcomes"]) == len(events)
        assert all(x["status"] == "UNKNOWN" for x in outcome["outcomes"])
        assert not any(x["kind"] == "SIMULATED_ENTRY" for x in outcome["ledger"])
