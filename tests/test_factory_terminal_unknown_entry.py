"""Synthetic-only terminal execution boundary regression."""
from research_wp_r0.historical_dev_exits_v1 import Config, digest, replay_contract_fixture

def test_terminal_entry_without_eligible_open_is_unknown():
    bars=[]
    for i in range(22):
        t=i*60000
        bars.append(dict(open_ms=t,close_ms=t+59999,open=100.0,high=101.0,
                         low=99.0,close=100.0,volume=1.0,
                         available_ms=t+61000,modeled_quote=True))
    source=dict(version="synthetic-terminal",reference="fixture:terminal",
                archive_sha256="a"*64,rows_sha256=digest(bars),
                availability_evidence="UNKNOWN",correction_evidence="PINNED_VERSION_ONLY")
    signals=[dict(bar_open_ms=bars[-1]["open_ms"],action="ENTER_LONG",
                  available_ms=bars[-1]["available_ms"])]
    result=replay_contract_fixture(bars,source=source,signals=signals,config=Config())
    factual=result["paths"]["FACTUAL"]
    assert factual["status"]=="UNKNOWN_UNRESOLVED"
    assert factual["realized_pnl"] is None
    assert factual["modeled_equity_return"] is None
    assert factual["opportunities"][-1]["status"]=="UNKNOWN_NO_ELIGIBLE_OPEN"
    assert any(e["kind"]=="UNKNOWN_NO_ENTRY_OPEN" for e in factual["ledger"])
    assert factual["scheduled_denominator"]==1
