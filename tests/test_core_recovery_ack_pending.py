"""AIARC-025: store commit succeeds but journal ACK fails; report and restart must not lie."""
from unittest.mock import patch

from aql.journal.durable_journal import DurableJournal
from aql.models.bar import MarketBar
from aql.pipeline import _run_gap_recovery
from aql.recovery.gap_recovery import RecoveryReport
from aql.storage.operational_store import OperationalStore


def test_store_write_with_failed_ack_reports_pending_and_restart_replays(tmp_path):
    journal_path = str(tmp_path / "journal.sqlite")
    store_path = str(tmp_path / "store.sqlite")
    journal = DurableJournal(journal_path)
    store = OperationalStore(store_path)
    bar = MarketBar("BTCUSDT", "1m", 0, 59999, 100., 101., 99., 100.,
                    1., True, "synthetic", 60000).with_checksum()

    # A successful REST fetch is injected; this test does not use the network.
    # Use the actual recover_gap implementation with an injected provider response.
    rows = [[0, "100", "101", "99", "100", "1", 59999]]
    with patch("aql.recovery.gap_recovery._fetch_klines", return_value=(rows, 2)):
        with patch.object(journal, "mark_persisted", side_effect=OSError("injected ACK failure")):
            result = _run_gap_recovery(journal, store, "BTCUSDT", "1m", 0, 60000)

    assert result["recovery_inserted"] == 1
    assert result["recovery_errors"] == 1
    assert result["recovery_ack_pending"] == 1
    assert store.count("BTCUSDT", "1m") == 1
    assert len(journal.replay(pending_only=True)) == 1

    # Restart must ACK the already present row without a second store insertion.
    reopened = DurableJournal(journal_path)
    replayed, inserted, errors, _ = reopened.startup_reconcile(
        OperationalStore(store_path), "BTCUSDT", "1m")
    assert (replayed, inserted, errors) == (0, 0, 0)
    assert reopened.replay(pending_only=True) == []
    assert store.count("BTCUSDT", "1m") == 1
