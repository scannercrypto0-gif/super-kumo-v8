"""
Focused tests: Discoverer → Factory Lab Bridge
==============================================
Tests cover:
  - FactoryLabReceiptV1 contract (hash integrity, safety flags)
  - LabDenominatorSnapshotV1 (fields from NominationEvidenceV1)
  - LabAttemptLogV1 (append, chain linkage, counts)
  - DataSourceIsolator rules R1–R6
  - DiscovererToFactoryBridge routing (admitted, quarantined, rejected)
  - Batch routing

No Holdout, no real execution, no Work module.
Only synthetic/test-fixture nominations are used.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import replace

import pytest

from tools.strategy_discoverer_offline.contracts import (
    NominationEvidenceV1,
    EvidenceClass,
    SourceAvailability,
    ScannerQuarantineStatus,
    DiscoveryCandidatePackageV1,
    FactoryRouting,
    _digest,
    _canonical,
)
from tools.strategy_discoverer_offline.data_isolator import (
    DataSourceIsolator,
    QuarantineVerdict,
)
from tools.strategy_discoverer_offline.factory_lab_contracts import (
    FactoryRoutingStatus,
    FactoryLabReceiptV1,
    LabDenominatorSnapshotV1,
    LabAttemptLogV1,
)
from tools.strategy_discoverer_offline.factory_lab_bridge import (
    DiscovererToFactoryBridge,
    SafetyFlagError,
    _verify_package_safety,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"),
                   allow_nan=False).encode()
    ).hexdigest()


def _make_evidence(
    *,
    evidence_class=EvidenceClass.TEST_ONLY_SYNTHETIC.value,
    quarantine_status=ScannerQuarantineStatus.TEST_ONLY_SYNTHETIC.value,
    source_availability=SourceAvailability.CONFIRMED_FINAL.value,
    cutoff_ms=1_700_000_000_000,
    source_dataset_id="test-dataset-001",
    source_dataset_version=1,
    full_universe_denominator=100,
    eligible_selected=80,
    ineligible=10,
    unscanned=5,
    screened_rejected=3,
    unknown=2,
    nominated=60,
) -> NominationEvidenceV1:
    """Build a minimal valid NominationEvidenceV1 for testing via .build()."""
    null_sha = "0" * 64
    return NominationEvidenceV1.build(
        schema_version="aql.discoverer.nomination-evidence.v1",
        evidence_class=evidence_class,
        quarantine_status=quarantine_status,
        scanner_contract_version="0.1.0",
        scanner_source_commit=null_sha,
        scanner_envelope_sha256=null_sha,
        scanner_receipt_sha256=null_sha,
        source_dataset_id=source_dataset_id,
        source_dataset_version=source_dataset_version,
        source_raw_sha256=null_sha,
        source_manifest_sha256=null_sha,
        universe_snapshot_sha256=null_sha,
        scan_run_id="run-001",
        market="BINANCE_SPOT",
        symbol="BTCUSDT",
        timeframe="1h",
        profile="default",
        cutoff_ms=cutoff_ms,
        source_availability=source_availability,
        full_universe_denominator=full_universe_denominator,
        eligible_selected=eligible_selected,
        ineligible=ineligible,
        unscanned=unscanned,
        screened_rejected=screened_rejected,
        unknown=unknown,
        nominated=nominated,
        failed_attempts=0,
        omission_reason_codes=(),
        independent_verifier_receipt_sha256=null_sha,
    )


def _make_package(evidence: NominationEvidenceV1) -> DiscoveryCandidatePackageV1:
    """Build a minimal valid DiscoveryCandidatePackageV1 from evidence."""
    null_sha = "0" * 64
    strat_spec = {"strategy_id": "test-strat", "version": "1"}
    strat_digest = _sha256(strat_spec)
    candidate_id = str(uuid.uuid4())
    # Build via the .build() classmethod so safety flags are set correctly
    return DiscoveryCandidatePackageV1.build(
        schema_version="aql.discoverer.candidate.v1",
        candidate_id=candidate_id,
        family_id="F001",
        family_version="1.0.0",
        strategy_definition_digest=strat_digest,
        strategy_spec=strat_spec,
        nomination_evidence_digest=evidence.nomination_digest,
        source_manifest_sha256=null_sha,
        rule_grammar_version="aql.strategy-definition.grammar.v1",
        search_plan_digest=null_sha,
        counterhypothesis_id="null-001",
        attempt_ledger_head=null_sha,
        status="PROPOSED_RESEARCH_ONLY",
    )


GOOD_EVIDENCE = _make_evidence()
GOOD_PACKAGE = _make_package(GOOD_EVIDENCE)
NULL_SHA = "0" * 64


# ---------------------------------------------------------------------------
# LabDenominatorSnapshotV1
# ---------------------------------------------------------------------------

class TestLabDenominatorSnapshot:
    def test_from_evidence_roundtrip(self):
        snap = LabDenominatorSnapshotV1.from_evidence(GOOD_EVIDENCE)
        assert snap.full_universe_denominator == 100
        assert snap.eligible_selected == 80
        assert snap.nominated == 60
        assert snap.source_dataset_id == "test-dataset-001"
        assert snap.source_dataset_version == 1
        assert len(snap.snapshot_digest) == 64

    def test_digest_verified(self):
        snap = LabDenominatorSnapshotV1.from_evidence(GOOD_EVIDENCE)
        # Re-computing must match
        d = LabDenominatorSnapshotV1.from_evidence(GOOD_EVIDENCE)
        assert snap.snapshot_digest == d.snapshot_digest

    def test_bad_nominated_gt_eligible(self):
        with pytest.raises(ValueError, match="nominated cannot exceed"):
            LabDenominatorSnapshotV1(
                schema_version="aql.lab.denominator-snapshot.v1",
                full_universe_denominator=100,
                eligible_selected=10,
                ineligible=0,
                unscanned=0,
                screened_rejected=0,
                unknown=0,
                nominated=50,          # > eligible_selected
                source_dataset_id="x",
                source_dataset_version=1,
                snapshot_digest=NULL_SHA,
            )

    def test_tampered_snapshot_digest_rejected(self):
        snap = LabDenominatorSnapshotV1.from_evidence(GOOD_EVIDENCE)
        d = snap.to_dict()
        d["snapshot_digest"] = NULL_SHA  # tamper
        with pytest.raises(ValueError, match="snapshot_digest mismatch"):
            LabDenominatorSnapshotV1(**{k: v for k, v in d.items()
                                        if k != "denominator_snapshot"})


# ---------------------------------------------------------------------------
# FactoryLabReceiptV1
# ---------------------------------------------------------------------------

class TestFactoryLabReceiptV1:
    def _snap(self):
        return LabDenominatorSnapshotV1.from_evidence(GOOD_EVIDENCE)

    def _base_kwargs(self):
        snap = self._snap()
        return dict(
            receipt_id=str(uuid.uuid4()),
            routing_status=FactoryRoutingStatus.ROUTED_SYNTHETIC_ONLY,
            quarantine_reason=None,
            candidate_id=GOOD_PACKAGE.candidate_id,
            package_digest=GOOD_PACKAGE.package_digest,
            strategy_definition_digest=GOOD_PACKAGE.strategy_definition_digest,
            family_id=GOOD_PACKAGE.family_id,
            nomination_evidence_digest=GOOD_PACKAGE.nomination_evidence_digest,
            denominator_snapshot=snap,
            ledger_attempt_id="attempt-001",
            ledger_head_digest=NULL_SHA,
            predecessor_receipt_digest=NULL_SHA,
            routed_at_ns=1_000_000_000,
            safety_flags_verified=True,
        )

    def test_build_roundtrip(self):
        receipt = FactoryLabReceiptV1.build(**self._base_kwargs())
        assert receipt.routing_status == FactoryRoutingStatus.ROUTED_SYNTHETIC_ONLY.value
        assert receipt.holdout_accessed is False
        assert receipt.real_execution_initiated is False
        assert receipt.work_module_imported is False
        assert len(receipt.receipt_digest) == 64

    def test_holdout_guard(self):
        """build() always produces holdout_accessed=False; __post_init__ rejects True."""
        receipt = FactoryLabReceiptV1.build(**self._base_kwargs())
        assert receipt.holdout_accessed is False
        # Direct construction with holdout_accessed=True must raise
        kw = self._base_kwargs()
        snap = self._snap()
        # Build the receipt_digest for a modified payload (would differ, but we just
        # want to confirm the guard fires BEFORE the digest check)
        with pytest.raises(ValueError, match="holdout_accessed must be False"):
            FactoryLabReceiptV1(
                schema_version=FactoryLabReceiptV1.SCHEMA_VERSION,
                receipt_id=kw["receipt_id"],
                routing_status=FactoryRoutingStatus.ROUTED_SYNTHETIC_ONLY.value,
                quarantine_reason=None,
                candidate_id=kw["candidate_id"],
                package_digest=kw["package_digest"],
                strategy_definition_digest=kw["strategy_definition_digest"],
                family_id=kw["family_id"],
                nomination_evidence_digest=kw["nomination_evidence_digest"],
                denominator_snapshot=snap,
                ledger_attempt_id=kw["ledger_attempt_id"],
                ledger_head_digest=kw["ledger_head_digest"],
                predecessor_receipt_digest=kw["predecessor_receipt_digest"],
                routed_at_ns=kw["routed_at_ns"],
                safety_flags_verified=kw["safety_flags_verified"],
                holdout_accessed=True,       # <-- violation
                real_execution_initiated=False,
                work_module_imported=False,
                receipt_digest=NULL_SHA,
            )

    def test_tampered_receipt_digest_rejected(self):
        receipt = FactoryLabReceiptV1.build(**self._base_kwargs())
        # Build fresh receipt with wrong digest directly
        kw = self._base_kwargs()
        snap = self._snap()
        with pytest.raises(ValueError, match="receipt_digest mismatch"):
            FactoryLabReceiptV1(
                schema_version=FactoryLabReceiptV1.SCHEMA_VERSION,
                receipt_id=kw["receipt_id"],
                routing_status=FactoryRoutingStatus.ROUTED_SYNTHETIC_ONLY.value,
                quarantine_reason=None,
                candidate_id=kw["candidate_id"],
                package_digest=kw["package_digest"],
                strategy_definition_digest=kw["strategy_definition_digest"],
                family_id=kw["family_id"],
                nomination_evidence_digest=kw["nomination_evidence_digest"],
                denominator_snapshot=snap,
                ledger_attempt_id=kw["ledger_attempt_id"],
                ledger_head_digest=kw["ledger_head_digest"],
                predecessor_receipt_digest=kw["predecessor_receipt_digest"],
                routed_at_ns=kw["routed_at_ns"],
                safety_flags_verified=kw["safety_flags_verified"],
                holdout_accessed=False,
                real_execution_initiated=False,
                work_module_imported=False,
                receipt_digest=NULL_SHA,   # tampered
            )

    def test_schema_version_enforced(self):
        kw = self._base_kwargs()
        snap = self._snap()
        with pytest.raises(ValueError, match="Bad schema_version"):
            FactoryLabReceiptV1(
                schema_version="wrong.version",
                receipt_id=kw["receipt_id"],
                routing_status=FactoryRoutingStatus.ROUTED_SYNTHETIC_ONLY.value,
                quarantine_reason=None,
                candidate_id=kw["candidate_id"],
                package_digest=kw["package_digest"],
                strategy_definition_digest=kw["strategy_definition_digest"],
                family_id=kw["family_id"],
                nomination_evidence_digest=kw["nomination_evidence_digest"],
                denominator_snapshot=snap,
                ledger_attempt_id=kw["ledger_attempt_id"],
                ledger_head_digest=kw["ledger_head_digest"],
                predecessor_receipt_digest=kw["predecessor_receipt_digest"],
                routed_at_ns=kw["routed_at_ns"],
                safety_flags_verified=kw["safety_flags_verified"],
                holdout_accessed=False,
                real_execution_initiated=False,
                work_module_imported=False,
                receipt_digest=NULL_SHA,
            )


# ---------------------------------------------------------------------------
# LabAttemptLogV1
# ---------------------------------------------------------------------------

class TestLabAttemptLogV1:
    def _make_receipt(self, predecessor_digest: str) -> FactoryLabReceiptV1:
        snap = LabDenominatorSnapshotV1.from_evidence(GOOD_EVIDENCE)
        return FactoryLabReceiptV1.build(
            receipt_id=str(uuid.uuid4()),
            routing_status=FactoryRoutingStatus.ROUTED_SYNTHETIC_ONLY,
            quarantine_reason=None,
            candidate_id=GOOD_PACKAGE.candidate_id,
            package_digest=GOOD_PACKAGE.package_digest,
            strategy_definition_digest=GOOD_PACKAGE.strategy_definition_digest,
            family_id=GOOD_PACKAGE.family_id,
            nomination_evidence_digest=GOOD_PACKAGE.nomination_evidence_digest,
            denominator_snapshot=snap,
            ledger_attempt_id=str(uuid.uuid4()),
            ledger_head_digest=NULL_SHA,
            predecessor_receipt_digest=predecessor_digest,
            routed_at_ns=1_000_000_000,
            safety_flags_verified=True,
        )

    def test_empty_log(self):
        log = LabAttemptLogV1()
        assert len(log) == 0
        assert log.head_digest == NULL_SHA

    def test_append_chain(self):
        log = LabAttemptLogV1()
        r1 = self._make_receipt(NULL_SHA)
        log.append(r1)
        r2 = self._make_receipt(r1.receipt_digest)
        log.append(r2)
        assert len(log) == 2
        assert log.head_digest == r2.receipt_digest
        assert log.routed_count == 2

    def test_chain_break_rejected(self):
        log = LabAttemptLogV1()
        r1 = self._make_receipt(NULL_SHA)
        log.append(r1)
        # Wrong predecessor
        r_bad = self._make_receipt(NULL_SHA)   # should be r1.receipt_digest
        with pytest.raises(ValueError, match="Chain broken"):
            log.append(r_bad)

    def test_max_entries_enforced(self):
        log = LabAttemptLogV1(max_entries=2)
        r1 = self._make_receipt(NULL_SHA)
        log.append(r1)
        r2 = self._make_receipt(r1.receipt_digest)
        log.append(r2)
        r3 = self._make_receipt(r2.receipt_digest)
        with pytest.raises(OverflowError):
            log.append(r3)

    def test_summary_counts(self):
        log = LabAttemptLogV1()
        r1 = self._make_receipt(NULL_SHA)
        log.append(r1)
        s = log.summary()
        assert s["total"] == 1
        assert s["routed"] == 1
        assert s["quarantined"] == 0
        assert s["rejected"] == 0


# ---------------------------------------------------------------------------
# DataSourceIsolator
# ---------------------------------------------------------------------------

class TestDataSourceIsolator:
    def setup_method(self):
        self.iso = DataSourceIsolator()

    def test_good_evidence_admitted(self):
        result = self.iso.evaluate(GOOD_EVIDENCE)
        assert result.admitted
        assert result.verdict == QuarantineVerdict.ADMITTED.value
        assert result.rule_id is None

    def test_r1_unknown_evidence_class(self):
        ev = _make_evidence(
            evidence_class=EvidenceClass.UNKNOWN_UNVERIFIED.value,
            quarantine_status=ScannerQuarantineStatus.TEST_ONLY_SYNTHETIC.value,
        )
        result = self.iso.evaluate(ev)
        assert not result.admitted
        assert result.verdict == QuarantineVerdict.QUARANTINED_EVIDENCE_UNKNOWN.value
        assert result.rule_id == "R1"

    def test_r2_unknown_source_availability(self):
        ev = _make_evidence(source_availability=SourceAvailability.UNKNOWN.value)
        result = self.iso.evaluate(ev)
        assert result.verdict == QuarantineVerdict.QUARANTINED_UNDOCUMENTED_TIME.value
        assert result.rule_id == "R2"

    def test_r2_missing_source_availability(self):
        ev = _make_evidence(source_availability=SourceAvailability.MISSING.value)
        result = self.iso.evaluate(ev)
        assert result.verdict == QuarantineVerdict.QUARANTINED_UNDOCUMENTED_TIME.value
        assert result.rule_id == "R2"

    def test_r3_zero_cutoff(self):
        ev = _make_evidence(cutoff_ms=0)
        result = self.iso.evaluate(ev)
        assert result.verdict == QuarantineVerdict.QUARANTINED_UNDOCUMENTED_TIME.value
        assert result.rule_id == "R3"

    def test_r4_scanner_p0(self):
        ev = _make_evidence(
            quarantine_status=ScannerQuarantineStatus.UNKNOWN_DEFERRED.value
        )
        result = self.iso.evaluate(ev)
        assert result.verdict == QuarantineVerdict.QUARANTINED_SCANNER_P0.value
        assert result.rule_id == "R4"

    def test_r5_bad_dataset_version(self):
        """R5 triggers when source_dataset_version < 1.

        NominationEvidenceV1 itself enforces version ≥ 1 so we cannot
        build one with version=0.  We test the rule function directly —
        it reads only source_dataset_version from whatever object is passed.
        """
        from tools.strategy_discoverer_offline.data_isolator import _RULES

        # Find R5 rule function
        r5_fn = next(fn for rid, fn in _RULES if rid == "R5")

        # Build a minimal duck-typed object with the field R5 reads
        class _Stub:
            source_dataset_version = 0
        outcome = r5_fn(_Stub())
        assert outcome is not None
        verdict, reason = outcome
        assert verdict.value == QuarantineVerdict.QUARANTINED_UNDOCUMENTED_SRC.value
        assert "source_dataset_version" in reason

    def test_r6_empty_dataset_id(self):
        ev = _make_evidence(source_dataset_id="")
        result = self.iso.evaluate(ev)
        assert result.verdict == QuarantineVerdict.QUARANTINED_UNDOCUMENTED_SRC.value
        assert result.rule_id == "R6"

    def test_r1_takes_priority_over_r4(self):
        """R1 fires before R4 when both would trigger."""
        ev = _make_evidence(
            evidence_class=EvidenceClass.UNKNOWN_UNVERIFIED.value,
            quarantine_status=ScannerQuarantineStatus.UNKNOWN_DEFERRED.value,
        )
        result = self.iso.evaluate(ev)
        assert result.rule_id == "R1"

    def test_batch_evaluation(self):
        good_ev = GOOD_EVIDENCE
        bad_ev = _make_evidence(
            quarantine_status=ScannerQuarantineStatus.UNKNOWN_DEFERRED.value
        )
        admitted, quarantined = self.iso.evaluate_batch([good_ev, bad_ev])
        assert len(admitted) == 1
        assert len(quarantined) == 1
        assert quarantined[0].rule_id == "R4"

    def test_wrong_type_raises(self):
        with pytest.raises(TypeError):
            self.iso.evaluate("not an evidence object")


# ---------------------------------------------------------------------------
# DiscovererToFactoryBridge — routing
# ---------------------------------------------------------------------------

class TestDiscovererToFactoryBridge:
    def setup_method(self):
        self.bridge = DiscovererToFactoryBridge(ledger_reference="test-ledger")

    # --- Admitted path ------------------------------------------------------
    def test_route_admitted_evidence(self):
        result = self.bridge.route(
            package=GOOD_PACKAGE,
            evidence=GOOD_EVIDENCE,
            ledger_attempt_id="attempt-001",
            ledger_head_digest=NULL_SHA,
        )
        assert result.routed is True
        assert result.routing_status == FactoryRoutingStatus.ROUTED_SYNTHETIC_ONLY.value
        receipt = result.receipt
        assert receipt.holdout_accessed is False
        assert receipt.real_execution_initiated is False
        assert receipt.work_module_imported is False
        assert receipt.safety_flags_verified is True
        # Denominator must be populated
        assert receipt.denominator_snapshot.full_universe_denominator == 100
        assert receipt.denominator_snapshot.nominated == 60

    # --- Quarantine paths ---------------------------------------------------
    def test_route_scanner_p0_quarantined(self):
        ev = _make_evidence(
            quarantine_status=ScannerQuarantineStatus.UNKNOWN_DEFERRED.value
        )
        pkg = _make_package(ev)
        result = self.bridge.route(
            package=pkg, evidence=ev,
            ledger_attempt_id="attempt-002", ledger_head_digest=NULL_SHA,
        )
        assert result.routed is False
        assert result.routing_status == FactoryRoutingStatus.QUARANTINED_SCANNER_P0.value
        assert result.quarantine_rule == "R4"

    def test_route_undocumented_timing(self):
        ev = _make_evidence(cutoff_ms=0)
        pkg = _make_package(ev)
        result = self.bridge.route(
            package=pkg, evidence=ev,
            ledger_attempt_id="attempt-003", ledger_head_digest=NULL_SHA,
        )
        assert result.routing_status == FactoryRoutingStatus.QUARANTINED_UNDOCUMENTED_TIME.value

    def test_route_undocumented_source(self):
        ev = _make_evidence(source_dataset_id="")
        pkg = _make_package(ev)
        result = self.bridge.route(
            package=pkg, evidence=ev,
            ledger_attempt_id="attempt-004", ledger_head_digest=NULL_SHA,
        )
        assert result.routing_status == FactoryRoutingStatus.QUARANTINED_UNDOCUMENTED_SRC.value

    # --- Denominator logging ------------------------------------------------
    def test_denominator_logged_for_quarantined(self):
        """Denominator is captured even for quarantined attempts."""
        ev = _make_evidence(
            quarantine_status=ScannerQuarantineStatus.UNKNOWN_DEFERRED.value,
            full_universe_denominator=500,
            eligible_selected=200,
            nominated=50,
        )
        pkg = _make_package(ev)
        result = self.bridge.route(
            package=pkg, evidence=ev,
            ledger_attempt_id="attempt-005", ledger_head_digest=NULL_SHA,
        )
        snap = result.receipt.denominator_snapshot
        assert snap.full_universe_denominator == 500
        assert snap.eligible_selected == 200
        assert snap.nominated == 50

    # --- Log chain ----------------------------------------------------------
    def test_log_chain_across_routes(self):
        """Receipt chain is maintained across consecutive routes."""
        for i in range(3):
            ev = _make_evidence()
            pkg = _make_package(ev)
            # Use current ledger head from previous round
            prev_head = NULL_SHA
            self.bridge.route(
                package=pkg, evidence=ev,
                ledger_attempt_id=f"attempt-{i:03d}",
                ledger_head_digest=prev_head,
            )
        assert len(self.bridge.log) == 3
        receipts = self.bridge.log.receipts
        for j in range(1, 3):
            assert receipts[j].predecessor_receipt_digest == receipts[j - 1].receipt_digest

    # --- Batch routing ------------------------------------------------------
    def test_batch_routing(self):
        pairs = [
            (GOOD_PACKAGE, GOOD_EVIDENCE),
            (_make_package(_make_evidence(cutoff_ms=0)),
             _make_evidence(cutoff_ms=0)),
        ]
        results = self.bridge.route_batch(
            pairs=pairs, ledger_head_digest=NULL_SHA
        )
        assert len(results) == 2
        assert results[0].routed is True
        assert results[1].routed is False

    # --- Summary ------------------------------------------------------------
    def test_summary(self):
        result = self.bridge.route(
            package=GOOD_PACKAGE, evidence=GOOD_EVIDENCE,
            ledger_attempt_id="x", ledger_head_digest=NULL_SHA,
        )
        s = self.bridge.summary()
        assert s["total"] == 1
        assert s["routed"] == 1
        assert s["ledger_reference"] == "test-ledger"

    # --- Wrong type guards --------------------------------------------------
    def test_wrong_package_type_raises(self):
        with pytest.raises(TypeError):
            self.bridge.route(
                package="not a package",
                evidence=GOOD_EVIDENCE,
                ledger_attempt_id="x",
                ledger_head_digest=NULL_SHA,
            )

    def test_wrong_evidence_type_raises(self):
        with pytest.raises(TypeError):
            self.bridge.route(
                package=GOOD_PACKAGE,
                evidence="not evidence",
                ledger_attempt_id="x",
                ledger_head_digest=NULL_SHA,
            )


# ---------------------------------------------------------------------------
# Safety flags — independent re-verification
# ---------------------------------------------------------------------------

class TestSafetyFlagVerification:
    def test_good_package_passes(self):
        # Must not raise
        _verify_package_safety(GOOD_PACKAGE)

    def test_holdout_flag_blocked(self):
        """Bridge independently re-verifies holdout status."""
        # We can only test this via checking what _verify_package_safety looks at
        # (DiscoveryCandidatePackageV1 itself enforces it, so we verify the bridge's check)
        # Create a mock-like object by bypassing frozen dataclass
        import copy
        bad_pkg = copy.copy(GOOD_PACKAGE)
        # Force the field value (bypassing frozen; for test only)
        object.__setattr__(bad_pkg, "holdout_status", "HOLDOUT_OPEN")
        # Also need to relax factory check temporarily — patch __post_init__ is not feasible
        # Instead verify that the bridge's _verify_package_safety function catches it:
        with pytest.raises(SafetyFlagError, match="holdout_status"):
            _verify_package_safety(bad_pkg)

    def test_holdout_not_accessed_on_quarantine(self):
        """Even when quarantined, holdout must not be accessed."""
        ev = _make_evidence(cutoff_ms=0)
        pkg = _make_package(ev)
        bridge = DiscovererToFactoryBridge()
        result = bridge.route(
            package=pkg, evidence=ev,
            ledger_attempt_id="x", ledger_head_digest=NULL_SHA,
        )
        assert result.receipt.holdout_accessed is False
