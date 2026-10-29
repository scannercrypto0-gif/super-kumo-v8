"""Predeclared synthetic-only sensitivity candidates from Core issue 175."""
from dataclasses import dataclass
from .core_dev_b0_adapter import build_synthetic_candidate, ExecutionDenied
from .historical_dev_exits_v1 import Config, digest

# source lag ms, execution lag ms, full spread bp, slip bp/side, fee bp/side
SENSITIVITY = {
 "S00":(1000,1000,2,5,10), "S01":(5000,1000,2,5,10),
 "S02":(60000,1000,2,5,10), "S03":(1000,5000,2,5,10),
 "S04":(1000,60000,2,5,10), "S05":(1000,1000,10,5,10),
 "S06":(1000,1000,2,10,10), "S07":(1000,1000,2,25,10),
 "S08":(1000,1000,2,5,20), "S09":(60000,60000,10,25,20),
 "S10":(1000,1000,0,0,0), "S11":(120000,1000,10,50,20),
}

@dataclass(frozen=True)
class SensitivityCase:
    scenario_id: str
    source_lag_ms: int
    execution_lag_ms: int
    candidate: object

def build_synthetic_sensitivity(bars, source):
    """Twelve independent engine replays; no real-data study authorization."""
    if not isinstance(source, dict) or source.get("version") != "synthetic-b0":
        raise ExecutionDenied("SYNTHETIC_SOURCE_ONLY")
    if not isinstance(bars, list) or not all(isinstance(b, dict) and b.get("modeled_quote") is True for b in bars):
        raise ExecutionDenied("SYNTHETIC_QUOTE_REQUIRED")
    results = {}
    for sid, (src_lag, exec_lag, spread, slip, fee) in SENSITIVITY.items():
        # New bar copies, no mutation of caller input. Never add source lag twice.
        adjusted = [{**bar, "available_ms":bar["close_ms"]+1+src_lag} for bar in bars]
        pinned = {**source, "rows_sha256":digest(adjusted)}
        cfg = Config(initial_cash=1000, quantity=.001, warmup_bars=252,
                     latency_ms=exec_lag, spread_bps=spread,
                     slippage_bps=slip, fee_bps=fee, max_signal_age_ms=120000,
                     indicator_exit=True, tp_fraction=None, sl_fraction=None)
        candidate = build_synthetic_candidate(adjusted, pinned, config=cfg)
        results[sid] = SensitivityCase(sid,src_lag,exec_lag,candidate)
    return results
