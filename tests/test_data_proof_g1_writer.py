"""Persisted MarketBar custody survives reopen; conflict never overwrites."""
import pytest
from aql.data_proof import ProofError
from aql.data_proof_g1_writer import G1RevisionWriter
from aql.data_proof_registry import RevisionRegistry
from aql.models.bar import MarketBar


def _bar(close=2.):
    return MarketBar(symbol="BTCUSDT", interval="1m", bar_open=0,
                     bar_close=59999, open=1., high=2., low=1.,
                     close=close, volume=5., is_final=True,
                     source="binance_ws", ingested_at=60001).with_checksum()


def test_writer_persists_reopens_and_replays(tmp_path):
    path = tmp_path / "observations.sqlite"
    registry = RevisionRegistry(path)
    writer = G1RevisionWriter(registry)
    assert writer.observe(_bar()) == "APPENDED"
    assert writer.observe(_bar()) == "ALREADY_PRESENT"
    registry.close()
    reopened = RevisionRegistry(path)
    versions = reopened.revisions("BTCUSDT:1m:0")
    assert len(versions) == 1
    assert versions[0].payload_digest == _bar().compute_checksum()
    assert versions[0].provider_available_ms is None
    assert versions[0].ingest_committed_ms is None
    assert versions[0].eligibility(70000) == "UNKNOWN_PENDING_EVIDENCE"
    reopened.close()


def test_conflicting_payload_is_not_implicit_correction(tmp_path):
    registry = RevisionRegistry(tmp_path / "observations.sqlite")
    writer = G1RevisionWriter(registry)
    assert writer.observe(_bar()) == "APPENDED"
    with pytest.raises(ProofError, match="G1_CONTENT_CONFLICT"):
        writer.observe(_bar(close=1.5))
    assert len(registry.revisions("BTCUSDT:1m:0")) == 1
    registry.close()
