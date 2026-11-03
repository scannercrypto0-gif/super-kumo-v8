"""P1-A retrospective opportunity-outcome report library.

Pure offline summarization of 653 original Jan 2024 BTCUSDT 15m opportunities
against 4h/24h/72h market-only future windows.

Contract:
  scope      = RETROSPECTIVE_NON_PIT_DESCRIPTIVE
  evidence   = BASE_DESCRIPTIVE only
  SHADOW     = NOT_EVALUABLE_NO_PREDECLARED_PAIRED_CANDIDATE
  F1         = MISSING_ORIGINAL_CAPTURE
  G2         = NOT_CONNECTED
  fills/PnL  = NOT_INFERRED (no fees for NO_SIGNAL/REJECTED)
  direction  = NULL unless independently proven in original receipts

Compatible with Factory #77/6597621790 proposed
``aql-p1-original-opportunity-outcomes.v1`` JSON rows.

This module is PURE Python stdlib.  It never imports Core producer,
Work's private data index, Factory PR #209 W1 files, or G2 runtime.
No network, no real bar data, no hardcoded real results.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass, asdict, field
from typing import Any, Sequence

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "aql.p1a-report-library.v1"
POLICY_VERSION = "P1A-RETROSPECTIVE-DESCRIPTIVE-v1"
EVIDENCE_CLASS = "RETROSPECTIVE_NON_PIT"
SCOPE = "RETROSPECTIVE_NON_PIT_DESCRIPTIVE"

BAR_MS = 900_000        # 15 min in ms
HORIZONS_MS = (14_400_000, 86_400_000, 259_200_000)  # 4h / 24h / 72h
HORIZON_HOURS = (4, 24, 72)
HORIZON_BARS = (16, 96, 288)    # expected 15m bars per horizon

ORIGINAL_DENOMINATOR = 653
ORIGINAL_F3_COUNTS = {"NO_SIGNAL": 616, "REJECTED": 27, "TRIGGERED": 10}

F3_DISPOSITIONS = frozenset(("NO_SIGNAL", "REJECTED", "TRIGGERED",
                              "OPEN_UNRESOLVED", "UNKNOWN", "BLOCKED"))
COVERAGE_STATES = frozenset(("COMPLETE", "CENSORED", "UNKNOWN"))

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class P1AError(ValueError):
    """Raised for contract violations; never silently repaired."""


# ---------------------------------------------------------------------------
# Row schema — one per (opportunity × horizon)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class P1ARow:
    """Typed immutable row: one original opportunity × one horizon.

    All fields are deliberately primitive (str, int, float, None) for clean
    JSON serialization without custom encoders.
    """
    # Identity (exact C2 four-tuple)
    trial_id: str
    opportunity_id: str
    producer_event_id: str
    envelope_sha256: str

    # Decision time
    decision_cutoff_ms: int
    decision_ms: int

    # Original F3 outcome
    f3_disposition: str                  # NO_SIGNAL / REJECTED / TRIGGERED / …
    f3_reason_code: str | None

    # Original direction — null unless proven in source bytes
    original_direction: str | None       # "LONG" / "SHORT" / None

    # Horizon
    horizon_hours: int                   # 4 / 24 / 72
    horizon_ms: int                      # 14_400_000 / …
    window_start_ms: int                 # == decision_cutoff_ms
    window_end_exclusive_ms: int         # window_start + horizon_ms
    expected_bars: int                   # 16 / 96 / 288

    # Coverage
    coverage_status: str                 # COMPLETE / CENSORED / UNKNOWN
    coverage_reason: str | None          # e.g. ARCHIVE_END_CENSORED / GAP

    # Market-only unsigned excursion metrics (non-directional)
    # Present ONLY when coverage_status == "COMPLETE"
    observed_bars: int | None
    market_high_pct: float | None        # (max_high / ref_open) - 1
    market_low_pct: float | None         # (min_low  / ref_open) - 1 ; ≤ 0
    market_return_pct: float | None      # (close_at_end / ref_open) - 1

    # Directional signed excursion (null unless original_direction is set)
    mfe: float | None                    # max favorable excursion
    mae: float | None                    # max adverse excursion  ; ≥ 0

    # Explicitly NOT computed:
    fills: None = field(default=None, repr=False)      # never inferred
    pnl: None = field(default=None, repr=False)        # never inferred
    f1_capture: str = field(default="MISSING_ORIGINAL_CAPTURE", repr=False)
    g2_status: str = field(default="NOT_CONNECTED", repr=False)
    shadow_status: str = field(
        default="NOT_EVALUABLE_NO_PREDECLARED_PAIRED_CANDIDATE", repr=False
    )
    evidence_class: str = field(default=EVIDENCE_CLASS, repr=False)

    def __post_init__(self) -> None:
        if not self.trial_id or not self.opportunity_id:
            raise P1AError("empty C2 identity field")
        if not _is_sha256(self.envelope_sha256):
            raise P1AError("envelope_sha256 not a 64-char hex digest")
        if self.f3_disposition not in F3_DISPOSITIONS:
            raise P1AError(f"unknown F3 disposition: {self.f3_disposition!r}")
        if self.original_direction not in (None, "LONG", "SHORT"):
            raise P1AError(f"invalid direction: {self.original_direction!r}")
        if self.horizon_hours not in HORIZON_HOURS:
            raise P1AError(f"unsupported horizon_hours: {self.horizon_hours}")
        if self.coverage_status not in COVERAGE_STATES:
            raise P1AError(f"unknown coverage_status: {self.coverage_status!r}")
        if self.coverage_status == "COMPLETE":
            if self.observed_bars != self.expected_bars:
                raise P1AError("COMPLETE row must have observed_bars == expected_bars")
            if self.market_high_pct is None or self.market_low_pct is None:
                raise P1AError("COMPLETE row must have market excursion metrics")
        else:
            # Non-COMPLETE rows must have null metrics — no fabricated numbers
            for attr in ("market_high_pct", "market_low_pct",
                         "market_return_pct", "mfe", "mae"):
                if getattr(self, attr) is not None:
                    raise P1AError(
                        f"non-COMPLETE row must not have {attr} (coverage={self.coverage_status})"
                    )
        # Directional metrics require proven direction
        if self.original_direction is None:
            if self.mfe is not None or self.mae is not None:
                raise P1AError(
                    "mfe/mae require original_direction — not inferred for "
                    "NO_SIGNAL/REJECTED"
                )
        # NO_SIGNAL / REJECTED must never carry fill/PnL
        if self.f3_disposition in ("NO_SIGNAL", "REJECTED"):
            if self.fills is not None or self.pnl is not None:
                raise P1AError("NO_SIGNAL/REJECTED must not carry fills/pnl")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_sha256(v: Any) -> bool:
    return (
        isinstance(v, str)
        and len(v) == 64
        and all(c in "0123456789abcdef" for c in v)
    )


def _canonical_bytes(obj: Any) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _identity_key(row_or_dict: Any) -> tuple:
    if isinstance(row_or_dict, dict):
        d = row_or_dict
    else:
        d = asdict(row_or_dict)
    return (
        d["trial_id"],
        d["opportunity_id"],
        d["producer_event_id"],
        d["envelope_sha256"],
    )


# ---------------------------------------------------------------------------
# Opportunity input record (raw, pre-row)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OpportunityInput:
    """One original decision, as supplied by Work's read-only index.

    This struct never reaches the test suite with real private bytes;
    tests use TEST_ONLY synthetic fixtures.
    """
    trial_id: str
    opportunity_id: str
    producer_event_id: str
    envelope_sha256: str
    decision_cutoff_ms: int
    decision_ms: int
    f3_disposition: str
    f3_reason_code: str | None
    original_direction: str | None    # None unless proven in original source bytes

    def __post_init__(self) -> None:
        if not self.trial_id or not self.opportunity_id:
            raise P1AError("empty opportunity identity")
        if not _is_sha256(self.envelope_sha256):
            raise P1AError("envelope_sha256 invalid")
        if self.f3_disposition not in F3_DISPOSITIONS:
            raise P1AError(f"unknown F3 disposition: {self.f3_disposition!r}")
        if self.original_direction not in (None, "LONG", "SHORT"):
            raise P1AError(f"invalid direction: {self.original_direction!r}")
        if self.decision_cutoff_ms % BAR_MS != 0:
            raise P1AError("decision_cutoff_ms must be bar-aligned")
        if self.decision_ms < self.decision_cutoff_ms:
            raise P1AError("decision_ms < decision_cutoff_ms")


# ---------------------------------------------------------------------------
# Bar input record
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BarInput:
    """One finalized 15m OHLC bar supplied by Work's bar index."""
    open_ms: int    # bar open timestamp (bar-aligned)
    open: float
    high: float
    low: float
    close: float
    finalized: bool = True

    def __post_init__(self) -> None:
        if self.open_ms % BAR_MS != 0:
            raise P1AError("bar open_ms not bar-aligned")
        if not all(math.isfinite(v) for v in (self.open, self.high, self.low, self.close)):
            raise P1AError("bar OHLC must be finite")
        if self.low <= 0:
            raise P1AError("bar low must be positive")
        if self.low > min(self.open, self.close):
            raise P1AError("low > min(open,close)")
        if self.high < max(self.open, self.close):
            raise P1AError("high < max(open,close)")


# ---------------------------------------------------------------------------
# Outcome computation (single opportunity × single horizon)
# ---------------------------------------------------------------------------

def compute_outcome_row(
    opp: OpportunityInput,
    horizon_hours: int,
    bar_index: dict[int, BarInput],
    *,
    source_end_exclusive_ms: int,
) -> P1ARow:
    """Compute one P1ARow for (opp, horizon_hours).

    bar_index maps open_ms → BarInput for the entire available window.
    source_end_exclusive_ms is the exclusive end of available source data.
    Future bars are only used for outcome computation — never influence
    predecision signal.
    """
    if horizon_hours not in HORIZON_HOURS:
        raise P1AError(f"unsupported horizon_hours: {horizon_hours}")
    idx = HORIZON_HOURS.index(horizon_hours)
    horizon_ms = HORIZONS_MS[idx]
    expected_bars = HORIZON_BARS[idx]

    window_start = opp.decision_cutoff_ms
    window_end = window_start + horizon_ms

    # --- Coverage determination (strictly post-decision future bars only) ---
    if source_end_exclusive_ms <= window_start:
        # Source ends before window even begins
        return _make_row(
            opp, horizon_hours, horizon_ms, window_start, window_end,
            expected_bars, "CENSORED", "ARCHIVE_END_CENSORED",
            None, None, None, None, None, None
        )

    if source_end_exclusive_ms < window_end:
        # Source ends inside the window
        return _make_row(
            opp, horizon_hours, horizon_ms, window_start, window_end,
            expected_bars, "CENSORED", "ARCHIVE_END_CENSORED",
            None, None, None, None, None, None
        )

    # Check all expected bar slots exist and are finalized
    expected_opens = list(range(window_start, window_end, BAR_MS))
    if len(expected_opens) != expected_bars:
        raise P1AError("horizon/bar count mismatch — internal error")

    missing = [ts for ts in expected_opens if ts not in bar_index]
    if missing:
        return _make_row(
            opp, horizon_hours, horizon_ms, window_start, window_end,
            expected_bars, "UNKNOWN", "GAPPED_WINDOW",
            None, None, None, None, None, None
        )

    ordered = [bar_index[ts] for ts in expected_opens]
    if any(not b.finalized for b in ordered):
        return _make_row(
            opp, horizon_hours, horizon_ms, window_start, window_end,
            expected_bars, "UNKNOWN", "UNFINALIZED_BAR",
            None, None, None, None, None, None
        )

    # --- COMPLETE: compute market-only metrics ---
    ref_open = ordered[0].open
    if ref_open <= 0:
        return _make_row(
            opp, horizon_hours, horizon_ms, window_start, window_end,
            expected_bars, "UNKNOWN", "INVALID_REF_PRICE",
            None, None, None, None, None, None
        )

    max_high = max(b.high for b in ordered)
    min_low = min(b.low for b in ordered)
    end_close = ordered[-1].close

    market_high_pct = (max_high / ref_open) - 1.0
    market_low_pct = (min_low / ref_open) - 1.0
    market_return_pct = (end_close / ref_open) - 1.0

    # Directional metrics: NULL unless direction proven
    mfe: float | None = None
    mae: float | None = None
    if opp.original_direction == "LONG":
        mfe = max(0.0, market_high_pct)
        mae = max(0.0, -market_low_pct)
    elif opp.original_direction == "SHORT":
        mfe = max(0.0, -market_low_pct)
        mae = max(0.0, market_high_pct)
    # else: direction is None → mfe/mae stay None

    return _make_row(
        opp, horizon_hours, horizon_ms, window_start, window_end,
        expected_bars, "COMPLETE", None,
        expected_bars, market_high_pct, market_low_pct,
        market_return_pct, mfe, mae
    )


def _make_row(
    opp: OpportunityInput,
    horizon_hours: int,
    horizon_ms: int,
    window_start: int,
    window_end: int,
    expected_bars: int,
    coverage_status: str,
    coverage_reason: str | None,
    observed_bars: int | None,
    market_high_pct: float | None,
    market_low_pct: float | None,
    market_return_pct: float | None,
    mfe: float | None,
    mae: float | None,
) -> P1ARow:
    return P1ARow(
        trial_id=opp.trial_id,
        opportunity_id=opp.opportunity_id,
        producer_event_id=opp.producer_event_id,
        envelope_sha256=opp.envelope_sha256,
        decision_cutoff_ms=opp.decision_cutoff_ms,
        decision_ms=opp.decision_ms,
        f3_disposition=opp.f3_disposition,
        f3_reason_code=opp.f3_reason_code,
        original_direction=opp.original_direction,
        horizon_hours=horizon_hours,
        horizon_ms=horizon_ms,
        window_start_ms=window_start,
        window_end_exclusive_ms=window_end,
        expected_bars=expected_bars,
        coverage_status=coverage_status,
        coverage_reason=coverage_reason,
        observed_bars=observed_bars,
        market_high_pct=market_high_pct,
        market_low_pct=market_low_pct,
        market_return_pct=market_return_pct,
        mfe=mfe,
        mae=mae,
    )


# ---------------------------------------------------------------------------
# Batch computation
# ---------------------------------------------------------------------------

def compute_all_rows(
    opportunities: Sequence[OpportunityInput],
    bar_index: dict[int, BarInput],
    *,
    source_end_exclusive_ms: int,
    expected_denominator: int = ORIGINAL_DENOMINATOR,
) -> list[P1ARow]:
    """Compute all P1ARow objects for N opportunities × 3 horizons.

    Enforces:
    - Exact denominator match
    - No duplicate (opportunity_id, horizon_hours) slots
    - No silent omission of any decision

    Returns list of N×3 rows sorted by (decision_cutoff_ms, opportunity_id, horizon_hours).
    """
    if len(opportunities) != expected_denominator:
        raise P1AError(
            f"denominator mismatch: got {len(opportunities)}, "
            f"expected {expected_denominator}"
        )

    # Deduplication check on C2 identity (no duplicate opportunity_ids)
    seen_ids: dict[str, str] = {}
    for opp in opportunities:
        key = opp.opportunity_id
        sig = (opp.trial_id, opp.producer_event_id, opp.envelope_sha256)
        if key in seen_ids:
            raise P1AError(f"duplicate opportunity_id: {key!r}")
        seen_ids[key] = str(sig)

    rows: list[P1ARow] = []
    for opp in opportunities:
        for h in HORIZON_HOURS:
            rows.append(compute_outcome_row(
                opp, h, bar_index,
                source_end_exclusive_ms=source_end_exclusive_ms
            ))

    # Sort for deterministic output
    rows.sort(key=lambda r: (r.decision_cutoff_ms, r.opportunity_id, r.horizon_hours))
    return rows


# ---------------------------------------------------------------------------
# Summary aggregation
# ---------------------------------------------------------------------------

def _descriptive_stats(values: list[float]) -> dict:
    """Median + IQR for a list of float values.  Requires ≥ 2 values."""
    if len(values) < 2:
        return {"count": len(values), "median": None, "iqr": None,
                "note": "INSUFFICIENT_SAMPLE"}
    n = len(values)
    s = sorted(values)
    med = statistics.median(s)
    q1 = statistics.median(s[: n // 2])
    q3 = statistics.median(s[(n + 1) // 2 :])
    return {"count": n, "median": round(med, 6), "iqr": round(q3 - q1, 6)}


def build_summary(rows: list[P1ARow]) -> dict:
    """Aggregate rows into a structured summary dict.

    Computes:
    - Total slots = len(rows)
    - Coverage counts by horizon and f3_disposition
    - Descriptive stats (median/IQR) for COMPLETE market-only metrics
    - Directional stats separately, only for rows with direction set
    - Explicit threat notes
    """
    total = len(rows)
    # Verify all 3 horizons present for each opportunity
    opp_ids = {r.opportunity_id for r in rows}
    for h in HORIZON_HOURS:
        h_rows = [r for r in rows if r.horizon_hours == h]
        if len(h_rows) != len(opp_ids):
            raise P1AError(
                f"missing horizon {h}h rows: "
                f"got {len(h_rows)}, expected {len(opp_ids)}"
            )

    # F3 disposition counts
    f3_counts: dict[str, int] = {}
    for r in rows:
        if r.horizon_hours == HORIZON_HOURS[0]:  # count once per opp
            f3_counts[r.f3_disposition] = f3_counts.get(r.f3_disposition, 0) + 1

    # Coverage by horizon
    coverage: dict[int, dict] = {}
    for h in HORIZON_HOURS:
        h_rows = [r for r in rows if r.horizon_hours == h]
        cov: dict[str, int] = {"COMPLETE": 0, "CENSORED": 0, "UNKNOWN": 0}
        for r in h_rows:
            cov[r.coverage_status] = cov.get(r.coverage_status, 0) + 1
        coverage[h] = cov

    # Descriptive stats on COMPLETE market-only metrics
    market_stats: dict[int, dict] = {}
    for h in HORIZON_HOURS:
        complete = [r for r in rows if r.horizon_hours == h
                    and r.coverage_status == "COMPLETE"]
        highs = [r.market_high_pct for r in complete if r.market_high_pct is not None]
        lows = [r.market_low_pct for r in complete if r.market_low_pct is not None]
        rets = [r.market_return_pct for r in complete if r.market_return_pct is not None]
        market_stats[h] = {
            "complete_count": len(complete),
            "market_high_pct": _descriptive_stats(highs),
            "market_low_pct": _descriptive_stats(lows),
            "market_return_pct": _descriptive_stats(rets),
        }

    # Directional stats (only for COMPLETE rows with proven direction)
    directional_stats: dict[int, dict] = {}
    for h in HORIZON_HOURS:
        dir_rows = [r for r in rows if r.horizon_hours == h
                    and r.coverage_status == "COMPLETE"
                    and r.mfe is not None and r.mae is not None]
        mfes = [r.mfe for r in dir_rows]   # type: ignore[misc]
        maes = [r.mae for r in dir_rows]   # type: ignore[misc]
        directional_stats[h] = {
            "direction_established_count": len(dir_rows),
            "mfe": _descriptive_stats(mfes),
            "mae": _descriptive_stats(maes),
            "note": (
                "NULL_DIRECTION_NOT_ESTABLISHED"
                if not dir_rows
                else "BASE_DESCRIPTIVE"
            ),
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "scope": SCOPE,
        "evidence_class": EVIDENCE_CLASS,
        "denominator": len(opp_ids),
        "total_horizon_slots": total,
        "f3_disposition_counts": f3_counts,
        "coverage_by_horizon": coverage,
        "market_stats_by_horizon": market_stats,
        "directional_stats_by_horizon": directional_stats,
        "shadow_status": "NOT_EVALUABLE_NO_PREDECLARED_PAIRED_CANDIDATE",
        "f1_capture": "MISSING_ORIGINAL_CAPTURE",
        "g2_status": "NOT_CONNECTED",
        "threats": [
            "7-day sample: not statistically valid for strategy selection",
            "overlapping 4h/24h/72h windows: observations not independent",
            "retrospective source publication clock absent: RETROSPECTIVE_NON_PIT",
            "72h end-of-window censor expected for last decisions near archive end",
            "no OOS holdout opened; no alpha or walk-forward claim",
            "direction established only for TRIGGERED/OPEN_UNRESOLVED rows",
        ],
    }


# ---------------------------------------------------------------------------
# Artifact emission
# ---------------------------------------------------------------------------

def build_artifact(
    rows: list[P1ARow],
    *,
    input_manifest_sha256: str,
    source_end_exclusive_ms: int,
    generated_at_utc: str,
) -> dict:
    """Produce the canonical aql-p1-original-opportunity-outcomes.v1 artifact dict.

    artifact_sha256 covers all rows in canonical sorted order.
    Never embed private raw bytes.
    """
    if not _is_sha256(input_manifest_sha256):
        raise P1AError("input_manifest_sha256 must be 64-char hex")

    summary = build_summary(rows)
    serializable_rows = [asdict(r) for r in rows]

    content_hash = _sha256_hex(
        _canonical_bytes({
            "rows": [{
                "trial_id": r["trial_id"],
                "opportunity_id": r["opportunity_id"],
                "producer_event_id": r["producer_event_id"],
                "envelope_sha256": r["envelope_sha256"],
                "horizon_hours": r["horizon_hours"],
                "coverage_status": r["coverage_status"],
                "market_high_pct": r["market_high_pct"],
                "market_low_pct": r["market_low_pct"],
                "market_return_pct": r["market_return_pct"],
                "mfe": r["mfe"],
                "mae": r["mae"],
            } for r in serializable_rows]
        })
    )

    return {
        "schema": "aql-p1-original-opportunity-outcomes.v1",
        "scope": SCOPE,
        "source_proof": {
            "input_manifest_sha256": input_manifest_sha256,
            "source_end_exclusive_ms": source_end_exclusive_ms,
            "generated_at_utc": generated_at_utc,
            "policy_version": POLICY_VERSION,
            "decision_cutoff_convention": "bar-aligned 15m open_ms (BAR_MS=900000)",
        },
        "content_sha256": content_hash,
        "summary": summary,
        "rows": serializable_rows,
    }


# ---------------------------------------------------------------------------
# Markdown report renderer
# ---------------------------------------------------------------------------

def render_markdown_report(artifact: dict) -> str:
    """Render a human-readable Markdown summary from a built artifact.

    Never claims alpha, PIT, or forward-looking results.
    """
    s = artifact["summary"]
    sp = artifact["source_proof"]
    lines: list[str] = []

    lines += [
        "# P1-A Retrospective Opportunity-Outcome Report",
        "",
        f"**Scope:** `{artifact['scope']}`  ",
        f"**Policy:** `{sp['policy_version']}`  ",
        f"**Generated:** `{sp['generated_at_utc']}`  ",
        f"**Input manifest SHA256:** `{sp['input_manifest_sha256']}`  ",
        f"**Artifact content SHA256:** `{artifact['content_sha256']}`  ",
        f"**F1 capture:** `{s['f1_capture']}`  ",
        f"**G2 status:** `{s['g2_status']}`  ",
        f"**SHADOW:** `{s['shadow_status']}`  ",
        "",
        "## Denominator",
        "",
        f"- Total opportunities: **{s['denominator']}**",
        f"- Total horizon slots (N×3): **{s['total_horizon_slots']}**",
        "",
        "### F3 Disposition Breakdown",
        "",
    ]

    for disp, cnt in sorted(s["f3_disposition_counts"].items()):
        lines.append(f"- `{disp}`: {cnt}")

    lines += ["", "## Coverage by Horizon", ""]
    for h in HORIZON_HOURS:
        cov = s["coverage_by_horizon"][h]
        lines.append(
            f"- **{h}h**: COMPLETE={cov.get('COMPLETE', 0)}  "
            f"CENSORED={cov.get('CENSORED', 0)}  "
            f"UNKNOWN={cov.get('UNKNOWN', 0)}"
        )

    lines += ["", "## Market-Only Excursion Metrics (COMPLETE rows, non-directional)", ""]
    for h in HORIZON_HOURS:
        ms = s["market_stats_by_horizon"][h]
        n = ms["complete_count"]
        high = ms["market_high_pct"]
        ret = ms["market_return_pct"]
        lines.append(f"### {h}h — {n} complete observations")
        if high.get("median") is not None:
            lines.append(
                f"- market_high_pct: median={high['median']:.4%}  IQR={high['iqr']:.4%}"
            )
            low = ms["market_low_pct"]
            lines.append(
                f"- market_low_pct:  median={low['median']:.4%}  IQR={low['iqr']:.4%}"
            )
            lines.append(
                f"- market_return_pct: median={ret['median']:.4%}  IQR={ret['iqr']:.4%}"
            )
        else:
            lines.append(f"- {high.get('note', 'INSUFFICIENT_SAMPLE')}")
        lines.append("")

    lines += ["## Directional MFE/MAE (COMPLETE + proven direction only)", ""]
    for h in HORIZON_HOURS:
        ds = s["directional_stats_by_horizon"][h]
        n = ds["direction_established_count"]
        note = ds["note"]
        lines.append(f"### {h}h — {n} direction-established rows  ({note})")
        if ds["mfe"].get("median") is not None:
            lines.append(
                f"- MFE: median={ds['mfe']['median']:.4%}  IQR={ds['mfe']['iqr']:.4%}"
            )
            lines.append(
                f"- MAE: median={ds['mae']['median']:.4%}  IQR={ds['mae']['iqr']:.4%}"
            )
        lines.append("")

    lines += [
        "## Scope Limitations and Threats",
        "",
    ]
    for t in s["threats"]:
        lines.append(f"- {t}")

    lines += [
        "",
        "---",
        "_This report is RETROSPECTIVE_NON_PIT_DESCRIPTIVE. "
        "No fills, PnL, alpha, OOS, or forward-looking claims._",
    ]

    return "\n".join(lines) + "\n"
