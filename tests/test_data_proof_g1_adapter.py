"""Actual G1 MarketBar proof adapter checks (no provider timing fabricated)."""
import pytest
from aql.models.bar import MarketBar
from aql.data_proof import ProofError
from aql.data_proof_g1_adapter import from_persisted_market_bar


def bar():
    return MarketBar(symbol="BTCUSDT", interval="1m", bar_open=0,
                     bar_close=59999, open=1., high=2., low=1.,
                     close=2., volume=5., is_final=True,
                     source="binance_ws", ingested_at=60001).with_checksum()


def test_market_bar_identity_digest_and_local_only_evidence():
    b = bar()
    v = from_persisted_market_bar(b, local_commit_evidence_ref="journal:receipt")
    assert v.logical_bar_id == b.stable_key()
    assert v.payload_digest == b.compute_checksum()
    assert v.first_local_seen_ms == 60001
    assert v.ingest_committed_ms is None
    assert v.provider_available_ms is None
    assert v.clock_evidence_ref is None
    assert v.eligibility(70000) == "UNKNOWN_PENDING_EVIDENCE"


def test_non_final_and_tampered_bar_fail_closed():
    b = bar()
    b.is_final = False
    with pytest.raises(ProofError):
        from_persisted_market_bar(b)
    b = bar()
    b.close = 99.
    with pytest.raises(ProofError):
        from_persisted_market_bar(b)
