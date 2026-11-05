"""Package E fail-closed independent Discoverer research intake admission.

Admitted here means *eligible for Factory's research consumer*, not evaluated.
Factory owns its actual Lab execution and any consumer acknowledgement.
"""
from __future__ import annotations

from dataclasses import dataclass
from tools.strategy_discoverer_offline.contracts import _digest
from tools.strategy_discoverer_offline.factory_lab_consumer_contract import build_research_intake
from tools.strategy_discoverer_offline.ledger_membership_verifier import verify_ledger_membership


@dataclass(frozen=True)
class ResearchHandoffDecisionV1:
    status: str
    candidate_id: str
    package_digest: str
    intake_digest: str | None
    membership_verification_digest: str | None
    reason: str
    decision_digest: str

    @classmethod
    def build(cls, *, status, candidate_id, package_digest,
              intake_digest=None, membership_verification_digest=None, reason=""):
        fields = dict(status=status, candidate_id=candidate_id, package_digest=package_digest,
                      intake_digest=intake_digest,
                      membership_verification_digest=membership_verification_digest,
                      reason=reason)
        return cls(**fields, decision_digest=_digest(fields))


class VerifiedResearchHandoff:
    """Records every attempt, including rejected, quarantined and duplicate attempts."""

    def __init__(self, ledger_reference: str):
        if not ledger_reference or not isinstance(ledger_reference, str):
            raise ValueError("ledger_reference required")
        self.ledger_reference = ledger_reference
        self._decisions: list[ResearchHandoffDecisionV1] = []
        self._accepted: dict[str, str] = {}

    def decisions(self):
        return tuple(self._decisions)

    def handoff(self, *, package, evidence, receipt, entries_data,
                attempt_log_head_digest, ledger_attempt_id, ledger_head_digest):
        intake = None
        membership = None
        try:
            if receipt.routing_status != "ROUTED_SYNTHETIC_ONLY":
                raise ValueError("candidate route is not admitted")
            identity = {
                "package_digest": (receipt.package_digest, package.package_digest),
                "candidate_id": (receipt.candidate_id, package.candidate_id),
                "family_id": (receipt.family_id, package.family_id),
                "strategy_definition_digest": (
                    receipt.strategy_definition_digest, package.strategy_definition_digest),
                "nomination_evidence_digest": (
                    receipt.nomination_evidence_digest, evidence.nomination_digest),
                "package_nomination_digest": (
                    package.nomination_evidence_digest, evidence.nomination_digest),
                "ledger_attempt_id": (receipt.ledger_attempt_id, ledger_attempt_id),
                "ledger_head_digest": (receipt.ledger_head_digest, ledger_head_digest),
            }
            mismatched = [k for k, (a, b) in identity.items() if a != b]
            if mismatched:
                raise ValueError("cross-object binding mismatch: " + ",".join(mismatched))
            membership = verify_ledger_membership(
                entries_data=entries_data, package=package,
                ledger_attempt_id=ledger_attempt_id,
                ledger_head_digest=ledger_head_digest,
                ledger_reference=self.ledger_reference,
            )
            if package.package_digest in self._accepted:
                raise ValueError("duplicate package handoff")
            if not isinstance(attempt_log_head_digest, str):
                raise ValueError("attempt log head missing")
            # Existing proposed contract deliberately remains NOT_VERIFIED:
            # only the separately validated membership result upgrades
            # admission; no self-issued LedgerMembershipProofV1 is trusted.
            intake = build_research_intake(
                package=package, receipt=receipt,
                attempt_log_head_digest=attempt_log_head_digest,
                ledger_reference=self.ledger_reference,
            )
            self._accepted[package.package_digest] = intake.intake_digest
            decision = ResearchHandoffDecisionV1.build(
                status="ELIGIBLE_FOR_FACTORY_RESEARCH",
                candidate_id=package.candidate_id,
                package_digest=package.package_digest,
                intake_digest=intake.intake_digest,
                membership_verification_digest=membership.verification_digest,
                reason="ledger checkpoint and complete identity binding verified; Factory consumer unconnected",
            )
        except (TypeError, ValueError, AttributeError, KeyError) as exc:
            decision = ResearchHandoffDecisionV1.build(
                status="REJECTED_OR_QUARANTINED_NOT_VERIFIED",
                candidate_id=getattr(package, "candidate_id", "UNKNOWN"),
                package_digest=getattr(package, "package_digest", "0" * 64),
                reason=str(exc),
            )
        self._decisions.append(decision)
        return decision, intake, membership
