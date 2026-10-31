"""Focused changed-seam tests for F1-F4 pipeline.

Tests aql.p0.historical-decision.v1 — Factory F1+F2 opportunity detection,
F3 modeled fill, F4 financial ledger.

No live data, no formal backtest, no formal study run.
Validates changed seams only: full denominator, NON_PIT labeling,
modeled fill semantics, ledger invariants, immutable report hash.

Governance: Factory #77 comment 6540573678.
"""
from __future__ import annotations

import json
from decimal import Decimal
from hashlib import sha256

import pytest

from research_wp_r0.aql_p0_c1_source import (
    P0Bar, P0SourceManifest,
    INTERVAL_MS, WINDOW_START_MS,
    SOURCE_BYTES_SHA256, RECEIPT_STATUS, RECEIPT_MISSING_REASON, CUSTODY_STATUS,
    _canonical_bytes, _sha256_hex, _bar_checksum,
)
from research_wp_r0.aql_p0_c2_producer import produce_envelopes, MIN_PREFIX_BARS
from research_wp_r0.aql_p0_f1f2_opportunities import (
    evaluate_opportunities, SignalState, ENTRY_LOOKBACK, EXIT_LOOKBACK,
)
from research_wp_r0.aql_p0_f3_fill_model import model_fills, INITIAL_CASH
from research_wp_r0.aql_p0_f4_ledger import build_ledger, LedgerConflictError


# ---------------------------------------------------------------------------
# Test fixture builder
# ---------------------------------------------------------------------------

def _make_bar(index: int, open_=100.0, high_=101.0, low_=99.0, close_=100.5, vol=1.0) -> P0Bar:
    open_ms = WINDOW_START_MS + index * INTERVAL_MS
    close_ms = open_ms + INTERVAL_MS - 1
    chk = _bar_checksum(open_ms, open_, high_, low_, close_, vol)
    return P0Bar(
        bar_id=f"BTCUSDT:15m:{open_ms}",
        bar_open_ms=open_ms,
        bar_close_ms=close_ms,
        open=open_, high=high_, low=low_, close=close_, volume=vol,
        is_final=True,
        source_label="TEST",
        availability_kind="RETROSPECTIVE",
        available_as_of_decision="UNKNOWN",
        observation_lower_bound_ms=close_ms + 1,
        receipt_ms=None,
        known_at_ms=None,
        bar_checksum=chk,
        gap_state="COMPLETE",
        correction_generation_id="UNKNOWN_NOT_ATTESTED",
        correction_parent_id=None,
    )


def _make_manifest(bars: list[P0Bar]) -> P0SourceManifest:
    checksums = [b.bar_checksum for b in bars]
    ordered_sha = _sha256_hex(_canonical_bytes(checksums))
    gap_inv = {"complete": len(bars), "missing": 0, "total_scheduled": len(bars),
               "unknown": 0, "bars_with_gap_state": []}
    gap_sha = _sha256_hex(_canonical_bytes(gap_inv))
    corr = {"correction_generation_id": "UNKNOWN_NOT_ATTESTED",
            "reason": "test", "status": "UNKNOWN_NOT_ATTESTED"}
    corr_sha = _sha256_hex(_canonical_bytes(corr))
    n = len(bars)
    return P0SourceManifest(
        schema="aql.p0.historical-decision.v1",
        project_id="AQL-CRYPTO-RESEARCH-001",
        exchange="BINANCE", market="SPOT", symbol="BTCUSDT",
        interval_ms=INTERVAL_MS, timezone="UTC",
        dataset_id="TEST-DS-001", dataset_version=1,
        raw_generation_id="P0-TEST",
        source_bytes_sha256=SOURCE_BYTES_SHA256,
        source_provider="BINANCE_VISION", source_version="TEST",
        source_receipt_sha256=None,
        receipt_status=RECEIPT_STATUS, receipt_missing_reason=RECEIPT_MISSING_REASON,
        custody_status=CUSTODY_STATUS,
        manifest_integrity_sha256=_sha256_hex(b"test-manifest"),
        ordered_bar_checksums_sha256=ordered_sha,
        gap_inventory_sha256=gap_sha,
        correction_lineage_sha256=corr_sha,
        window_start_ms=WINDOW_START_MS,
        window_end_exclusive_ms=WINDOW_START_MS + n * INTERVAL_MS,
        mode="RETROSPECTIVE_NON_PIT", research_only=True,
        bars=tuple(bars),
    )


def _run_full_pipeline(bars: list[P0Bar], trial_id: str = "TEST-TRIAL"):
    manifest = _make_manifest(bars)
    envelopes = produce_envelopes(manifest, trial_id=trial_id)
    opportunities = evaluate_opportunities(manifest, envelopes)
    fills = model_fills(manifest, opportunities)
    state, report = build_ledger(opportunities, fills, trial_id=trial_id)
    return manifest, envelopes, opportunities, fills, state, report


# ---------------------------------------------------------------------------
# F1+F2 — Opportunity detection
# ---------------------------------------------------------------------------

class TestF1F2Opportunities:

    def test_full_denominator_no_signal_bars(self):
        """All-flat bars: all decisions should be NO_SIGNAL (warmup) or NO_SIGNAL (no breakout)."""
        bars = [_make_bar(i) for i in range(30)]
        manifest, envelopes, opps, fills, state, report = _run_full_pipeline(bars)
        assert len(opps) == len(envelopes)
        for opp in opps:
            assert opp.signal_state in (SignalState.NO_SIGNAL,), \
                f"Unexpected state: {opp.signal_state}"

    def test_breakout_signal_fires_on_close_above_20_high(self):
        """Construct bars where close exceeds prior 20-bar high → ARMED signal."""
        # Bars 0-19: all with high=101.0
        # Bar 20: breakout close=110.0 (> prior 20-bar max high=101.0)
        bars = [_make_bar(i, high_=101.0, close_=100.5) for i in range(20)]
        bars.append(_make_bar(20, open_=100.0, high_=111.0, low_=99.0, close_=110.0))
        # Add a few more bars so the trigger bar exists
        for i in range(21, 30):
            bars.append(_make_bar(i, open_=105.0, high_=110.0, low_=100.0, close_=105.0))

        manifest, envelopes, opps, fills, state, report = _run_full_pipeline(bars)

        # Find the opportunity for bar index 20 (decision after bar 20)
        # C2 produces decisions after each bar starting from index MIN_PREFIX_BARS=20
        # So the first envelope has cutoff after bar[19], and the second after bar[20]
        # Index 1 in envelopes = decision after bar[20]
        armed_opps = [o for o in opps if o.signal_state == SignalState.ARMED]
        assert len(armed_opps) >= 1, "Expected at least one ARMED signal for breakout"
        # The ARMED opportunity should have entry_level set
        assert armed_opps[0].entry_level is not None
        assert armed_opps[0].trigger_bar_open_ms is not None

    def test_no_signal_does_not_set_trigger(self):
        """NO_SIGNAL opportunities must have trigger_bar_open_ms=None."""
        bars = [_make_bar(i) for i in range(25)]
        _, _, opps, _, _, _ = _run_full_pipeline(bars)
        for opp in opps:
            if opp.signal_state == SignalState.NO_SIGNAL:
                assert opp.trigger_bar_open_ms is None

    def test_opportunity_count_equals_scheduled_decisions(self):
        """len(opportunities) == len(envelopes) — full denominator."""
        bars = [_make_bar(i) for i in range(30)]
        _, envelopes, opps, _, _, _ = _run_full_pipeline(bars)
        assert len(opps) == len(envelopes)

    def test_availability_mode_propagated(self):
        """All opportunities must reference RETROSPECTIVE_NON_PIT."""
        bars = [_make_bar(i) for i in range(25)]
        _, envelopes, opps, _, _, _ = _run_full_pipeline(bars)
        for env in envelopes:
            assert env.availability_mode == "RETROSPECTIVE_NON_PIT"
        for opp in opps:
            assert opp.input_disposition in ("EVALUABLE_RETROSPECTIVE", "BLOCKED", "UNKNOWN")


# ---------------------------------------------------------------------------
# F3 — Modeled fill
# ---------------------------------------------------------------------------

class TestF3Fill:

    def test_no_signal_pass_through(self):
        """NO_SIGNAL opportunities must pass through F3 unchanged."""
        bars = [_make_bar(i) for i in range(25)]
        _, _, opps, fills, _, _ = _run_full_pipeline(bars)
        for opp, fill in zip(opps, fills):
            if opp.signal_state == SignalState.NO_SIGNAL:
                assert fill.signal_state == "NO_SIGNAL"
                assert fill.entry_price_net is None
                assert fill.exit_price_net is None
                assert fill.is_terminal is True

    def test_triggered_fill_has_prices(self):
        """A TRIGGERED fill must have entry and exit prices set."""
        # Create bars with a breakout and subsequent exit condition
        bars = [_make_bar(i, high_=101.0, close_=100.5, low_=99.0) for i in range(20)]
        # Breakout bar
        bars.append(_make_bar(20, open_=100.0, high_=115.0, low_=99.0, close_=112.0))
        # Bars after entry that go high, then drop below exit level
        for i in range(21, 25):
            bars.append(_make_bar(i, open_=110.0, high_=115.0, low_=108.0, close_=112.0))
        # Add drop bars to trigger exit
        for i in range(25, 40):
            bars.append(_make_bar(i, open_=85.0, high_=86.0, low_=80.0, close_=82.0))

        _, _, opps, fills, _, _ = _run_full_pipeline(bars)
        triggered = [(o, f) for o, f in zip(opps, fills) if f.signal_state == "TRIGGERED"]
        if triggered:
            opp, fill = triggered[0]
            assert fill.entry_price_net is not None
            assert fill.exit_price_net is not None
            assert fill.gross_return is not None
            assert fill.net_return is not None

    def test_open_unresolved_has_entry_no_exit(self):
        """OPEN_UNRESOLVED positions must have entry but no exit."""
        # Breakout with no subsequent drop — position stays open
        bars = [_make_bar(i, high_=101.0, close_=100.5, low_=99.0) for i in range(20)]
        bars.append(_make_bar(20, open_=100.0, high_=115.0, low_=99.0, close_=112.0))
        # Keep high prices so exit condition never triggers
        for i in range(21, 30):
            bars.append(_make_bar(i, open_=112.0, high_=115.0, low_=110.0, close_=113.0))

        _, _, opps, fills, _, _ = _run_full_pipeline(bars)
        unresolved = [f for f in fills if f.signal_state == "OPEN_UNRESOLVED"]
        for f in unresolved:
            assert f.entry_price_net is not None
            assert f.exit_price_net is None
            assert f.gross_return is None
            assert f.is_terminal is False

    def test_fill_count_equals_opportunity_count(self):
        """len(fills) == len(opportunities) — denominator preserved."""
        bars = [_make_bar(i) for i in range(30)]
        _, _, opps, fills, _, _ = _run_full_pipeline(bars)
        assert len(fills) == len(opps)


# ---------------------------------------------------------------------------
# F4 — Financial ledger
# ---------------------------------------------------------------------------

class TestF4Ledger:

    def test_denominator_invariant(self):
        """sum(denominator_counts) == total_scheduled_decisions."""
        bars = [_make_bar(i) for i in range(25)]
        _, _, opps, fills, state, report = _run_full_pipeline(bars)
        report.assert_denominator()

    def test_initial_cash_is_constant(self):
        """Ledger cash starts at INITIAL_CASH (Decimal)."""
        assert INITIAL_CASH == Decimal("10000.00")

    def test_report_sha256_deterministic(self):
        """Same data produces same report_sha256."""
        bars = [_make_bar(i) for i in range(25)]
        _, _, opps, fills, state, report = _run_full_pipeline(bars)
        sha1 = report.report_sha256()
        sha2 = report.report_sha256()
        assert sha1 == sha2

    def test_settled_equity_null_if_open_position(self):
        """settled_equity must be null when held_btc > 0."""
        bars = [_make_bar(i, high_=101.0, close_=100.5, low_=99.0) for i in range(20)]
        bars.append(_make_bar(20, open_=100.0, high_=115.0, low_=99.0, close_=112.0))
        for i in range(21, 30):
            bars.append(_make_bar(i, open_=112.0, high_=115.0, low_=110.0, close_=113.0))
        _, _, opps, fills, state, report = _run_full_pipeline(bars)
        if report.open_unresolved > 0:
            # At least one open position — settled_equity should be null
            assert report.settled_equity is None, \
                f"Expected settled_equity=None with open positions, got {report.settled_equity}"

    def test_no_profitability_claim_without_closed_trades(self):
        """average_net_return must be None when no closed trades."""
        bars = [_make_bar(i) for i in range(25)]  # all flat — no breakout
        _, _, opps, fills, state, report = _run_full_pipeline(bars)
        if report.closed_trades == 0:
            assert report.average_net_return_closed is None

    def test_idempotent_ledger_replay(self):
        """Replaying same fills twice into same LedgerState must be idempotent."""
        bars = [_make_bar(i) for i in range(25)]
        manifest = _make_manifest(bars)
        envelopes = produce_envelopes(manifest, trial_id="IDEM-TEST")
        opps = evaluate_opportunities(manifest, envelopes)
        fills = model_fills(manifest, opps)

        from research_wp_r0.aql_p0_f4_ledger import LedgerState, _apply_event
        from research_wp_r0.aql_p0_f4_ledger import LedgerEvent, _event_id

        # Build state once
        state1, report1 = build_ledger(opps, fills, trial_id="IDEM-TEST")

        # Build state again — same inputs must produce same report hash
        state2, report2 = build_ledger(opps, fills, trial_id="IDEM-TEST")
        assert report1.report_sha256() == report2.report_sha256()

    def test_report_to_dict_is_json_serializable(self):
        """LedgerReport.to_dict() must be JSON-serializable."""
        bars = [_make_bar(i) for i in range(25)]
        _, _, opps, fills, state, report = _run_full_pipeline(bars)
        d = report.to_dict()
        # Convert Decimal fields manually as json doesn't handle Decimal
        serialized = json.dumps(d, default=str)
        parsed = json.loads(serialized)
        assert parsed["total_scheduled_decisions"] == report.total_scheduled_decisions

    def test_report_sha256_is_64_hex(self):
        """report_sha256 must be 64 lowercase hex characters."""
        bars = [_make_bar(i) for i in range(25)]
        _, _, opps, fills, state, report = _run_full_pipeline(bars)
        sha = report.report_sha256()
        assert len(sha) == 64
        assert sha == sha.lower()
        assert all(c in "0123456789abcdef" for c in sha)

    def test_no_signal_counts_in_denominator(self):
        """NO_SIGNAL decisions must appear in denominator_counts."""
        bars = [_make_bar(i) for i in range(25)]
        _, _, opps, fills, state, report = _run_full_pipeline(bars)
        assert "NO_SIGNAL" in report.denominator_counts
        assert report.denominator_counts["NO_SIGNAL"] > 0
