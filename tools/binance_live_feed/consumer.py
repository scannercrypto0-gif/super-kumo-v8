"""Read-only mapping to native Core, G2 and Scanner/Factory research contracts."""
from aql.models.bar import MarketBar
from aql.observation.contracts import CONTEXT_KEYS, ContextValue, DecisionSnapshot
from tools.scanner_strategy_f.research_e2e_diagnostic import _eval_strategy
from tools.binance_live_feed.feed import hash_bytes, canonical, need


def project(view, *, embargo_or_holdout=(), definition=None):
    if view["status"] != "OFFLINE_RESEARCH_INPUT_READY":
        return dict(state="UNKNOWN", reason=view.get("reason"), signal=None, authority="NONE")
    cutoff = view["as_of_ms"]
    record = view["records"]["15m"]
    material = record["material"]
    if any(start <= cutoff < end or (material["open_ms"] < end and material["end_ms_exclusive"] > start)
           for start, end in embargo_or_holdout):
        return dict(state="UNKNOWN", reason="EMBARGO_OR_HOLDOUT", signal=None, authority="NONE")
    bar = MarketBar.from_dict(view["bars"]["15m"])
    need(bar.is_final and bar.checksum == bar.compute_checksum()
         and bar.bar_close <= record["event_ms"] <= record["receive_ms"] <= record["commit_ms"] <= cutoff,
         "NATIVE_BAR_CAUSALITY")
    snapshot = DecisionSnapshot(
        opportunity_key=bar.stable_key(), source=bar.source, event_ms=record["event_ms"],
        receipt_ms=record["receive_ms"], decision_ms=cutoff, disposition="observed",
        context={k: ContextValue(None,None,None,None,"NOT_IN_SCOPE") for k in CONTEXT_KEYS},
        freshness_limit_ms=5000)
    # Same native Scanner AST / Factory indicator kernel. This bounded seam
    # passes a single causal mark; lookbacks remain UNKNOWN until sufficient
    # separately admitted inputs exist.
    shaped = dict(bar_open_ms=bar.bar_open, bar_close_ms=bar.bar_close,
                  **{k:material[k] for k in ("open","high","low","close","volume")})
    diagnostic = _eval_strategy(definition, [shaped])[0][1] if definition is not None else "NOT_EVALUATED"
    return dict(state="OBSERVED_FIXTURE", snapshot_sha256=snapshot.snapshot_id,
                native_bar_sha256=bar.checksum, record_sha256=hash_bytes(canonical(record)),
                diagnostic=diagnostic, signal=None, authority="NONE", actual_fills=None,
                execution="UNKNOWN", first_known_at_ms=None)
