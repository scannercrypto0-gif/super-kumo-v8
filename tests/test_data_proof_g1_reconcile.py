"""Offline journal repair is bounded, idempotent and preserves local timing."""
from aql.data_proof_g1_reconcile import reconcile_persisted_observations
from aql.data_proof_registry import RevisionRegistry
from aql.models.bar import MarketBar


def _bar():
    return MarketBar(symbol="BTCUSDT", interval="1m", bar_open=0,
                     bar_close=59999, open=1., high=2., low=1.,
                     close=2., volume=5., is_final=True,
                     source="binance_ws", ingested_at=60001).with_checksum()


class PersistedJournal:
    def __init__(self):
        self.calls = []

    def replay(self, *args, **kwargs):
        self.calls.append(kwargs)
        assert kwargs["persisted_only"] is True
        assert kwargs["limit"] == 1
        return [_bar()]


def test_bounded_repair_and_idempotent_restart(tmp_path):
    registry = RevisionRegistry(tmp_path / "proof.sqlite")
    journal = PersistedJournal()
    first = reconcile_persisted_observations(journal, registry,
        symbol="BTCUSDT", interval="1m", limit=1)
    assert first["added"] == 1 and first["bounded_prefix_only"]
    registry.close()
    reopened = RevisionRegistry(tmp_path / "proof.sqlite")
    second = reconcile_persisted_observations(journal, reopened,
        symbol="BTCUSDT", interval="1m", limit=1)
    assert second["added"] == 0 and second["existing"] == 1
    assert reopened.revisions("BTCUSDT:1m:0")[0].ingest_committed_ms is None
    reopened.close()
