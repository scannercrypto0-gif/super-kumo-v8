"""Read-only, freshness- and gap-aware SQLite contract for downstream consumers."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from tools.realtime_market_feed.service import normalize_symbols, utc_ms


def read_snapshot(
    database: str | Path,
    symbols: str,
    *,
    now_ms: int | None = None,
    history_lookback_ms: int = 86_400_000,
    max_trade_age_ms: int = 30_000,
    max_quote_age_ms: int = 10_000,
    max_bar_age_ms: int = 120_000,
) -> dict:
    """Read prices without changing the store; stale inputs and recent gaps block use.

    Values stay as provider decimal strings. Consumers must still apply their
    own indicator warmup and strategy-specific history requirements.
    """
    requested = normalize_symbols(symbols)
    now_ms = utc_ms() if now_ms is None else now_ms
    cutoff = now_ms - history_lookback_ms
    uri = Path(database).resolve().as_uri() + "?mode=ro"
    db = sqlite3.connect(uri, uri=True)
    db.row_factory = sqlite3.Row
    items, blockers = [], []
    try:
        # Keep every symbol and integrity decision on one SQLite snapshot.
        db.execute("BEGIN")
        conflict_events = db.execute(
            "SELECT at_ms,detail FROM service_event "
            "WHERE kind='FINAL_BAR_CONFLICT' AND at_ms>=? ORDER BY id",
            (cutoff,),
        ).fetchall()
        conflicts_by_symbol = {}
        for event in conflict_events:
            detail = str(event["detail"])
            symbol, separator, opened = detail.partition(":")
            if not separator or not symbol or not opened.isdecimal():
                blockers.append("UNSCOPED_FINAL_BAR_CONFLICT")
                continue
            conflicts_by_symbol.setdefault(symbol.upper(), []).append(int(opened))
        for symbol in requested:
            trade = db.execute("SELECT * FROM latest_trade WHERE symbol=?", (symbol.upper(),)).fetchone()
            quote = db.execute("SELECT * FROM latest_quote WHERE symbol=?", (symbol.upper(),)).fetchone()
            bar = db.execute("""SELECT * FROM final_bar WHERE symbol=? AND interval='1m'
                                ORDER BY open_ms DESC LIMIT 1""", (symbol.upper(),)).fetchone()
            gaps = db.execute("""SELECT start_ms,end_ms,reason FROM open_gap
                                 WHERE symbol=? AND interval='1m' AND status='OPEN' AND end_ms>?
                                 ORDER BY start_ms""", (symbol.upper(), cutoff)).fetchall()
            missing = []
            for label, row, column, maximum in (
                ("TRADE", trade, "received_ms", max_trade_age_ms),
                ("QUOTE", quote, "received_ms", max_quote_age_ms),
                ("FINAL_BAR", bar, "received_ms", max_bar_age_ms),
            ):
                if row is None:
                    missing.append(label + "_MISSING")
                else:
                    age = max(0, now_ms-int(row[column]))
                    if age > maximum:
                        missing.append(label + "_STALE")
            if gaps:
                missing.append("OPEN_HISTORY_GAP")
            conflict_opens = conflicts_by_symbol.get(symbol.upper(), [])
            if any(opened >= cutoff and opened <= now_ms for opened in conflict_opens):
                missing.append("FINAL_BAR_CONFLICT")
            item = {
                "symbol": symbol.upper(),
                "trade": dict(trade) if trade else None,
                "quote": dict(quote) if quote else None,
                "latest_final_bar": dict(bar) if bar else None,
                "open_gaps": [dict(g) for g in gaps],
                "fresh": not missing,
                "blockers": missing,
            }
            items.append(item)
            blockers.extend(f"{symbol.upper()}:{reason}" for reason in missing)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return {
        "schema": "atlas.realtime-market-feed.consumer-snapshot.v1",
        "as_of_ms": now_ms,
        "history_cutoff_ms": cutoff,
        "symbols": items,
        "status": "LIVE_FRESH" if not blockers else "HELD",
        "blockers": blockers,
        "orders": 0,
        "trading_authority": "NONE",
    }
