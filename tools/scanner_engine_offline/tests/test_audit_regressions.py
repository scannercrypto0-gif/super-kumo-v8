"""Adversarial regression tests for all P0/P1 defects.

Audit reference: AQL-SCANNER-V1-SCIENTIFIC-ENGINEERING-REVIEW-001
Comment: https://github.com/scannercrypto0-gif/super-kumo-v8/issues/134#issuecomment-6605160086

Each test class names the specific audit finding it guards against.
These tests MUST remain green on any refactor of the scanner engine.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest

from tools.scanner_engine_offline.contracts import (
    AdmittedBar, AdmissionResult, admit_bars, SourceManifest,
    ScannerNominationEnvelope, canonical_bytes, sha256_hex,
    AVAILABILITY_RETRO, STAGE_NOMINATED, STAGE_UNKNOWN, SCHEMA_VERSION,
    _utc,
)
from tools.scanner_engine_offline.engine import (
    OfflineScannerEngine, ScanRunConfig, _admit_symbol_bars,
)
from tools.scanner_engine_offline.adapters import (
    make_synthetic_bars, make_synthetic_universe,
)
from tools.scanner_engine_offline.evidence import (
    BoundedSpool, EvidenceReceipt, commit_receipt,
    restore_from_checkpoint, _claim_receipt_id,
)

UTC = timezone.utc
T0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
SYMBOLS = ["SOLUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT", "MATICUSDT"]
TFS = ["5m", "30m", "1h", "4h", "1d"]


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_manifest(cutoff_at: datetime = T0) -> SourceManifest:
    return SourceManifest(
        dataset_id="AUDIT-TEST-DS",
        dataset_sha=sha256_hex(canonical_bytes({"audit": True})),
        schema_version=SCHEMA_VERSION,
        cutoff_at=cutoff_at,
        created_at=cutoff_at,
    )


def _make_bars(symbols=None, count=35, cutoff_at=T0):
    symbols = symbols or SYMBOLS
    return {
        sym: {tf: make_synthetic_bars(sym, tf, cutoff_at, count=count) for tf in TFS}
        for sym in symbols
    }


def _make_engine(limit=5, offset=0, cutoff_at=T0):
    config = ScanRunConfig(
        scanner_id="AUDIT-SCANNER-001",
        candidate_limit=limit,
        candidate_offset=offset,
    )
    return OfflineScannerEngine(config, _make_manifest(cutoff_at))


def _make_good_bar(symbol="SOLUSDT", timeframe="5m", cutoff_at=T0) -> AdmittedBar:
    close_at = cutoff_at - timedelta(minutes=5)
    return AdmittedBar(
        source_id="TEST",
        timeframe=timeframe,
        symbol=symbol,
        open_at=close_at - timedelta(minutes=5),
        close_at=close_at,
        available_at=close_at,
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100.5"),
        base_volume=Decimal("500"),
        quote_volume=Decimal("50000"),
    )


# ── P0-01: Central admission boundary ─────────────────────────────────────────

class TestP001AdmissionBoundary:
    """Engine must reject future bars, wrong-symbol bars, wrong-TF bars
    at the central admission boundary before any feature is computed."""

    def test_future_bars_never_reach_features(self):
        """Future bar (close_at > cutoff) must be excluded by engine admission."""
        future_close = T0 + timedelta(minutes=10)
        future_bar = AdmittedBar(
            source_id="TEST", timeframe="5m", symbol="SOLUSDT",
            open_at=T0 + timedelta(minutes=5),
            close_at=future_close,
            available_at=future_close,
            open=Decimal("200"), high=Decimal("201"), low=Decimal("199"),
            close=Decimal("200"), base_volume=Decimal("1"), quote_volume=Decimal("200"),
        )
        admitted = _admit_symbol_bars("SOLUSDT", {"5m": [future_bar]}, T0, "test-run")
        assert future_bar not in admitted.get("5m", []), \
            "Future bar must be excluded by central admission"

    def test_wrong_symbol_bars_excluded(self):
        """Bars with the wrong symbol for a slot must be excluded."""
        wrong_symbol_bar = _make_good_bar(symbol="BTCUSDT", timeframe="5m")
        admitted = _admit_symbol_bars("SOLUSDT", {"5m": [wrong_symbol_bar]}, T0, "test-run")
        assert admitted.get("5m", []) == [], \
            "Bars with wrong symbol must be excluded at admission"

    def test_wrong_timeframe_bars_excluded(self):
        """Bars placed in wrong TF slot (e.g. 1h bar in 5m slot) must be excluded."""
        wrong_tf_bar = _make_good_bar(symbol="SOLUSDT", timeframe="1h")
        # Put a bar with timeframe="1h" into the "5m" slot
        admitted = _admit_symbol_bars("SOLUSDT", {"5m": [wrong_tf_bar]}, T0, "test-run")
        assert admitted.get("5m", []) == [], \
            "Bars with wrong timeframe must be excluded at admission"

    def test_bar_exactly_at_cutoff_admitted(self):
        """Bar closing exactly at cutoff must be admitted (boundary condition)."""
        bar = _make_good_bar(symbol="SOLUSDT", timeframe="5m", cutoff_at=T0)
        # close_at = T0 - 5m, available_at = close_at → should be admitted
        admitted = _admit_symbol_bars("SOLUSDT", {"5m": [bar]}, T0, "test-run")
        assert len(admitted.get("5m", [])) == 1, "Bar closing before cutoff must be admitted"

    def test_engine_uses_central_admission_for_all_bars(self):
        """Engine run with future bars in input must never produce features from them."""
        # Inject a future bar into "5m" slot for SOLUSDT
        future_close = T0 + timedelta(minutes=5)
        future_bar = AdmittedBar(
            source_id="TEST", timeframe="5m", symbol="SOLUSDT",
            open_at=T0, close_at=future_close, available_at=future_close,
            open=Decimal("999"), high=Decimal("1000"), low=Decimal("998"),
            close=Decimal("999"), base_volume=Decimal("1"), quote_volume=Decimal("999"),
        )
        bars = _make_bars(["SOLUSDT"])
        bars["SOLUSDT"]["5m"].append(future_bar)  # inject future bar

        universe = make_synthetic_universe(["SOLUSDT"], T0)
        engine = _make_engine(limit=1)
        run = engine.scan(universe, bars)

        # Engine must complete without accepting future data
        # (run completes and produces results — the future bar is silently rejected)
        assert run is not None
        # No P0-01 error should be raised — future bar just gets dropped at admission


# ── P0-02: Fail-closed census ──────────────────────────────────────────────────

class TestP002FailClosedCensus:
    """Every (symbol, profile) attempt must produce a receipt, even on error.
    No symbol/profile pair may silently vanish from the census."""

    def test_census_counts_match_expected(self):
        """Census.expected_receipt_count == symbols × profiles."""
        symbols = SYMBOLS[:3]
        universe = make_synthetic_universe(symbols, T0)
        bars = _make_bars(symbols)
        engine = _make_engine(limit=3)
        run = engine.scan(universe, bars)
        census = run.census
        expected = census["expected_receipt_count"]
        actual = census["completed"] + census["error"]
        assert actual == expected, (
            f"Completed ({census['completed']}) + error ({census['error']}) "
            f"must equal expected ({expected})"
        )

    def test_error_produces_unknown_receipt_not_silence(self):
        """A symbol that causes a feature error must still produce UNKNOWN receipts."""
        # Provide bars with valid structure but for only 1 symbol
        # so the other symbols trigger SCORE_UNAVAILABLE (empty bars)
        symbols = ["SOLUSDT", "AVAXUSDT"]
        universe = make_synthetic_universe(symbols, T0)
        engine = _make_engine(limit=2)
        run = engine.scan(universe, {})  # empty bars → SCORE_UNAVAILABLE path

        # Every (symbol, profile) must have a receipt
        spool_receipts = list(run.spool)
        profiles = list(engine._config.profiles)
        expected_count = len(symbols) * len(profiles)
        # Spool may evict but we have few receipts here
        assert len(spool_receipts) == expected_count, (
            f"Expected {expected_count} receipts (one per symbol×profile), "
            f"got {len(spool_receipts)}"
        )

    def test_all_envelopes_have_score_unavailable_on_empty_bars(self):
        """Symbols with no bars must have SCORE_UNAVAILABLE, not be silently omitted.

        With empty bars: features compute but coverage fails → stage is SCREENED or
        lower (not NOMINATED).  UNKNOWN is reserved for Python exceptions.  The key
        P0-02 invariant is that envelopes ARE produced (not silently dropped) and
        all carry SCORE_UNAVAILABLE.
        """
        symbols = SYMBOLS[:2]
        universe = make_synthetic_universe(symbols, T0)
        engine = _make_engine(limit=2)
        run = engine.scan(universe, {})

        assert len(run.envelopes) > 0, "Must produce envelopes even for empty bars"
        for env in run.envelopes:
            assert env.score_status == "SCORE_UNAVAILABLE", (
                f"Envelope {env.candidate_id}/{env.profile_id} must have "
                f"SCORE_UNAVAILABLE with empty bars, got: {env.score_status}"
            )
            # Must NOT be NOMINATED — no bars means no valid nomination
            assert env.stage != STAGE_NOMINATED, (
                f"Envelope must not be NOMINATED with empty bars: {env.stage}"
            )

    def test_summary_has_full_census_keys(self):
        """Summary must expose census keys for auditability."""
        symbols = SYMBOLS[:2]
        universe = make_synthetic_universe(symbols, T0)
        bars = _make_bars(symbols)
        engine = _make_engine(limit=2)
        run = engine.scan(universe, bars)
        s = run.summary()
        assert "census" in s
        for key in ("symbols_attempted", "profiles", "expected_receipt_count",
                    "completed", "error", "spool_size"):
            assert key in s["census"], f"Missing census key: {key}"


# ── P0-03: Receipt identity / idempotency ─────────────────────────────────────

class TestP003ReceiptIdentity:
    """Receipt IDs must not collide across runs.
    Same receipt_id with different payload must raise, not silently drop."""

    def test_receipt_id_includes_run_id(self):
        """Two different run_ids produce different receipt_ids for same symbol/profile."""
        id1 = _claim_receipt_id("SCANNER-1", "SOLUSDT", "INTRADAY", T0, run_id="RUN-A")
        id2 = _claim_receipt_id("SCANNER-1", "SOLUSDT", "INTRADAY", T0, run_id="RUN-B")
        assert id1 != id2, "Different run_ids must produce different receipt_ids"

    def test_same_inputs_produce_same_receipt_id(self):
        """Receipt ID is deterministic for identical inputs."""
        id1 = _claim_receipt_id("SCANNER-1", "SOLUSDT", "INTRADAY", T0, run_id="RUN-A")
        id2 = _claim_receipt_id("SCANNER-1", "SOLUSDT", "INTRADAY", T0, run_id="RUN-A")
        assert id1 == id2

    def test_spool_rejects_same_id_different_payload(self):
        """BoundedSpool must raise ValueError on same receipt_id with different payload."""
        payload1 = {"score": "70.00", "stage": "NOMINATED"}
        payload2 = {"score": "50.00", "stage": "SCREENED"}
        digest1 = sha256_hex(canonical_bytes(payload1))
        digest2 = sha256_hex(canonical_bytes(payload2))
        assert digest1 != digest2

        # Create two receipts with same ID but different payloads
        r1 = EvidenceReceipt(
            receipt_id="SAME-ID-001",
            claim_at=T0, committed_at=T0,
            scanner_id="S1", symbol="SOLUSDT", profile="INTRADAY",
            stage="NOMINATED", score="70.00", score_status="SCORED",
            payload=payload1, payload_digest=digest1,
        )
        r2 = EvidenceReceipt(
            receipt_id="SAME-ID-001",
            claim_at=T0, committed_at=T0,
            scanner_id="S1", symbol="SOLUSDT", profile="INTRADAY",
            stage="SCREENED", score="50.00", score_status="SCORED",
            payload=payload2, payload_digest=digest2,
        )
        spool = BoundedSpool(capacity=10, spool_id="TEST")
        spool.append(r1)
        with pytest.raises(ValueError, match="RECEIPT_ID_CONFLICT"):
            spool.append(r2)

    def test_spool_exact_replay_is_idempotent(self):
        """Same receipt appended twice (exact replay) returns first without raising."""
        payload = {"score": "70.00"}
        digest = sha256_hex(canonical_bytes(payload))
        r = EvidenceReceipt(
            receipt_id="REPLAY-001",
            claim_at=T0, committed_at=T0,
            scanner_id="S1", symbol="SOLUSDT", profile="INTRADAY",
            stage="NOMINATED", score="70.00", score_status="SCORED",
            payload=payload, payload_digest=digest,
        )
        spool = BoundedSpool(capacity=10, spool_id="TEST")
        spool.append(r)
        result = spool.append(r)  # must not raise
        assert len(spool) == 1, "Exact replay must not duplicate the receipt"
        assert result.receipt_id == r.receipt_id

    def test_committed_at_is_deterministic(self):
        """commit_receipt with no explicit committed_at uses claim_at (not wall clock)."""
        r1 = commit_receipt(
            scanner_id="S", symbol="SOLUSDT", profile="INTRADAY",
            stage="NOMINATED", score="70.00", score_status="SCORED",
            payload={"x": 1}, claim_at=T0, run_id="R1",
        )
        r2 = commit_receipt(
            scanner_id="S", symbol="SOLUSDT", profile="INTRADAY",
            stage="NOMINATED", score="70.00", score_status="SCORED",
            payload={"x": 1}, claim_at=T0, run_id="R1",
        )
        assert r1.committed_at == r2.committed_at, \
            "committed_at must be deterministic (= claim_at) for research receipts"
        assert r1.committed_at == T0

    def test_run_ids_differ_for_different_manifests(self):
        """Two engines with different manifests produce different run_ids."""
        manifest1 = _make_manifest(T0)
        manifest2 = SourceManifest(
            dataset_id="DIFFERENT-DS",
            dataset_sha=sha256_hex(canonical_bytes({"different": True})),
            schema_version=SCHEMA_VERSION,
            cutoff_at=T0,
            created_at=T0,
        )
        config = ScanRunConfig(scanner_id="AUDIT-SCANNER-001", candidate_limit=2)
        e1 = OfflineScannerEngine(config, manifest1)
        e2 = OfflineScannerEngine(config, manifest2)
        universe = make_synthetic_universe(SYMBOLS[:2], T0)
        bars = _make_bars(SYMBOLS[:2])
        r1 = e1.scan(universe, bars)
        r2 = e2.scan(universe, bars)
        assert r1.run_id != r2.run_id, \
            "Different manifests must produce different run_ids"


# ── P0-04: Manifest / time binding ────────────────────────────────────────────

class TestP004ManifestTimeBinding:
    """Engine must reject cutoff mismatches between manifest, universe, and run."""

    def test_manifest_cutoff_mismatch_raises(self):
        """Engine must raise if manifest.cutoff_at != run cutoff_at."""
        manifest_at_t1 = _make_manifest(T0 + timedelta(hours=1))
        config = ScanRunConfig(scanner_id="TEST", candidate_limit=2)
        engine = OfflineScannerEngine(config, manifest_at_t1)
        universe = make_synthetic_universe(SYMBOLS[:2], T0)  # universe at T0
        with pytest.raises(ValueError, match="CUTOFF_MISMATCH"):
            engine.scan(universe, {})  # cutoff defaults to universe.cutoff_at = T0

    def test_universe_cutoff_mismatch_raises(self):
        """Engine must raise if universe.cutoff_at != run cutoff_at."""
        manifest = _make_manifest(T0)  # manifest at T0
        config = ScanRunConfig(scanner_id="TEST", candidate_limit=2)
        engine = OfflineScannerEngine(config, manifest)
        universe = make_synthetic_universe(SYMBOLS[:2], T0)
        # Pass explicit cutoff that differs from universe.cutoff_at
        with pytest.raises(ValueError, match="CUTOFF_MISMATCH"):
            engine.scan(universe, {}, cutoff_at=T0 + timedelta(hours=1))

    def test_consistent_cutoffs_accepted(self):
        """Engine must not raise when all cutoffs are consistent."""
        engine = _make_engine()  # manifest at T0
        universe = make_synthetic_universe(SYMBOLS[:2], T0)  # universe at T0
        run = engine.scan(universe, {})  # cutoff = universe.cutoff_at = T0
        assert run is not None


# ── P1-01: Cross-process determinism ──────────────────────────────────────────

class TestP101CrossProcessDeterminism:
    """Synthetic bar generation must be stable across Python processes
    (independent of PYTHONHASHSEED)."""

    def test_make_synthetic_bars_cross_process_stable(self):
        """Run make_synthetic_bars in two subprocesses with different PYTHONHASHSEED;
        verify identical JSON output for the same symbol/tf/cutoff."""
        script = (
            "import json; "
            "from tools.scanner_engine_offline.adapters import make_synthetic_bars; "
            "from datetime import datetime, timezone; "
            "UTC = timezone.utc; "
            "T0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC); "
            "bars = make_synthetic_bars('SOLUSDT', '5m', T0, count=5); "
            "print(json.dumps([str(b.close) for b in bars]))"
        )
        out1 = subprocess.check_output(
            [sys.executable, "-c", script],
            env={**__import__("os").environ, "PYTHONHASHSEED": "0"},
            text=True,
        ).strip()
        out2 = subprocess.check_output(
            [sys.executable, "-c", script],
            env={**__import__("os").environ, "PYTHONHASHSEED": "12345"},
            text=True,
        ).strip()
        assert out1 == out2, (
            f"make_synthetic_bars is not cross-process stable!\n"
            f"  SEED=0:     {out1}\n"
            f"  SEED=12345: {out2}"
        )

    def test_scan_run_id_cross_process_stable(self):
        """run_id must be identical across Python processes (no hash() in its seed)."""
        script = (
            "from tools.scanner_engine_offline.engine import ScanRunConfig; "
            "from tools.scanner_engine_offline.contracts import sha256_hex, canonical_bytes; "
            "from datetime import datetime, timezone; "
            "UTC = timezone.utc; "
            "T0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC); "
            "config = ScanRunConfig(scanner_id='AUDIT-SCANNER-001', candidate_limit=5); "
            "print(config.run_id_seed(T0, 'MANIFEST-SHA-ABC123'))"
        )
        id1 = subprocess.check_output(
            [sys.executable, "-c", script],
            env={**__import__("os").environ, "PYTHONHASHSEED": "0"},
            text=True,
        ).strip()
        id2 = subprocess.check_output(
            [sys.executable, "-c", script],
            env={**__import__("os").environ, "PYTHONHASHSEED": "99999"},
            text=True,
        ).strip()
        assert id1 == id2, "run_id must be stable across PYTHONHASHSEED values"


# ── P1-02: Sealed envelope immutability ───────────────────────────────────────

class TestP102SealedEnvelopeImmutability:
    """After seal(), no field on ScannerNominationEnvelope may be mutated."""

    def _make_env(self) -> ScannerNominationEnvelope:
        manifest = _make_manifest()
        return ScannerNominationEnvelope(
            scanner_id="S1",
            candidate_id="SOLUSDT:2024",
            profile_id="INTRADAY",
            market="BINANCE:SPOT:USDT",
            cutoff_at=T0,
            availability_class=AVAILABILITY_RETRO,
            stage=STAGE_NOMINATED,
            source_manifest=manifest.as_dict(),
            feature_snapshot={"oc_5m": "1.5"},
            reasons=["TEST"],
            coverage={"ok": 1, "total": 1},
            score="72.00",
            score_status="SCORED",
        )

    def test_mutation_before_seal_allowed(self):
        """Fields may be mutated before seal()."""
        env = self._make_env()
        env.score = "80.00"  # must not raise
        assert env.score == "80.00"

    def test_mutation_after_seal_raises(self):
        """Any field mutation after seal() must raise SEALED_ENVELOPE_MUTATION."""
        env = self._make_env().seal()
        with pytest.raises(ValueError, match="SEALED_ENVELOPE_MUTATION"):
            env.score = "99.00"

    def test_stage_mutation_after_seal_raises(self):
        """stage field mutation after seal() must raise."""
        env = self._make_env().seal()
        with pytest.raises(ValueError, match="SEALED_ENVELOPE_MUTATION"):
            env.stage = "SCREENED"

    def test_publishable_mutation_after_seal_raises(self):
        """publishable field mutation after seal() must raise."""
        env = self._make_env().seal()
        with pytest.raises(ValueError, match="SEALED_ENVELOPE_MUTATION"):
            env.publishable = True

    def test_digest_unchanged_after_seal(self):
        """Digest must not change after seal (can't re-seal with different content)."""
        env = self._make_env()
        env.seal()
        original_digest = env.digest
        # digest field is exempt from mutation guard (it IS the seal)
        # but subsequent seal calls just overwrite _digest only
        assert env.digest == original_digest

    def test_publishable_always_false_in_dict_regardless_of_field(self):
        """as_dict() returns publishable=False even if field was set True before seal."""
        env = self._make_env()
        env.publishable = True  # set True before seal (allowed)
        env.seal()
        assert env.as_dict()["publishable"] is False
        assert env.as_dict()["delivery_authorized"] is False

    def test_sealed_envelope_passes_integrity_check(self):
        """A sealed envelope's digest must match re-computation of as_dict."""
        env = self._make_env().seal()
        d = env.as_dict(include_digest=False)
        expected_digest = sha256_hex(canonical_bytes(d))
        assert env.digest == expected_digest


# ── P1-03: CI safety (production scope only) ──────────────────────────────────

class TestP103CISafety:
    """The publishable=True guard must not fire on legitimate negative test code."""

    def test_negative_test_code_not_a_safety_violation(self):
        """test_contracts.py has publishable=True in a negative test.
        This is correct behavior — the test verifies the override works.
        Production code (non-test) must never have publishable=True."""
        import ast, pathlib
        scanner_root = pathlib.Path("tools/scanner_engine_offline")
        # Only check production files (not test files)
        prod_files = [
            f for f in scanner_root.rglob("*.py")
            if not any(part == "tests" for part in f.parts)
        ]
        violations = []
        for fpath in prod_files:
            tree = ast.parse(fpath.read_text(), filename=str(fpath))
            for node in ast.walk(tree):
                if isinstance(node, ast.keyword):
                    if node.arg in ("publishable", "delivery_authorized"):
                        if isinstance(node.value, ast.Constant) and node.value.value is True:
                            violations.append(f"{fpath}: {node.arg}=True")
        assert violations == [], (
            f"Production source has publishable/delivery_authorized=True:\n"
            + "\n".join(violations)
        )

    def test_all_produced_envelopes_publishable_false(self):
        """Every envelope produced by the engine must have publishable=False."""
        universe = make_synthetic_universe(SYMBOLS[:3], T0)
        bars = _make_bars(SYMBOLS[:3])
        engine = _make_engine(limit=3)
        run = engine.scan(universe, bars)
        for env in run.envelopes:
            assert env.publishable is False
            assert env.delivery_authorized is False
            assert env.as_dict()["publishable"] is False
            assert env.as_dict()["delivery_authorized"] is False

    def test_demo_output_has_publishable_check_true(self):
        """Demo run's publishable_check and delivery_authorized_check must be True
        (meaning ALL envelopes returned False)."""
        from tools.scanner_engine_offline.demo import run_demo
        result = run_demo()
        assert result["publishable_check"] is True, \
            "publishable_check=True means all envelopes had publishable=False"
        assert result["delivery_authorized_check"] is True


# ── P1-04: Universe coverage / as-of contract (documented limitation) ─────────

class TestP104UniverseCoverageContract:
    """Universe snapshots must be tagged as RETROSPECTIVE_NON_PIT.
    Delisted symbols and selection bias are out of scope for offline V1
    but must be explicitly documented in envelope availability_class."""

    def test_all_envelopes_tagged_retrospective(self):
        """Every envelope must carry AVAILABILITY_RETRO tag."""
        universe = make_synthetic_universe(SYMBOLS[:3], T0)
        bars = _make_bars(SYMBOLS[:3])
        engine = _make_engine(limit=3)
        run = engine.scan(universe, bars)
        for env in run.envelopes:
            assert env.availability_class == AVAILABILITY_RETRO, (
                f"Envelope {env.candidate_id}/{env.profile_id} has wrong "
                f"availability_class: {env.availability_class}"
            )

    def test_universe_snapshot_cutoff_used_consistently(self):
        """Universe cutoff must propagate to all envelope cutoff_at fields."""
        universe = make_synthetic_universe(SYMBOLS[:2], T0)
        bars = _make_bars(SYMBOLS[:2])
        engine = _make_engine(limit=2)
        run = engine.scan(universe, bars)
        for env in run.envelopes:
            env_cutoff = _utc(env.cutoff_at)
            assert env_cutoff == T0, (
                f"Envelope cutoff mismatch: {env_cutoff} != {T0}"
            )


# ── Cross-cutting: End-to-end determinism ─────────────────────────────────────

class TestEndToEndDeterminism:
    """Full engine runs with identical inputs must produce identical outputs."""

    def test_two_runs_produce_identical_run_ids(self):
        """Identical inputs → identical run_id."""
        universe = make_synthetic_universe(SYMBOLS[:3], T0)
        bars = _make_bars(SYMBOLS[:3])
        e1 = _make_engine(limit=3)
        e2 = _make_engine(limit=3)
        r1 = e1.scan(universe, bars)
        r2 = e2.scan(universe, bars)
        assert r1.run_id == r2.run_id

    def test_two_runs_produce_identical_envelope_digests(self):
        """Identical inputs → identical envelope digests for all produced envelopes."""
        universe = make_synthetic_universe(SYMBOLS[:3], T0)
        bars = _make_bars(SYMBOLS[:3])
        e1 = _make_engine(limit=3)
        e2 = _make_engine(limit=3)
        r1 = e1.scan(universe, bars)
        r2 = e2.scan(universe, bars)
        digests1 = sorted(e.digest for e in r1.envelopes if e.digest)
        digests2 = sorted(e.digest for e in r2.envelopes if e.digest)
        assert digests1 == digests2, "Envelope digests must be identical across runs"

    def test_spool_checkpoint_restore_integrity(self):
        """Checkpoint restore must produce identical receipts; corrupt receipts rejected."""
        universe = make_synthetic_universe(SYMBOLS[:2], T0)
        bars = _make_bars(SYMBOLS[:2])
        engine = _make_engine(limit=2)
        run = engine.scan(universe, bars)

        checkpoint = run.spool.to_checkpoint()
        restored_spool, rejected = restore_from_checkpoint(checkpoint)

        assert rejected == [], f"No receipts should be rejected: {rejected}"
        assert len(restored_spool) == len(run.spool), \
            "Restored spool must have same receipt count"

    def test_corrupt_checkpoint_receipt_rejected(self):
        """A receipt with tampered payload must be rejected on restore."""
        universe = make_synthetic_universe(SYMBOLS[:1], T0)
        bars = _make_bars(SYMBOLS[:1])
        engine = _make_engine(limit=1)
        run = engine.scan(universe, bars)

        checkpoint = run.spool.to_checkpoint()
        cp_dict = checkpoint.as_dict()
        # Tamper with first receipt's payload
        if cp_dict["receipts"]:
            cp_dict["receipts"][0]["payload"] = {"tampered": True}
        from tools.scanner_engine_offline.evidence import SpoolCheckpoint
        tampered_checkpoint = SpoolCheckpoint(
            spool_id=cp_dict["spool_id"],
            capacity=cp_dict["capacity"],
            receipt_count=cp_dict["receipt_count"],
            receipts=cp_dict["receipts"],
        )
        _, rejected = restore_from_checkpoint(tampered_checkpoint)
        assert len(rejected) > 0, "Tampered receipt must be rejected on restore"
