from aql.collector.binance_collector import BinanceCollector


def test_reconnect_budget_resets_only_after_finalized_bar_progress():
    assert BinanceCollector._attempt_after_session(7, True) == 0
    assert BinanceCollector._attempt_after_session(7, False) == 7


def test_healthy_sessions_do_not_accumulate_toward_permanent_exit():
    attempt = 0
    for _ in range(100):
        # A session made progress, then disconnected.
        attempt = BinanceCollector._attempt_after_session(attempt, True)
        attempt += 1
    assert attempt == 1

