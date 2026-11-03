"""P1-A retrospective opportunity-outcome report library — pure consumer/renderer.

Consumes ``aql-p1-original-opportunity-outcomes.v1`` rows as emitted by
Work PR #220 (aql_p1a_original_653.py).  Never re-reads private source
bytes, never re-computes bar outcomes, never invents fills/PnL/direction.

Role:
  - Validate inbound row schema (fail-closed)
  - Aggregate: coverage counts, descriptive stats (COMPLETE market-only only)
  - Render: deterministic canonical JSON artifact + Markdown report
  - No W1, no Core producer, no G2 runtime imported

Contract alignment: Work PR #220 HEAD 3d045048
  schema_version = aql-p1-original-opportunity-outcomes.v1
  rows[*].availability       ∈ {COMPLETE, CENSORED, UNKNOWN}
  rows[*].market_metrics     dict | None   (None unless availability==COMPLETE)
  rows[*].directional_metrics None         (no original direction)
  rows[*].direction          None
  rows[*].f1_status          MISSING_ORIGINAL_CAPTURE
  rows[*].g2_prospective_status NOT_CONNECTED
  shadow_status              NOT_EVALUABLE_NO_PREDECLARED_PAIRED_CANDIDATE

SCOPE      = RETROSPECTIVE_NON_PIT_DESCRIPTIVE
EVIDENCE   = BASE_DESCRIPTIVE
FILLS/PnL  = never inferred; not_available for NO_SIGNAL/REJECTED
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from typing import Any, Sequence

# ---------------------------------------------------------------------------
# Public constants — aligned with Work PR #220
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "aql-p1-original-opportunity-outcomes.v1"
RENDERER_VERSION = "aql.p1a-report-library.v1"
POLICY_VERSION = "P1A-RETROSPECTIVE-DESCRIPTIVE-v1"
SCOPE = "RETROSPECTIVE_NON_PIT_DESCRIPTIVE"
EVIDENCE_CLASS = "RETROSPECTIVE_NON_PIT"

EXPECTED_DENOMINATOR = 653
EXPECTED_SLOTS = 1959        # 653 × 3 horizons
HORIZON_HOURS_VALID = frozenset((4, 24, 72))
F3_DISPOSITIONS_VALID = frozenset(
    ("NO_SIGNAL", "REJECTED", "TRIGGERED", "OPEN_UNRESOLVED", "UNKNOWN", "BLOCKED")
)
AVAILABILITY_VALID = frozenset(("COMPLETE", "CENSORED", "UNKNOWN"))

# Immutable constants every row must carry (Work PR #220 contract)
F1_STATUS_REQUIRED = "MISSING_ORIGINAL_CAPTURE"
G2_STATUS_REQUIRED = "NOT_CONNECTED"
SHADOW_STATUS_REQUIRED = "NOT_EVALUABLE_NO_PREDECLARED_PAIRED_CANDIDATE"
DIRECTIONAL_STATUS_REQUIRED = "NOT_EVALUABLE_MISSING_ORIGINAL_DIRECTION"
REFERENCE_KIND_REQUIRED = "OPEN_AT_CUTOFF_NON_EXECUTABLE"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class P1AError(ValueError):
    """Raised for contract violations — never silently patched."""


# ---------------------------------------------------------------------------
# Typed inbound row — exactly mirrors Work's emitted row fields
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InboundRow:
    """One validated row from Work's aql-p1-original-opportunity-outcomes.v1.

    Only the fields used for aggregation/rendering are mandatory here;
    additional provenance fields from Work are preserved in `extra`.
    """
    # C2 identity
    trial_id: str
    opportunity_id: str
    producer_event_id: str
    envelope_sha256: str

    # Decision timing
    decision_cutoff_ms: int     # bar-aligned cutoff; NON_EXECUTABLE reference
    decision_ms: int            # +2000ms by convention (MODELED, never fill)

    # F3
    f3_disposition: str         # NO_SIGNAL | REJECTED | TRIGGERED | …
    f3_reason: str | None       # null in original receipts

    # Horizon
    horizon_hours: int          # 4 | 24 | 72
    window_end_exclusive_ms: int
    expected_bars: int          # 16 | 96 | 288
    observed_bars: int | None

    # Coverage (Work field name: 'availability')
    availability: str           # COMPLETE | CENSORED | UNKNOWN
    availability_reason: str | None

    # Market-only metrics (COMPLETE only; null otherwise)
    # Work emits a nested dict 'market_metrics' or null
    market_metrics: dict | None   # {reference_price, observed_high, observed_low,
                                  #  market_high_return, market_low_return,
                                  #  market_close_return}

    # Directional (always None — no original direction)
    directional_metrics: None
    direction: None
    directional_status: str     # NOT_EVALUABLE_MISSING_ORIGINAL_DIRECTION

    # Immutable status fields
    f1_status: str              # MISSING_ORIGINAL_CAPTURE
    g2_prospective_status: str  # NOT_CONNECTED
    reference_kind: str         # OPEN_AT_CUTOFF_NON_EXECUTABLE

    def __post_init__(self) -> None:
        # Identity
        if not self.trial_id or not self.opportunity_id:
            raise P1AError("empty C2 identity field")
        if not _is_sha256(self.envelope_sha256):
            raise P1AError(f"envelope_sha256 not a 64-char hex digest: {self.envelope_sha256!r}")

        # F3
        if self.f3_disposition not in F3_DISPOSITIONS_VALID:
            raise P1AError(f"unknown f3_disposition: {self.f3_disposition!r}")

        # Horizon
        if self.horizon_hours not in HORIZON_HOURS_VALID:
            raise P1AError(f"unsupported horizon_hours: {self.horizon_hours}")

        # Coverage
        if self.availability not in AVAILABILITY_VALID:
            raise P1AError(f"unknown availability: {self.availability!r}")

        # market_metrics consistency
        if self.availability == "COMPLETE":
            if self.market_metrics is None:
                raise P1AError("COMPLETE row must have market_metrics")
            _validate_market_metrics(self.market_metrics)
        else:
            if self.market_metrics is not None:
                raise P1AError(
                    f"non-COMPLETE row must not have market_metrics "
                    f"(availability={self.availability})"
                )

        # Direction always null
        if self.direction is not None:
            raise P1AError(
                "direction must be null (no original direction in source)"
            )
        if self.directional_metrics is not None:
            raise P1AError(
                "directional_metrics must be null (no original direction)"
            )

        # No fills/PnL — not a field here, but validate directional_status
        if self.directional_status != DIRECTIONAL_STATUS_REQUIRED:
            raise P1AError(
                f"directional_status must be {DIRECTIONAL_STATUS_REQUIRED!r}, "
                f"got {self.directional_status!r}"
            )

        # Immutable constants
        if self.f1_status != F1_STATUS_REQUIRED:
            raise P1AError(f"f1_status must be {F1_STATUS_REQUIRED!r}")
        if self.g2_prospective_status != G2_STATUS_REQUIRED:
            raise P1AError(f"g2_prospective_status must be {G2_STATUS_REQUIRED!r}")
        if self.reference_kind != REFERENCE_KIND_REQUIRED:
            raise P1AError(f"reference_kind must be {REFERENCE_KIND_REQUIRED!r}")

        # decision_ms should be after or equal to cutoff (never before)
        if self.decision_ms < self.decision_cutoff_ms:
            raise P1AError(
                "decision_ms < decision_cutoff_ms (impossible lookahead)"
            )


def _is_sha256(v: Any) -> bool:
    return (
        isinstance(v, str)
        and len(v) == 64
        and all(c in "0123456789abcdef" for c in v)
    )


def _validate_market_metrics(mm: dict) -> None:
    required = ("reference_price", "observed_high", "observed_low",
                 "market_high_return", "market_low_return", "market_close_return")
    for k in required:
        if k not in mm:
            raise P1AError(f"market_metrics missing key: {k!r}")
        v = mm[k]
        if not isinstance(v, (int, float)) or not math.isfinite(v):
            raise P1AError(f"market_metrics[{k!r}] must be finite float, got {v!r}")
    if mm["reference_price"] <= 0:
        raise P1AError("market_metrics.reference_price must be > 0")
    if mm["observed_low"] > mm["reference_price"]:
        raise P1AError("market_metrics.observed_low > reference_price is suspicious")
    # market_low_return should be ≤ 0 (low is below open)
    # — warn via error only for grossly wrong values (low > open is impossible)
    if mm["market_low_return"] > 0:
        raise P1AError("market_metrics.market_low_return > 0 is impossible")


# ---------------------------------------------------------------------------
# Batch validator
# ---------------------------------------------------------------------------

def validate_rows(
    rows: Sequence[dict],
    *,
    expected_denominator: int = EXPECTED_DENOMINATOR,
) -> list[InboundRow]:
    """Parse and validate raw row dicts from Work's result.json.

    Enforces:
    - Exact denominator (unique opportunity_ids)
    - No duplicate (opportunity_id, horizon_hours) slots
    - All required fields present; all invariants satisfied

    Raises P1AError on the first violation (fail-closed).
    """
    # Extract and deduplicate opportunities
    seen_opps: dict[str, set] = {}     # opportunity_id → {horizon_hours seen}
    seen_identity: dict[tuple, None] = {}  # full C2 4-tuple → present

    parsed: list[InboundRow] = []
    for i, raw in enumerate(rows):
        row = _parse_inbound_row(raw, index=i)
        parsed.append(row)

        opp_id = row.opportunity_id
        h = row.horizon_hours
        if opp_id not in seen_opps:
            seen_opps[opp_id] = set()
        if h in seen_opps[opp_id]:
            raise P1AError(
                f"duplicate (opportunity_id={opp_id!r}, horizon_hours={h}) at index {i}"
            )
        seen_opps[opp_id].add(h)

        # C2 identity includes horizon_hours: same envelope can have 3 horizon rows
        identity = (row.trial_id, row.opportunity_id,
                    row.producer_event_id, row.envelope_sha256, row.horizon_hours)
        if identity in seen_identity:
            raise P1AError(f"duplicate C2 identity at index {i}: {identity}")
        seen_identity[identity] = None

    n_opps = len(seen_opps)
    if n_opps != expected_denominator:
        raise P1AError(
            f"denominator mismatch: got {n_opps} unique opportunities, "
            f"expected {expected_denominator}"
        )
    expected_slots = n_opps * 3
    if len(parsed) != expected_slots:
        raise P1AError(
            f"slot count mismatch: missing horizons; got {len(parsed)} rows, "
            f"expected {expected_slots} ({n_opps} opps × 3 horizons)"
        )
    for opp_id, horizons in seen_opps.items():
        if horizons != {4, 24, 72}:
            raise P1AError(
                f"opportunity {opp_id!r} missing horizons: "
                f"present={sorted(horizons)}, required=[4,24,72]"
            )

    return parsed


def _parse_inbound_row(raw: dict, *, index: int) -> InboundRow:
    """Extract InboundRow from Work's raw dict, raising P1AError on missing fields."""
    def get(key: str) -> Any:
        if key not in raw:
            raise P1AError(f"row[{index}] missing required field {key!r}")
        return raw[key]

    return InboundRow(
        trial_id=get("trial_id"),
        opportunity_id=get("opportunity_id"),
        producer_event_id=get("producer_event_id"),
        envelope_sha256=get("envelope_sha256"),
        decision_cutoff_ms=get("decision_cutoff_ms"),
        decision_ms=get("decision_ms"),
        f3_disposition=get("f3_disposition"),
        f3_reason=raw.get("f3_reason"),
        horizon_hours=get("horizon_hours"),
        window_end_exclusive_ms=get("window_end_exclusive_ms"),
        expected_bars=get("expected_bars"),
        observed_bars=raw.get("observed_bars"),
        availability=get("availability"),
        availability_reason=raw.get("availability_reason"),
        market_metrics=raw.get("market_metrics"),
        directional_metrics=raw.get("directional_metrics"),
        direction=raw.get("direction"),
        directional_status=get("directional_status"),
        f1_status=get("f1_status"),
        g2_prospective_status=get("g2_prospective_status"),
        reference_kind=get("reference_kind"),
    )


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _descriptive_stats(values: list[float]) -> dict:
    """Median + IQR for a list of floats.  Requires ≥ 2 values."""
    n = len(values)
    if n < 2:
        return {"count": n, "median": None, "iqr": None,
                "note": "INSUFFICIENT_SAMPLE"}
    s = sorted(values)
    med = statistics.median(s)
    q1 = statistics.median(s[: n // 2])
    q3 = statistics.median(s[(n + 1) // 2 :])
    return {"count": n, "median": round(med, 8), "iqr": round(q3 - q1, 8)}


def aggregate_summary(rows: list[InboundRow]) -> dict:
    """Compute structured summary from validated InboundRow objects.

    Computes only from COMPLETE market-only fields.
    Directional stats left as NOT_EVALUABLE (no original direction).
    """
    opp_ids = {r.opportunity_id for r in rows}

    # F3 disposition counts (once per opportunity — use 4h rows as key)
    f3_counts: dict[str, int] = {}
    for r in rows:
        if r.horizon_hours == 4:
            f3_counts[r.f3_disposition] = f3_counts.get(r.f3_disposition, 0) + 1

    # Coverage by horizon
    coverage: dict[int, dict] = {}
    for h in (4, 24, 72):
        h_rows = [r for r in rows if r.horizon_hours == h]
        cov: dict[str, int] = {}
        for r in h_rows:
            cov[r.availability] = cov.get(r.availability, 0) + 1
        coverage[h] = cov

    # Coverage by horizon × f3_disposition
    coverage_by_disp: dict[str, dict] = {}
    for disp in f3_counts:
        coverage_by_disp[disp] = {}
        for h in (4, 24, 72):
            sub = [r for r in rows if r.horizon_hours == h and r.f3_disposition == disp]
            coverage_by_disp[disp][h] = {
                av: sum(1 for r in sub if r.availability == av)
                for av in ("COMPLETE", "CENSORED", "UNKNOWN")
                if any(r.availability == av for r in sub)
            }

    # Descriptive stats — COMPLETE market-only only, by horizon
    market_stats: dict[int, dict] = {}
    for h in (4, 24, 72):
        complete = [
            r for r in rows
            if r.horizon_hours == h and r.availability == "COMPLETE"
            and r.market_metrics is not None
        ]
        highs  = [r.market_metrics["market_high_return"]  for r in complete]
        lows   = [r.market_metrics["market_low_return"]   for r in complete]
        closes = [r.market_metrics["market_close_return"] for r in complete]
        market_stats[h] = {
            "complete_count": len(complete),
            "market_high_return":  _descriptive_stats(highs),
            "market_low_return":   _descriptive_stats(lows),
            "market_close_return": _descriptive_stats(closes),
        }

    # Descriptive stats — by horizon × f3_disposition (COMPLETE only)
    market_stats_by_disp: dict[str, dict[int, dict]] = {}
    for disp in f3_counts:
        market_stats_by_disp[disp] = {}
        for h in (4, 24, 72):
            sub = [
                r for r in rows
                if r.horizon_hours == h
                and r.f3_disposition == disp
                and r.availability == "COMPLETE"
                and r.market_metrics is not None
            ]
            highs  = [r.market_metrics["market_high_return"]  for r in sub]
            lows   = [r.market_metrics["market_low_return"]   for r in sub]
            closes = [r.market_metrics["market_close_return"] for r in sub]
            market_stats_by_disp[disp][h] = {
                "complete_count": len(sub),
                "market_high_return":  _descriptive_stats(highs),
                "market_low_return":   _descriptive_stats(lows),
                "market_close_return": _descriptive_stats(closes),
            }

    return {
        "renderer_version": RENDERER_VERSION,
        "scope": SCOPE,
        "evidence_class": EVIDENCE_CLASS,
        "denominator": len(opp_ids),
        "total_horizon_slots": len(rows),
        "f3_disposition_counts": f3_counts,
        "coverage_by_horizon": coverage,
        "coverage_by_horizon_and_disposition": coverage_by_disp,
        "market_stats_by_horizon": market_stats,
        "market_stats_by_horizon_and_disposition": market_stats_by_disp,
        "directional_stats": "NOT_EVALUABLE_MISSING_ORIGINAL_DIRECTION",
        "shadow_status": SHADOW_STATUS_REQUIRED,
        "f1_status": F1_STATUS_REQUIRED,
        "g2_status": G2_STATUS_REQUIRED,
        "threats": [
            "SEVEN_DAY_SAMPLE_NOT_STRATEGY_VALIDATION",
            "OVERLAPPING_HORIZONS_NOT_INDEPENDENT",
            "ARCHIVE_END_CENSORING_AFFECTS_72H_MOST",
            "SOURCE_ARRIVAL_PIT_NOT_AUTHENTICATED",
            "NO_ORIGINAL_F1_DIRECTION_OR_REGIME",
            "NO_ALPHA_OOS_OR_TRADING_CLAIM",
        ],
    }


# ---------------------------------------------------------------------------
# Canonical artifact
# ---------------------------------------------------------------------------

def _canonical_bytes(obj: Any) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_artifact(
    rows: list[InboundRow],
    *,
    source_artifact_content_sha256: str,
    generated_at_utc: str,
    work_code_sha: str,
) -> dict:
    """Produce a canonical renderer artifact from validated InboundRow objects.

    `source_artifact_content_sha256` is the `artifact_content_sha256` field
    from Work's result.json, proving which Work output this renderer consumed.

    The renderer's own `renderer_content_sha256` covers the summary only
    (rows are not re-embedded — Work's result.json is the row authority).
    """
    if not _is_sha256(source_artifact_content_sha256):
        raise P1AError("source_artifact_content_sha256 must be 64-char hex")
    if not generated_at_utc.endswith("Z"):
        raise P1AError("generated_at_utc must end with Z")

    summary = aggregate_summary(rows)

    content = {
        "schema": SCHEMA_VERSION,
        "renderer": RENDERER_VERSION,
        "scope": SCOPE,
        "source_proof": {
            "work_source_artifact_content_sha256": source_artifact_content_sha256,
            "work_code_sha": work_code_sha,
            "generated_at_utc": generated_at_utc,
            "decision_cutoff_convention": "OPEN_AT_CUTOFF_NON_EXECUTABLE",
        },
        "summary": summary,
    }

    content["renderer_content_sha256"] = _sha256_hex(_canonical_bytes(content))
    return content


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------

def render_markdown_report(artifact: dict) -> str:
    """Human-readable Markdown summary from a renderer artifact dict.

    Never claims alpha, PIT, fills, PnL, or forward-looking results.
    """
    s = artifact["summary"]
    sp = artifact["source_proof"]
    sha = artifact.get("renderer_content_sha256", "—")

    lines: list[str] = [
        "# P1-A Retrospective Opportunity-Outcome Report",
        "",
        f"**Scope:** `{artifact['scope']}`  ",
        f"**Renderer:** `{artifact['renderer']}`  ",
        f"**Generated:** `{sp['generated_at_utc']}`  ",
        f"**Source content SHA256:** `{sp['work_source_artifact_content_sha256']}`  ",
        f"**Renderer content SHA256:** `{sha}`  ",
        f"**F1 status:** `{s['f1_status']}`  ",
        f"**G2 status:** `{s['g2_status']}`  ",
        f"**SHADOW:** `{s['shadow_status']}`  ",
        f"**Directional stats:** `{s['directional_stats']}`  ",
        "",
        "## Denominator",
        "",
        f"- Unique opportunities: **{s['denominator']}**",
        f"- Total horizon slots (N×3): **{s['total_horizon_slots']}**",
        "",
        "### F3 Disposition",
        "",
    ]

    for disp, cnt in sorted(s["f3_disposition_counts"].items()):
        lines.append(f"- `{disp}`: {cnt}")

    lines += ["", "## Coverage by Horizon", ""]
    for h in (4, 24, 72):
        cov = s["coverage_by_horizon"].get(h, {})
        lines.append(
            f"- **{h}h**: COMPLETE={cov.get('COMPLETE', 0)}  "
            f"CENSORED={cov.get('CENSORED', 0)}  "
            f"UNKNOWN={cov.get('UNKNOWN', 0)}"
        )

    lines += ["", "## Market-Only Descriptive Stats (COMPLETE rows, non-directional)", ""]
    for h in (4, 24, 72):
        ms = s["market_stats_by_horizon"].get(h, {})
        n = ms.get("complete_count", 0)
        high = ms.get("market_high_return", {})
        lines.append(f"### {h}h — {n} complete observations")
        if high.get("median") is not None:
            low = ms["market_low_return"]
            close = ms["market_close_return"]
            lines.append(
                f"- market_high_return:  median={high['median']:.6%}  IQR={high['iqr']:.6%}"
            )
            lines.append(
                f"- market_low_return:   median={low['median']:.6%}  IQR={low['iqr']:.6%}"
            )
            lines.append(
                f"- market_close_return: median={close['median']:.6%}  IQR={close['iqr']:.6%}"
            )
        else:
            lines.append(f"- {high.get('note', 'INSUFFICIENT_SAMPLE')}")
        lines.append("")

    # Disposition-stratified stats
    lines += ["", "## Market Stats by Disposition × Horizon (COMPLETE only)", ""]
    dstats = s.get("market_stats_by_horizon_and_disposition", {})
    for disp in sorted(dstats):
        lines.append(f"### {disp}")
        for h in (4, 24, 72):
            ms = dstats[disp].get(h, {})
            n = ms.get("complete_count", 0)
            high = ms.get("market_high_return", {})
            if n == 0:
                lines.append(f"- {h}h: 0 COMPLETE rows")
            elif high.get("median") is not None:
                low = ms["market_low_return"]
                close = ms["market_close_return"]
                lines.append(
                    f"- {h}h (n={n}): high median={high['median']:.4%} "
                    f"low median={low['median']:.4%} "
                    f"close median={close['median']:.4%}"
                )
            else:
                lines.append(f"- {h}h (n={n}): INSUFFICIENT_SAMPLE")
        lines.append("")

    lines += [
        "## Scope Limitations and Threats",
        "",
    ]
    for t in s["threats"]:
        lines.append(f"- `{t}`")

    lines += [
        "",
        "---",
        "_RETROSPECTIVE_NON_PIT_DESCRIPTIVE. No fills, PnL, direction, alpha, "
        "OOS, or forward-looking claims._",
        "_Reference prices are OPEN_AT_CUTOFF_NON_EXECUTABLE (not achievable fill prices)._",
    ]

    return "\n".join(lines) + "\n"
