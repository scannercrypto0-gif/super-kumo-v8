"""Factory-only pre-write admission for an already frozen full research plan.

This is a single-writer *adapter* to the existing durable AttemptLedger.
The manifest digest must be retained separately; this module does not
provide independent custody, evaluation, or cross-database atomicity.
"""
from .attempt_ledger import AttemptLedger
from .frozen_research_plan import verify_research_plan
from .frozen_plan_reconciliation import reconcile_full_research_plan


class FrozenAttemptWriter:
    def __init__(self, ledger, raw_plan, expected_digest):
        if not isinstance(ledger, AttemptLedger):
            raise ValueError("Real Factory AttemptLedger required")
        self.ledger = ledger
        self.raw_plan = raw_plan
        self.expected_digest = expected_digest
        plan = verify_research_plan(raw_plan, expected_digest)
        self.family_id = plan["family_id"]
        self.allowed = {r["candidate_id"]: r["strategy_digest"]
                        for r in plan["candidates"]}
        # Enrollment and legacy-history rejection are atomic with ledger writes.
        # Reconciliation alone does not install the durable membership policy.
        ledger.bind_frozen_plan(raw_plan, expected_digest)
        reconcile_full_research_plan(raw_plan, expected_digest, ledger)

    def record_attempt(self, event):
        """Validate before writing, then delegate atomic append to real ledger.

        The ledger's sealed policy is authoritative even for direct callers;
        this callback adds validation, but cannot replace plan membership.
        """
        if type(event) is not dict or event.get("family_id") != self.family_id:
            raise ValueError("Wrong frozen experiment family")
        candidate = event.get("candidate_id")
        if candidate not in self.allowed:
            raise ValueError("Candidate not in frozen plan")
        if event.get("strategy_digest") != self.allowed[candidate]:
            raise ValueError("Strategy differs from frozen plan")
        if event.get("state") not in {"PENDING", "INPUTS", "FAILED", "ABANDONED", "INVALID"}:
            raise ValueError("Unsupported attempt state")
        # This read-only inventory is diagnostic. Membership is enforced again
        # inside the ledger's BEGIN IMMEDIATE transaction, not by this read.
        reconcile_full_research_plan(self.raw_plan, self.expected_digest, self.ledger)
        def admission(candidate_event, prior_events, prior_checkpoint):
            for prior in prior_events:
                if prior["family_id"] != self.family_id:
                    continue
                cid = prior["candidate_id"]
                if cid not in self.allowed or prior.get("strategy_digest") != self.allowed[cid]:
                    raise ValueError("Existing attempt violates frozen plan")
            if candidate_event["candidate_id"] not in self.allowed or (
                candidate_event.get("strategy_digest") != self.allowed[candidate_event["candidate_id"]]
            ):
                raise ValueError("Attempt violates frozen plan")
        checkpoint = self.ledger.record_attempt(event, admission=admission)
        reconcile_full_research_plan(self.raw_plan, self.expected_digest, self.ledger)
        return checkpoint
