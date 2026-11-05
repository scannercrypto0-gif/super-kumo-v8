"""ATLAS Package F4: bounded retrospective original-cohort research intake contract.

A candidate is a research proposal, never an operational strategy approval.
The envelope cannot be minted from synthetic-only Discoverer bridge routing.
Independent source/approval custody is NOT established merely by this SHA.
No Core/Scanner/Factory branch imports and no remote data reads.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from tools.strategy_discoverer_offline.contracts import _digest
from tools.strategy_discoverer_offline.durable_checkpoint_e import DurableDiscovererCheckpoint

SCHEMA = "aql.discoverer.f4.original-cohort-research-intake.v1"
WAIT = "WAIT_INDEPENDENT_SOURCE_AND_POLICY"
ELIGIBLE = "READY_FOR_FACTORY_RESEARCH_INTAKE"
ZERO = "0" * 64


class F4ContractError(ValueError):
    pass


def _sha(value, name):
    if not isinstance(value, str) or len(value) != 64 or any(
        ch not in "0123456789abcdef" for ch in value
    ) or value == ZERO:
        raise F4ContractError(f"{name}: independently verified nonzero SHA-256 required")


@dataclass(frozen=True)
class F4RetrospectiveEvidence:
    """Externally supplied per-cohort evidence, not a discoverer self-attestation.

    Custody identity and policy approval MUST be checked again by Factory
    against Core and independently authorized strategy-policy registers.
    """
    source_kind: str
    symbol: str
    timeframe: str
    market: str
    source_dataset_id: str
    source_manifest_sha256: Optional[str]
    publisher_checksum_sha256: Optional[str]
    original_archive_sha256: Optional[str]
    core_245_query_sha256: Optional[str]
    core_253_query_sha256: Optional[str]
    independent_source_verifier_sha256: Optional[str]
    independent_research_policy_approval_sha256: Optional[str]
    cutoff_ms: int
    first_bar_open_ms: int
    last_bar_open_ms: int
    historical_pit: str = "RETROSPECTIVE_NON_PIT"

    def __post_init__(self):
        if self.historical_pit != "RETROSPECTIVE_NON_PIT":
            raise F4ContractError("PIT promotion unavailable in Discoverer F4")
        if type(self.cutoff_ms) is not int or type(self.first_bar_open_ms) is not int or type(self.last_bar_open_ms) is not int:
            raise F4ContractError("timestamps must be integer milliseconds")
        if self.first_bar_open_ms < 0 or self.last_bar_open_ms < self.first_bar_open_ms:
            raise F4ContractError("invalid cohort bar window")
        if self.cutoff_ms < self.last_bar_open_ms + 900000:
            raise F4ContractError("cutoff before last closed 15m bar")
        if self.source_kind != "ORIGINAL_PUBLISHER" or self.symbol != "BTCUSDT" or self.timeframe != "15m" or self.market != "BINANCE:SPOT:USDT":
            raise F4ContractError("F4 source identity mismatch")

    def to_dict(self):
        return dict(self.__dict__)

    def validate_admitted(self):
        if not self.source_dataset_id:
            raise F4ContractError("missing source dataset id")
        for name in (
            "source_manifest_sha256", "publisher_checksum_sha256",
            "original_archive_sha256", "core_245_query_sha256",
            "core_253_query_sha256", "independent_source_verifier_sha256",
            "independent_research_policy_approval_sha256"
        ):
            _sha(getattr(self, name), name)
        if self.core_245_query_sha256 == self.core_253_query_sha256:
            raise F4ContractError("distinct Core245/Core253 query parents required")


@dataclass(frozen=True)
class F4ResearchIntake:
    schema_version: str
    status: str
    reason: str
    candidate_id: str
    package_digest: str
    nomination_digest: str
    strategy_digest: str
    ledger_checkpoint_sha256: Optional[str]
    membership_verification_sha256: Optional[str]
    ledger_attempt_id: str
    source_evidence: dict
    evaluation_status: str
    strategy_approval_status: str
    factory_consumer_status: str
    holdout_accessed: bool
    trading_authority: str
    intake_digest: str

    def __post_init__(self):
        if self.schema_version != SCHEMA:
            raise F4ContractError("unknown F4 schema")
        if self.status not in (WAIT, ELIGIBLE):
            raise F4ContractError("invalid F4 status")
        if (self.evaluation_status != "NOT_EVALUATED"
            or self.strategy_approval_status != "NOT_APPROVED_FOR_TRADING"
            or self.factory_consumer_status != "NOT_CONNECTED"
            or self.holdout_accessed is not False
            or self.trading_authority != "NONE"):
            raise F4ContractError("forbidden research-to-trading promotion")
        if self.status == ELIGIBLE:
            for field in ("ledger_checkpoint_sha256", "membership_verification_sha256"):
                _sha(getattr(self, field), field)
            F4RetrospectiveEvidence(**self.source_evidence).validate_admitted()
        if self.intake_digest != _digest(self._payload()):
            raise F4ContractError("F4 intake digest mismatch")

    def _payload(self):
        return {name:getattr(self,name) for name in (
            "schema_version", "status", "reason", "candidate_id",
            "package_digest","nomination_digest","strategy_digest",
            "ledger_checkpoint_sha256","membership_verification_sha256",
            "ledger_attempt_id","source_evidence","evaluation_status",
            "strategy_approval_status","factory_consumer_status",
            "holdout_accessed","trading_authority"
        )}

    def to_dict(self):
        return {**self._payload(), "intake_digest":self.intake_digest}


def prepare_f4_intake(*, package, evidence, ledger_checkpoint_path,
                      ledger_checkpoint_sha256, ledger_attempt_id,
                      ledger_reference, cohort: F4RetrospectiveEvidence,
                      source_independently_authenticated=False,
                      research_policy_independently_approved=False):
    """Construct candidate history envelope; never self-certify source/policy.

    Flags indicate external verifications to be attested *again* by Factory.
    The Discoverer cannot issue a final Factory consumer ACK or Lab result.
    """
    if package.nomination_evidence_digest != evidence.nomination_digest:
        raise F4ContractError("package/nomination mismatch")
    if package.candidate_id == "" or package.strategy_definition_digest == ZERO:
        raise F4ContractError("invalid candidate identity")
    if package.evaluation_status != "NOT_EVALUATED" or package.factory_routing != "NOT_CONNECTED" or package.holdout_status != "SEALED_UNOPENED":
        raise F4ContractError("candidate safety status mismatch")
    if evidence.evidence_class == "TEST_ONLY_SYNTHETIC":
        raise F4ContractError("synthetic evidence cannot enter F4 historical intake")
    if evidence.evidence_class != "RETROSPECTIVE_NON_PIT_VERIFIED":
        raise F4ContractError("unverified nomination quarantined")
    if (evidence.source_dataset_id != cohort.source_dataset_id
        or evidence.source_manifest_sha256 != cohort.source_manifest_sha256
        or evidence.symbol != cohort.symbol or evidence.timeframe != cohort.timeframe
        or evidence.cutoff_ms != cohort.cutoff_ms
        or evidence.source_availability != "CONFIRMED_FINAL"):
        raise F4ContractError("source/cutoff/nomination binding mismatch")
    if not isinstance(cohort,F4RetrospectiveEvidence):
        raise F4ContractError("cohort evidence type invalid")
    # This is merely a guarded proposal. If the owner/custodian attestation is
    # missing, emit WAIT with no verified membership or source admission claim.
    reason = "independent source and retrospective research policy required"
    status = WAIT
    checkpoint_sha = None
    membership_sha = None
    if source_independently_authenticated is True and research_policy_independently_approved is True:
        cohort.validate_admitted()
        durable = DurableDiscovererCheckpoint(ledger_checkpoint_path)
        snapshot = durable.read_latest_ledger()
        if snapshot["checkpoint_sha"] != ledger_checkpoint_sha256:
            raise F4ContractError("durable ledger checkpoint pin mismatch")
        membership = durable.verify_membership(
            package=package, ledger_attempt_id=ledger_attempt_id,
            ledger_head_digest=package.attempt_ledger_head,
            ledger_reference=ledger_reference)
        checkpoint_sha = snapshot["checkpoint_sha"]
        membership_sha = membership.verification_digest
        status = ELIGIBLE
        reason = "candidate provenance verified locally; Factory must reattest custody/policy"
    fields = dict(schema_version=SCHEMA,status=status,reason=reason,
                  candidate_id=package.candidate_id,
                  package_digest=package.package_digest,
                  nomination_digest=evidence.nomination_digest,
                  strategy_digest=package.strategy_definition_digest,
                  ledger_checkpoint_sha256=checkpoint_sha,
                  membership_verification_sha256=membership_sha,
                  ledger_attempt_id=ledger_attempt_id,
                  source_evidence=cohort.to_dict(),
                  evaluation_status="NOT_EVALUATED",
                  strategy_approval_status="NOT_APPROVED_FOR_TRADING",
                  factory_consumer_status="NOT_CONNECTED",
                  holdout_accessed=False,trading_authority="NONE")
    return F4ResearchIntake(**fields,intake_digest=_digest(fields))


def verify_f4_intake(*, intake: F4ResearchIntake, package, evidence, cohort,
                     durable_ledger_path=None, independently_confirm_source=False,
                     independently_confirm_policy=False):
    """Receiver-side verification of F4 envelope. Never trust sealed flags alone."""
    if not isinstance(intake, F4ResearchIntake) or not isinstance(cohort, F4RetrospectiveEvidence):
        raise F4ContractError("F4 verifier input type")
    F4ResearchIntake(**intake.to_dict())
    if (intake.package_digest!=package.package_digest or
        intake.candidate_id!=package.candidate_id or
        intake.nomination_digest!=evidence.nomination_digest or
        intake.strategy_digest!=package.strategy_definition_digest or
        intake.source_evidence!=cohort.to_dict()):
        raise F4ContractError("F4 cross-object parent drift")
    if intake.status != ELIGIBLE:
        raise F4ContractError("historical F4 intake is blocked")
    if independently_confirm_source is not True or independently_confirm_policy is not True:
        raise F4ContractError("independent source and research policy approval unavailable")
    cohort.validate_admitted()
    if durable_ledger_path is None:
        raise F4ContractError("independent durable checkpoint path required")
    durable = DurableDiscovererCheckpoint(durable_ledger_path)
    snapshot = durable.read_latest_ledger()
    if snapshot["checkpoint_sha"] != intake.ledger_checkpoint_sha256:
        raise F4ContractError("checkpoint custody pin drift")
    membership = durable.verify_membership(
        package=package,ledger_attempt_id=intake.ledger_attempt_id,
        ledger_head_digest=package.attempt_ledger_head,
        ledger_reference="discoverer-f4")
    if membership.verification_digest != intake.membership_verification_sha256:
        raise F4ContractError("independent membership drift")
    return True
