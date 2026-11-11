"""Read-only final-candle projection for the native Scanner diagnostic kernel."""
from decimal import Decimal, InvalidOperation

from .contracts import canonical, digest, timestamp
from .discoverer_view import seal
from .source_view import require, is_pin


def scanner_monitor_view(view, expected, *, opens, step_ms):
    require(len(canonical(view))<=256_000 and is_pin(expected)
            and view["digest"]==expected==digest({k:v for k,v in view.items() if k!="digest"})
            and view["schema"]=="aql.core.source-view.v1" and view["use"]=="MONITOR_ONLY",
            "SCANNER_VIEW_PIN")
    starts = tuple(opens)
    require(type(step_ms) is int and step_ms>0 and 1<=len(starts)<=64
            and len(starts)==len(view["slots"])
            and all(timestamp(v)%step_ms==0 for v in starts)
            and all(b-a==step_ms for a,b in zip(starts,starts[1:])), "SCANNER_GRID")
    bars, unknown = [],{}
    for start, slot in zip(starts,view["slots"]):
        require(slot["key"]==f"bar:{start}","SCANNER_SLOT_BINDING")
        if slot["reason"] is not None:
            unknown[str(start)] = slot["reason"]
            continue
        r = slot["record"]
        close = start+step_ms-1
        require(digest(r)==slot["digest"] and r["grade"]=="TEST_ONLY" and r["final"] is True
                and r["source"]==view["source"] and r["market"]==view["market"]
                and r["event_at"]==close<=r["published_at"]<=r["received_at"]<=r["committed_at"]<=view["cutoff"],
                "SCANNER_BAR_EVIDENCE")
        value = r["value"]
        require(set(value)=={"open","high","low","close","volume"}
                and all(type(v) is str and 0<len(v)<=40 for v in value.values()), "SCANNER_DECIMAL")
        try:
            o,h,l,c,v = (Decimal(value[k]) for k in ("open","high","low","close","volume"))
        except InvalidOperation as exc:
            raise ValueError("SCANNER_DECIMAL") from exc
        require(all(x.is_finite() and abs(x)<=Decimal("1e18") for x in (o,h,l,c,v))
                and 0<l<=min(o,c)<=max(o,c)<=h and v>=0,"SCANNER_OHLC")
        bars.append(dict(bar_open_ms=start,bar_close_ms=close,**value))
    return seal(dict(schema="aql.core.scanner-monitor-fixture.v1",source_view_sha256=expected,
                     bars=bars if not unknown else [],unknown=unknown,
                     expected_count=len(starts),status="UNKNOWN" if unknown else "READY_FIXTURE",
                     mode="MONITOR_ONLY",authority="NONE",first_known_at_ms=None))
