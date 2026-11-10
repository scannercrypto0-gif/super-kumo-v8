"""Read-only forward evidence bound to the unchanged G2 and Factory reports."""
from collections import Counter
from math import isfinite

from aql.observation.contracts import HORIZONS_MS, digest
from aql.observation.durable_bridge_v1 import require, sha
from aql.observation.prospective import CLOCK_MS, STEP


def _regime(samples, market, cutoff):
    # Regime producers are separate. Admit only self-sealed, timestamped labels
    # that were available at the decision and valid for that instant.
    eligible = [
        item for item in samples
        if item.get("market") == market
        and item.get("label") in ("UP", "DOWN", "SIDEWAYS")
        and all(type(item.get(k)) is int for k in ("as_of_ms", "available_ms", "valid_until_ms"))
        and 0 <= item["as_of_ms"] <= item["available_ms"] <= cutoff < item["valid_until_ms"]
        and sha(item.get("source_sha256"))
        and item.get("sha256") == digest({k: v for k, v in item.items() if k != "sha256"})
    ]
    latest = max((x["as_of_ms"] for x in eligible), default=None)
    selected = {x["sha256"]: x for x in eligible if x["as_of_ms"] == latest}
    if len(selected) != 1:
        return {"label": "UNKNOWN", "reason": "CONFLICT" if selected else "NO_ADMISSIBLE_INPUT"}
    item = next(iter(selected.values()))
    return {"label": item["label"], "receipt": item}


def _window(origin, horizon, as_of, by_open, source_valid):
    due = origin + horizon
    first = ((origin + STEP - 1) // STEP) * STEP
    end = due // STEP * STEP
    expected = range(first, end, STEP)
    row = {"horizon_ms": horizon, "due_ms": due, "expected_bars": len(expected),
           "edge_policy": "FULLY_CONTAINED_BARS_ONLY", "first_open_ms": first,
           "end_exclusive_ms": end, "extrema": None, "receipt_sha256s": []}
    if not source_valid or as_of < due:
        return {**row, "state": "UNKNOWN" if not source_valid else "pending"}
    missing = [opening for opening in expected if opening not in by_open]
    pairs = [by_open[opening] for opening in expected if opening in by_open]
    proofs = [proof for _, proof in pairs]
    late = [proof["open_ms"] for proof in proofs if proof["commit_ms"] > proof["close_ms"] + CLOCK_MS]
    row.update(missing_opens_ms=missing, late_opens_ms=late,
               receipt_sha256s=[proof["g1_receipt_sha256"] for proof in proofs])
    if missing or late:
        return {**row, "state": "missing" if missing else "late"}
    if not pairs or not all(
        isfinite(bar.high) and isfinite(bar.low) and 0 < bar.low <= min(bar.open, bar.close)
        <= max(bar.open, bar.close) <= bar.high for bar, _ in pairs
    ):
        return {**row, "state": "UNKNOWN"}

    def point(field, choose):
        value = choose(getattr(bar, field) for bar, _ in pairs)
        slots = [[proof["open_ms"], proof["close_ms"]] for bar, proof in pairs
                 if getattr(bar, field) == value]
        return {"value": value, "bar_intervals_ms": slots,
                "relative_intervals_ms": [[a - origin, b - origin] for a, b in slots]}

    high, low = point("high", max), point("low", min)
    hi, lo = high["bar_intervals_ms"], low["bar_intervals_ms"]
    order = ("HIGH_BEFORE_LOW" if hi[-1][1] < lo[0][0] else
             "LOW_BEFORE_HIGH" if lo[-1][1] < hi[0][0] else "AMBIGUOUS")
    return {**row, "state": "mature", "extrema": {"high": high, "low": low, "order": order}}


def read_forward_evidence(observer, *, as_of_ms, regime_samples=()):
    """Derive exact as-of evidence, without migrations, writes or inferred fills."""
    from research_wp_r0.aql_factory_prospective_read_v1 import read_prospective_research

    require(observer.read_only, "FORWARD_EVIDENCE_READ_ONLY_REQUIRED")
    g2 = observer.verified_read(as_of_ms=as_of_ms)
    factory = read_prospective_research(observer, as_of_ms=as_of_ms)
    require(factory["g2_sha256"] == g2["sha256"], "FORWARD_G2_FACTORY_MISMATCH")
    by_open = {bar.bar_open: (bar, proof) for bar, proof in observer._parents(as_of_ms)}
    source = {proof["g1_receipt_sha256"]: proof for _, proof in by_open.values()}
    rows, coverage = [], Counter()
    regime_samples = tuple(regime_samples)
    for g2_row in g2["rows"]:
        decision = g2_row["decision"]
        if not decision["opportunity_id"]:
            continue
        origin = decision["cutoff_ms"]
        regimes = {market: _regime(regime_samples, market, origin) for market in ("BTC", "ALT")}
        windows = [_window(origin, horizon, as_of_ms, by_open, g2_row["source_valid"])
                   for horizon in HORIZONS_MS]
        for window, previous in zip(windows, g2_row["horizons"]):
            window["legacy_g2_state"] = previous["state"]
            for market, regime in regimes.items():
                coverage[f'{market}:{regime["label"]}:{window["horizon_ms"]}:{window["state"]}'] += 1
        rows.append({"opportunity_id": decision["opportunity_id"], "cutoff_ms": origin,
                     "decision_sha256": g2_row["decision_sha256"], "regimes": regimes,
                     "windows": windows})
    body = {"schema": "aql.g2.forward-evidence.v1", "as_of_ms": as_of_ms,
            "g2_sha256": g2["sha256"], "factory_sha256": factory["sha256"],
            "evidence_mode": g2["run"]["evidence_mode"], "historical_pit": "NOT_ATTESTED",
            "source_receipts": source, "coverage": dict(coverage), "rows": rows,
            "trading_authority": "NONE"}
    return {**body, "sha256": digest(body)}
