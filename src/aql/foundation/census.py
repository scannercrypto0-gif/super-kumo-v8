"""Bounded classification of a caller-supplied Binance exchangeInfo snapshot.

No exchange calls: incomplete/truncated snapshots are never a complete census.
The caller retains the original snapshot and its acquisition provenance.
"""
import hashlib
import json
import re


def census(snapshot, *, observed_ms, decision_ms, max_symbols=10000):
    if (type(observed_ms) is not int or type(decision_ms) is not int
            or not 0 <= observed_ms <= decision_ms):
        raise ValueError("Unverified snapshot time")
    if type(max_symbols) is not int or not 1 <= max_symbols <= 10000:
        raise ValueError("Invalid census bound")
    rows = snapshot.get("symbols") if isinstance(snapshot, dict) else None
    if not isinstance(rows, list) or len(rows) > max_symbols:
        raise ValueError("Missing or oversized universe; no partial census")
    digest = hashlib.sha256(json.dumps(snapshot, sort_keys=True,
                            separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    names = [r.get("symbol") if isinstance(r, dict) else None for r in rows]
    counts = {}
    for name in names:
        if isinstance(name, str):
            counts[name] = counts.get(name, 0) + 1
    records = []
    for index, row in enumerate(rows):
        name = names[index]
        status, reason = "ERROR", "MALFORMED_SYMBOL"
        if isinstance(name, str) and re.fullmatch(r"[A-Z0-9]{2,32}", name):
            if counts[name] > 1:
                reason = "DUPLICATE_SYMBOL"
            elif not isinstance(row.get("status"), str) or type(row.get("isSpotTradingAllowed")) is not bool:
                reason = "MISSING_MARKET_STATUS"
            elif row["status"] not in {"PRE_TRADING", "TRADING", "POST_TRADING", "END_OF_DAY",
                                       "HALT", "AUCTION_MATCH", "BREAK"}:
                reason = "UNKNOWN_MARKET_STATUS"
            elif row["status"] != "TRADING" or not row["isSpotTradingAllowed"]:
                status, reason = "UNSUPPORTED", "NOT_ACTIVE_SPOT"
            else:
                status, reason = "ELIGIBLE", "ACTIVE_SPOT_METADATA_ONLY"
        records.append(dict(index=index, symbol=name if isinstance(name, str) else None,
                            status=status, reason=reason))
    return dict(schema="aql.g1.census.v1", snapshot_sha256=digest,
                observed_ms=observed_ms, decision_ms=decision_ms,
                discovered=len(rows), records=records,
                counts={s: sum(r["status"] == s for r in records)
                        for s in ("ELIGIBLE", "ERROR", "UNSUPPORTED")},
                scope="supplied snapshot only; metadata eligibility is not decision readiness")
