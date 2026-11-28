import sqlite3

import pytest

from research_wp_r0.attempt_ledger import AttemptLedger


def _event():
    return {
        "state": "PENDING",
        "family_id": "Family1",
        "candidate_id": "Candidate1",
        "input_digest": "f" * 64,
        "strategy_digest": "a" * 64,
    }


def _policy_and_receipt_count(path):
    with sqlite3.connect(path) as db:
        policy = db.execute(
            "SELECT require_admission FROM ledger_policy WHERE id=1"
        ).fetchone()[0]
        count = db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]
    return policy, count


def test_rejected_open_does_not_change_existing_unsealed_ledger(tmp_path):
    path = tmp_path / "attempts.sqlite"
    ledger = AttemptLedger(path)
    ledger.record_attempt(_event())
    before = _policy_and_receipt_count(path)
    assert before == (0, 1)

    with pytest.raises(ValueError, match="explicit frozen-plan enrollment"):
        AttemptLedger(path, require_admission=True)

    assert _policy_and_receipt_count(path) == before


def test_new_empty_ledger_can_still_start_with_admission_required(tmp_path):
    path = tmp_path / "protected.sqlite"
    ledger = AttemptLedger(path, require_admission=True)

    assert ledger.require_admission is True
    assert _policy_and_receipt_count(path) == (1, 0)

