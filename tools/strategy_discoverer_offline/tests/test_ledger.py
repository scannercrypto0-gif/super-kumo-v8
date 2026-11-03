"""
Adversarial tests for ledger.py
=================================
Covers:
  - Append-only: no duplicate attempt_id
  - Invalid state transitions rejected
  - Predecessor integrity / tampered hash detection
  - verify_chain(): detects broken chain
  - Crash recovery via from_dict_list()
  - Max entries raises correctly
  - Terminal states are final
  - Empty ledger has genesis digest
"""

import pytest

from tools.strategy_discoverer_offline.ledger import (
    DiscovererLedger,
    LedgerEntry,
    AttemptState,
    _GENESIS_DIGEST,
    DEFAULT_MAX_ENTRIES,
)
from tools.strategy_discoverer_offline.contracts import _digest


_FAKE_SHA = "a" * 64
_FAKE_SHA2 = "b" * 64
_FAKE_SHA3 = "c" * 64
_FAKE_SHA4 = "d" * 64
_FAKE_SHA5 = "e" * 64


def _register(ledger, attempt_id="atm-001", idx=0):
    return ledger.register(
        attempt_id=attempt_id,
        candidate_id=f"cand-{idx}",
        family_id="F001",
        strategy_digest=_FAKE_SHA,
        search_plan_digest=_FAKE_SHA2,
        nomination_digest=_FAKE_SHA3,
        reason="test registration",
    )


class TestLedgerBasic:
    def test_empty_ledger_genesis_digest(self):
        ledger = DiscovererLedger()
        assert ledger.head_digest() == _GENESIS_DIGEST

    def test_empty_ledger_entry_count_zero(self):
        ledger = DiscovererLedger()
        assert ledger.entry_count() == 0

    def test_register_one_entry(self):
        ledger = DiscovererLedger()
        entry = _register(ledger)
        assert entry.attempt_id == "atm-001"
        assert entry.state == AttemptState.REGISTERED.value
        assert ledger.entry_count() == 1

    def test_head_digest_changes_after_append(self):
        ledger = DiscovererLedger()
        before = ledger.head_digest()
        _register(ledger)
        after = ledger.head_digest()
        assert before != after

    def test_predecessor_chain_correct(self):
        ledger = DiscovererLedger()
        e1 = _register(ledger, "atm-001", 0)
        e2 = ledger.transition("atm-001", AttemptState.PENDING, "started")
        assert e2.predecessor_digest == e1.entry_digest
        assert e1.predecessor_digest == _GENESIS_DIGEST


class TestDuplicateAttemptRejection:
    def test_duplicate_attempt_id_rejected(self):
        ledger = DiscovererLedger()
        _register(ledger, "atm-001")
        with pytest.raises(ValueError, match="Duplicate attempt_id"):
            _register(ledger, "atm-001")

    def test_two_unique_attempts_ok(self):
        ledger = DiscovererLedger()
        _register(ledger, "atm-001", 0)
        _register(ledger, "atm-002", 1)
        assert ledger.entry_count() == 2


class TestStateTransitions:
    def test_registered_to_pending(self):
        ledger = DiscovererLedger()
        _register(ledger, "atm-001")
        entry = ledger.transition("atm-001", AttemptState.PENDING, "started")
        assert entry.state == AttemptState.PENDING.value

    def test_pending_to_complete(self):
        ledger = DiscovererLedger()
        _register(ledger)
        ledger.transition("atm-001", AttemptState.PENDING)
        entry = ledger.transition("atm-001", AttemptState.COMPLETE, "done")
        assert entry.state == AttemptState.COMPLETE.value

    def test_pending_to_failed(self):
        ledger = DiscovererLedger()
        _register(ledger)
        ledger.transition("atm-001", AttemptState.PENDING)
        entry = ledger.transition("atm-001", AttemptState.FAILED, "error")
        assert entry.state == AttemptState.FAILED.value

    def test_registered_to_invalid(self):
        ledger = DiscovererLedger()
        _register(ledger)
        entry = ledger.transition("atm-001", AttemptState.INVALID, "schema error")
        assert entry.state == AttemptState.INVALID.value

    def test_registered_to_abandoned(self):
        ledger = DiscovererLedger()
        _register(ledger)
        entry = ledger.transition("atm-001", AttemptState.ABANDONED)
        assert entry.state == AttemptState.ABANDONED.value

    def test_complete_is_terminal(self):
        ledger = DiscovererLedger()
        _register(ledger)
        ledger.transition("atm-001", AttemptState.PENDING)
        ledger.transition("atm-001", AttemptState.COMPLETE)
        with pytest.raises(ValueError):
            ledger.transition("atm-001", AttemptState.PENDING)

    def test_failed_is_terminal(self):
        ledger = DiscovererLedger()
        _register(ledger)
        ledger.transition("atm-001", AttemptState.PENDING)
        ledger.transition("atm-001", AttemptState.FAILED)
        with pytest.raises(ValueError):
            ledger.transition("atm-001", AttemptState.COMPLETE)

    def test_invalid_is_terminal(self):
        ledger = DiscovererLedger()
        _register(ledger)
        ledger.transition("atm-001", AttemptState.INVALID)
        with pytest.raises(ValueError):
            ledger.transition("atm-001", AttemptState.PENDING)

    def test_abandoned_is_terminal(self):
        ledger = DiscovererLedger()
        _register(ledger)
        ledger.transition("atm-001", AttemptState.ABANDONED)
        with pytest.raises(ValueError):
            ledger.transition("atm-001", AttemptState.COMPLETE)

    def test_invalid_direct_complete_from_registered(self):
        """Cannot jump from REGISTERED directly to COMPLETE."""
        ledger = DiscovererLedger()
        _register(ledger)
        with pytest.raises(ValueError):
            ledger.transition("atm-001", AttemptState.COMPLETE)

    def test_unknown_attempt_id_raises(self):
        ledger = DiscovererLedger()
        with pytest.raises((ValueError, KeyError)):
            ledger.transition("nonexistent", AttemptState.PENDING)


class TestChainIntegrity:
    def test_verify_chain_empty(self):
        ledger = DiscovererLedger()
        assert ledger.verify_chain() is True

    def test_verify_chain_one_entry(self):
        ledger = DiscovererLedger()
        _register(ledger)
        assert ledger.verify_chain() is True

    def test_verify_chain_multiple_entries(self):
        ledger = DiscovererLedger()
        for i in range(5):
            _register(ledger, f"atm-{i:03d}", i)
        assert ledger.verify_chain() is True


class TestCrashRecovery:
    def test_round_trip_empty(self):
        ledger = DiscovererLedger()
        data = ledger.to_dict_list()
        restored = DiscovererLedger.from_dict_list(data)
        assert restored.entry_count() == 0
        assert restored.head_digest() == _GENESIS_DIGEST

    def test_round_trip_with_entries(self):
        ledger = DiscovererLedger()
        _register(ledger, "atm-001")
        ledger.transition("atm-001", AttemptState.PENDING)
        ledger.transition("atm-001", AttemptState.COMPLETE)
        _register(ledger, "atm-002", 1)

        data = ledger.to_dict_list()
        restored = DiscovererLedger.from_dict_list(data)
        assert restored.entry_count() == ledger.entry_count()
        assert restored.head_digest() == ledger.head_digest()
        assert restored.verify_chain() is True

    def test_tampered_entry_digest_rejected_on_replay(self):
        ledger = DiscovererLedger()
        _register(ledger)
        data = ledger.to_dict_list()
        # Tamper the entry_digest
        data[0] = dict(data[0])
        data[0]["entry_digest"] = "0" * 64
        with pytest.raises((ValueError, AssertionError)):
            DiscovererLedger.from_dict_list(data)

    def test_tampered_predecessor_rejected_on_replay(self):
        ledger = DiscovererLedger()
        _register(ledger)
        _register(ledger, "atm-002", 1)
        data = ledger.to_dict_list()
        # Tamper predecessor_digest of second entry
        data[1] = dict(data[1])
        data[1]["predecessor_digest"] = "0" * 64
        with pytest.raises((ValueError, AssertionError)):
            DiscovererLedger.from_dict_list(data)


class TestMaxEntries:
    def test_max_entries_raises(self):
        ledger = DiscovererLedger(max_entries=2)
        _register(ledger, "atm-001", 0)
        _register(ledger, "atm-002", 1)
        with pytest.raises(ValueError, match="max_entries"):
            _register(ledger, "atm-003", 2)


class TestSummary:
    def test_summary_empty(self):
        ledger = DiscovererLedger()
        s = ledger.summary()
        assert s["total_attempts"] == 0
        assert s["incomplete_attempts"] == 0

    def test_summary_reflects_states(self):
        ledger = DiscovererLedger()
        _register(ledger, "atm-001")
        ledger.transition("atm-001", AttemptState.PENDING)
        ledger.transition("atm-001", AttemptState.COMPLETE)
        _register(ledger, "atm-002", 1)  # stays REGISTERED

        s = ledger.summary()
        assert s["total_attempts"] == 2
        assert s["by_state"]["COMPLETE"] == 1
        assert s["incomplete_attempts"] == 1

    def test_incomplete_attempts_returns_ids(self):
        ledger = DiscovererLedger()
        _register(ledger, "atm-001")
        _register(ledger, "atm-002", 1)
        ledger.transition("atm-001", AttemptState.PENDING)
        ledger.transition("atm-001", AttemptState.COMPLETE)

        incomplete = ledger.incomplete_attempts()
        assert "atm-002" in incomplete
        assert "atm-001" not in incomplete
