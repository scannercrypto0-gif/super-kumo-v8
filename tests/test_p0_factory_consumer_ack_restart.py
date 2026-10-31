"""Focused P0 F4↔C2 durable no-effect handshake regression tests.

Synthetic-only: tests protocol and process restart, not owner historical bytes.
"""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import json
import subprocess
import sys

import pytest

from research_wp_r0.aql_p0_c1_custody import MANIFEST_SHA
from research_wp_r0.aql_p0_c2_producer import (
    DecisionEnvelope, DurableJournal, C2ConflictError, POLICY_ID,
    _assumptions_digest, load_journal,
)
from research_wp_r0.aql_p0_f4_ledger import (
    LedgerState, LedgerIdentityError, LedgerReceiptCorrupted,
    persist_consumer_effect_receipts,
)


def _envelope():
    return DecisionEnvelope(
        schema="aql.p0.historical-decision.v1", trial_id="synthetic-trial",
        run_manifest_sha256="b" * 64, dataset_id="BTCUSDT-SPOT-15m",
        dataset_version=1, strategy_id="synthetic-strategy",
        strategy_version="1", strategy_digest="c" * 64,
        strategy_instance_id="synthetic-instance", account_id="synthetic-account",
        opportunity_id="synthetic-opp", decision_ms=1001,
        decision_cutoff_ms=1000, prefix_start_ms=0,
        prefix_end_exclusive_ms=1000, prefix_bar_checksums_sha256="d" * 64,
        feature_policy_version="synthetic-v1", gap_inventory_sha256="e" * 64,
        correction_lineage_sha256="f" * 64, coverage_status="COMPLETE",
        availability_mode="RETROSPECTIVE_NON_PIT",
        source_lag_assumption_ms=1000, latency_assumption_ms=1000,
        producer_event_id="synthetic-producer", input_disposition="EVALUABLE_RETROSPECTIVE",
        reason_code=None, envelope_sha256="a" * 64,
    )


def _persist(tmp_path, env, assumptions=None):
    return persist_consumer_effect_receipts(
        directory=tmp_path / "factory", envelopes=[env],
        opportunities=[SimpleNamespace(opportunity_id=env.opportunity_id)],
        fill_results=[SimpleNamespace(opportunity_id=env.opportunity_id, signal_state="NO_SIGNAL")],
        state=LedgerState(), manifest_sha256=MANIFEST_SHA,
        assumptions_digest=assumptions or _assumptions_digest(
            env.source_lag_assumption_ms, env.latency_assumption_ms
        ),
    )


def test_assumptions_cannot_be_forged_by_caller(tmp_path):
    env = _envelope()
    with pytest.raises(LedgerIdentityError, match="CONSUMER_ASSUMPTIONS_ENVELOPE_MISMATCH"):
        _persist(tmp_path, env, "2" * 64)
    assert not (tmp_path / "factory" / "synthetic-producer.json").exists()


def test_durable_no_effect_receipt_survives_restart_and_ack_is_idempotent(tmp_path):
    env = _envelope()
    assumptions = _assumptions_digest(env.source_lag_assumption_ms, env.latency_assumption_ms)
    journal_path = tmp_path / "producer.jsonl"
    journal = DurableJournal(journal_path)
    journal.write_pending(
        env.producer_event_id, env.opportunity_id, env.envelope_sha256,
        source_bytes_sha256="9" * 64, run_manifest_sha256=env.run_manifest_sha256,
        trial_id=env.trial_id, strategy_digest=env.strategy_digest,
        policy_id=POLICY_ID, assumptions_digest=assumptions,
    )
    journal.transition_applied(env.producer_event_id)
    with pytest.raises(C2ConflictError, match="ACK_CONSUMER_RECEIPT_REQUIRED"):
        journal.transition_acked([env.producer_event_id])

    paths = _persist(tmp_path, env)
    assert json.loads(Path(paths[env.producer_event_id]).read_text())["ordered_financial_event_ids"] == []
    assert _persist(tmp_path, env) == paths  # duplicate same bytes is a no-op

    # Actual separate Python process must reload producer and downstream receipt.
    repo_root = str(Path(__file__).resolve().parents[1])
    script = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from research_wp_r0.aql_p0_c2_producer import load_journal
journal = load_journal(Path(sys.argv[2]))
receipt = sys.argv[3]
pid = 'synthetic-producer'
assert journal.transition_acked([pid], {pid: receipt}) == 1
assert load_journal(Path(sys.argv[2])).transition_acked([pid], {pid: receipt}) == 0
"""
    proc = subprocess.run(
        [sys.executable, "-c", script, repo_root, str(journal_path),
         paths[env.producer_event_id]], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_conflicting_effect_receipt_fails_closed(tmp_path):
    env = _envelope()
    paths = _persist(tmp_path, env)
    receipt = Path(paths[env.producer_event_id])
    doc = json.loads(receipt.read_text())
    doc["effect_disposition"] = "TRIGGERED"
    receipt.write_text(json.dumps(doc))
    with pytest.raises(LedgerReceiptCorrupted, match="CONSUMER_RECEIPT_CONFLICT"):
        _persist(tmp_path, env)


def test_owner_source_attestation_requires_actual_three_original_domains(tmp_path):
    """No fabricated input, no hash-only bypass, no receipt on failure."""
    from research_wp_r0.aql_p0_c1_custody import SourceCustodyError
    from scripts.verify_p0_owner_source_bytes import verify_owner_evidence
    outer = tmp_path / "outer.zip"
    manifest = tmp_path / "manifest.json"
    normalized = tmp_path / "normalized.json"
    for p in (outer, manifest, normalized):
        p.write_bytes(b"synthetic-not-owner-original")
    with pytest.raises(SourceCustodyError, match="OUTER_ZIP_SHA256_MISMATCH"):
        verify_owner_evidence(outer, manifest, normalized)


def test_f4_rejects_unverified_caller_manifest_before_writing(tmp_path):
    env = _envelope()
    with pytest.raises(Exception, match="CONSUMER_SOURCE_MANIFEST_MISMATCH"):
        persist_consumer_effect_receipts(
            directory=tmp_path / "factory", envelopes=[env],
            opportunities=[SimpleNamespace(opportunity_id=env.opportunity_id)],
            fill_results=[SimpleNamespace(opportunity_id=env.opportunity_id, signal_state="NO_SIGNAL")],
            state=LedgerState(), manifest_sha256="1" * 64,
            assumptions_digest=_assumptions_digest(env.source_lag_assumption_ms, env.latency_assumption_ms),
        )
    assert not (tmp_path / "factory").exists()


def test_f4_preflight_rejects_bad_later_envelope_without_orphaned_effects(tmp_path):
    from research_wp_r0.aql_p0_f4_ledger import LedgerEvent, FinancialReceipt
    from decimal import Decimal
    env = _envelope()
    env2 = replace(env, producer_event_id="second-producer", opportunity_id="second-opp")
    event = LedgerEvent(
        event_id="financial-entry", opportunity_id=env.opportunity_id,
        kind="ENTRY_DEBIT", bar_open_ms=1100, price_net=Decimal("100"),
        quantity_btc=Decimal("1"), fee=Decimal("0"), cost_basis=Decimal("100"),
        cash_delta=Decimal("-100"), cumulative_cash=None,
        held_btc_delta=Decimal("1"), cumulative_held_btc=None,
    )
    state = LedgerState()
    state._receipts = [FinancialReceipt.from_event(event)]
    with pytest.raises(LedgerIdentityError, match="CONSUMER_RECEIPT_IDENTITY_MISMATCH"):
        persist_consumer_effect_receipts(
            directory=tmp_path / "factory", envelopes=[env, env2],
            opportunities=[
                SimpleNamespace(opportunity_id=env.opportunity_id),
                SimpleNamespace(opportunity_id="wrong-second-opp"),
            ],
            fill_results=[
                SimpleNamespace(opportunity_id=env.opportunity_id, signal_state="TRIGGERED"),
                SimpleNamespace(opportunity_id=env2.opportunity_id, signal_state="NO_SIGNAL"),
            ],
            state=state, manifest_sha256=MANIFEST_SHA,
            assumptions_digest=_assumptions_digest(env.source_lag_assumption_ms, env.latency_assumption_ms),
        )
    assert not (tmp_path / "factory" / "financial_receipts.jsonl").exists()


def test_positive_financial_receipt_ack_restart_and_tamper(tmp_path):
    from research_wp_r0.aql_p0_f4_ledger import LedgerEvent, FinancialReceipt
    from decimal import Decimal
    env = _envelope()
    assumptions = _assumptions_digest(env.source_lag_assumption_ms, env.latency_assumption_ms)
    journal_path = tmp_path / "producer.jsonl"
    journal = DurableJournal(journal_path)
    journal.write_pending(
        env.producer_event_id, env.opportunity_id, env.envelope_sha256,
        source_bytes_sha256="9" * 64, run_manifest_sha256=env.run_manifest_sha256,
        trial_id=env.trial_id, strategy_digest=env.strategy_digest,
        policy_id=POLICY_ID, assumptions_digest=assumptions,
    )
    journal.transition_applied(env.producer_event_id)
    event = LedgerEvent(
        event_id="synthetic-financial-entry", opportunity_id=env.opportunity_id,
        kind="ENTRY_DEBIT", bar_open_ms=1100, price_net=Decimal("100"),
        quantity_btc=Decimal("1"), fee=Decimal("0"), cost_basis=Decimal("100"),
        cash_delta=Decimal("-100"), cumulative_cash=None,
        held_btc_delta=Decimal("1"), cumulative_held_btc=None,
    )
    state = LedgerState()
    state._receipts = [FinancialReceipt.from_event(event)]
    paths = persist_consumer_effect_receipts(
        directory=tmp_path / "factory", envelopes=[env],
        opportunities=[SimpleNamespace(opportunity_id=env.opportunity_id)],
        fill_results=[SimpleNamespace(opportunity_id=env.opportunity_id, signal_state="TRIGGERED")],
        state=state, manifest_sha256=MANIFEST_SHA, assumptions_digest=assumptions,
    )
    assert persist_consumer_effect_receipts(
        directory=tmp_path / "factory", envelopes=[env],
        opportunities=[SimpleNamespace(opportunity_id=env.opportunity_id)],
        fill_results=[SimpleNamespace(opportunity_id=env.opportunity_id, signal_state="TRIGGERED")],
        state=state, manifest_sha256=MANIFEST_SHA, assumptions_digest=assumptions,
    ) == paths
    script = """
import sys
from pathlib import Path
from research_wp_r0.aql_p0_c2_producer import load_journal
journal = load_journal(Path(sys.argv[1]))
pid = 'synthetic-producer'
assert journal.transition_acked([pid], {pid: sys.argv[2]}) == 1
assert load_journal(Path(sys.argv[1])).transition_acked([pid], {pid: sys.argv[2]}) == 0
"""
    proc = subprocess.run([sys.executable, "-c", script, str(journal_path), paths[env.producer_event_id]],
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    # Mutated financial journal must invalidate a fresh replay of the receipt.
    financial = tmp_path / "factory" / "financial_receipts.jsonl"
    data = financial.read_text()
    financial.write_text(data.replace("synthetic-financial-entry", "tampered-financial-entry"))
    journal2 = DurableJournal(tmp_path / "producer2.jsonl")
    journal2.write_pending(
        env.producer_event_id, env.opportunity_id, env.envelope_sha256,
        source_bytes_sha256="9" * 64, run_manifest_sha256=env.run_manifest_sha256,
        trial_id=env.trial_id, strategy_digest=env.strategy_digest,
        policy_id=POLICY_ID, assumptions_digest=assumptions,
    )
    journal2.transition_applied(env.producer_event_id)
    with pytest.raises(C2ConflictError):
        journal2.transition_acked([env.producer_event_id], paths)
