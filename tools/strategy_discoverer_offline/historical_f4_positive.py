"""F4 optional engineering-positive authorization. No self-issued source/policy/ledger authority.

Independent trust roots and current time MUST be provisioned OUTSIDE candidate inputs.
CI ephemeral keys demonstrate code behavior, never real owner approval.
"""
from dataclasses import dataclass
from tools.strategy_discoverer_offline.contracts import _canonical, _digest
from tools.strategy_discoverer_offline.durable_checkpoint_e import DurableDiscovererCheckpoint

READY_SCHEMA = "aql.discoverer.f4.independent-research-ready.v2"
WITNESS_SCHEMA = "aql.discoverer.f4.external-role-witness.v1"
ROLES = ("SOURCE_CUSTODIAN", "RESEARCH_POLICY_APPROVER", "LEDGER_CUSTODIAN")
READY = "READY_FOR_FACTORY_RESEARCH_INTAKE"
ZERO = "0" * 64


class F4AuthorityError(ValueError):
    pass


def _sha(value, name):
    if not isinstance(value, str) or len(value) != 64 or value == ZERO or any(c not in "0123456789abcdef" for c in value):
        raise F4AuthorityError(name + ": nonzero sha256 required")
    return value


def _cross_bind(package, nomination, cohort):
    from tools.strategy_discoverer_offline.contracts import DiscoveryCandidatePackageV1, NominationEvidenceV1
    DiscoveryCandidatePackageV1.from_dict(package.to_dict())
    NominationEvidenceV1.from_dict(nomination.to_dict())
    markets = {"BINANCE_SPOT": "BINANCE:SPOT:USDT", "BINANCE:SPOT:USDT": "BINANCE:SPOT:USDT"}
    if (package.nomination_evidence_digest != nomination.nomination_digest
        or package.source_manifest_sha256 != cohort.source_manifest_sha256
        or nomination.source_manifest_sha256 != cohort.source_manifest_sha256
        or nomination.source_dataset_id != cohort.source_dataset_id
        or nomination.symbol != cohort.symbol or nomination.timeframe != cohort.timeframe
        or markets.get(nomination.market) != cohort.market
        or nomination.cutoff_ms != cohort.cutoff_ms
        or nomination.source_availability != "CONFIRMED_FINAL"
        or nomination.evidence_class != "RETROSPECTIVE_NON_PIT_VERIFIED"
        or package.evaluation_status != "NOT_EVALUATED"
        or package.factory_routing != "NOT_CONNECTED"
        or package.holdout_status != "SEALED_UNOPENED"):
        raise F4AuthorityError("immutable candidate/nomination/source mismatch")
    _sha(nomination.independent_verifier_receipt_sha256, "nomination verifier")
    cohort.validate_admitted()


def _member(db_path, checkpoint_sha, package, attempt_id, ledger_reference):
    _sha(checkpoint_sha, "checkpoint")
    if not isinstance(ledger_reference, str) or not ledger_reference.strip() or not db_path:
        raise F4AuthorityError("independently pinned ledger path/reference required")
    durable = DurableDiscovererCheckpoint(db_path)
    snap = durable.read_latest_ledger()
    if snap["checkpoint_sha"] != checkpoint_sha:
        raise F4AuthorityError("ledger checkpoint mismatch")
    proof = durable.verify_membership(
        package=package, ledger_attempt_id=attempt_id,
        ledger_head_digest=package.attempt_ledger_head, ledger_reference=ledger_reference)
    durable.attempt_events()
    return proof


def witness_subjects(*, package, nomination, cohort, report_sha, checkpoint_sha,
                     membership_sha, ledger_reference, attempt_id):
    _sha(report_sha, "Core F2 actual report")
    _sha(checkpoint_sha, "checkpoint")
    _sha(membership_sha, "membership")
    return {
        "SOURCE_CUSTODIAN": _digest(dict(
            f2_report_sha256=report_sha,
            dataset=cohort.source_dataset_id, manifest=cohort.source_manifest_sha256,
            archive=cohort.original_archive_sha256,
            publisher_checksum=cohort.publisher_checksum_sha256,
            source_verifier=cohort.independent_source_verifier_sha256,
            native245=cohort.core_245_query_sha256, local253=cohort.core_253_query_sha256,
            symbol=cohort.symbol, timeframe=cohort.timeframe, market=cohort.market,
            first=cohort.first_bar_open_ms, last=cohort.last_bar_open_ms,
            cutoff=cohort.cutoff_ms, pit="RETROSPECTIVE_NON_PIT")),
        "RESEARCH_POLICY_APPROVER": _digest(dict(
            policy_approval=cohort.independent_research_policy_approval_sha256,
            source_f2=report_sha, manifest=cohort.source_manifest_sha256,
            strategy=package.strategy_definition_digest,
            nomination=nomination.nomination_digest, cutoff=cohort.cutoff_ms,
            authority="RESEARCH_ONLY", pit="RETROSPECTIVE_NON_PIT")),
        "LEDGER_CUSTODIAN": _digest(dict(
            ledger_reference=ledger_reference, checkpoint=checkpoint_sha,
            membership=membership_sha, attempt_id=attempt_id,
            package=package.package_digest, nomination=nomination.nomination_digest)),
    }


def verify_signed_witnesses(witnesses, external_roots, trusted_now_ms, subjects):
    if (not isinstance(witnesses, dict) or set(witnesses) != set(ROLES)
        or not isinstance(external_roots, dict) or set(external_roots) != set(ROLES)
        or type(trusted_now_ms) is not int or trusted_now_ms <= 0):
        raise F4AuthorityError("independent witness, trust roots or clock missing")
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
    except ImportError as exc:
        raise F4AuthorityError("Ed25519 verifier unavailable") from exc
    seen = set()
    for role in ROLES:
        witness, root = witnesses[role], external_roots[role]
        if (not isinstance(witness, dict)
            or set(witness) != {"schema_version","role","key_id","approver_id","subject_sha256",
                                "not_before_ms","expires_at_ms","signature_hex"}
            or not isinstance(root, dict)
            or set(root) != {"key_id","approver_id","public_key_hex"}):
            raise F4AuthorityError("signed witness/independent registry schema mismatch")
        if (witness["schema_version"] != WITNESS_SCHEMA or witness["role"] != role
            or witness["key_id"] != root["key_id"] or witness["approver_id"] != root["approver_id"]
            or not witness["key_id"] or not witness["approver_id"]
            or witness["subject_sha256"] != subjects[role]):
            raise F4AuthorityError("signed witness role or subject mismatch")
        if root["public_key_hex"] in seen:
            raise F4AuthorityError("reused key across independent issuer roles")
        seen.add(root["public_key_hex"])
        if (type(witness["not_before_ms"]) is not int or type(witness["expires_at_ms"]) is not int
            or not witness["not_before_ms"] <= trusted_now_ms < witness["expires_at_ms"]):
            raise F4AuthorityError("signature time validity failed")
        try:
            signature = bytes.fromhex(witness["signature_hex"])
            key = bytes.fromhex(root["public_key_hex"])
            if len(signature) != 64 or len(key) != 32:
                raise ValueError("Ed25519 format")
            Ed25519PublicKey.from_public_bytes(key).verify(
                signature, _canonical({k:v for k,v in witness.items() if k != "signature_hex"}))
        except (InvalidSignature, TypeError, ValueError) as exc:
            raise F4AuthorityError("untrusted or invalid role signature") from exc
    return _digest(witnesses)


@dataclass(frozen=True)
class F4ReadyIntakeV2:
    schema_version: str
    status: str
    waiting_intake: dict
    original_ledger_reference: str
    core_f2_report_sha256: str
    ledger_checkpoint_sha256: str
    membership_verification_sha256: str
    witnesses: dict
    witnesses_digest: str
    ready_digest: str

    def _payload(self):
        return {k:getattr(self,k) for k in (
            "schema_version","status","waiting_intake","original_ledger_reference",
            "core_f2_report_sha256","ledger_checkpoint_sha256","membership_verification_sha256",
            "witnesses","witnesses_digest")}

    def __post_init__(self):
        if self.schema_version != READY_SCHEMA or self.status != READY or not self.original_ledger_reference:
            raise F4AuthorityError("invalid v2 ready envelope")
        for k in ("core_f2_report_sha256","ledger_checkpoint_sha256",
                  "membership_verification_sha256","witnesses_digest"):
            _sha(getattr(self,k),k)
        if self.witnesses_digest != _digest(self.witnesses) or self.ready_digest != _digest(self._payload()):
            raise F4AuthorityError("ready envelope digest mismatch")

    def to_dict(self):
        return {**self._payload(), "ready_digest":self.ready_digest}


def prepare_signed_f4(*, waiting, package, nomination, cohort, db_path,
                      checkpoint_sha, attempt_id, ledger_reference, report_sha,
                      witnesses, external_roots, trusted_now_ms):
    _cross_bind(package, nomination, cohort)
    proof = _member(db_path, checkpoint_sha, package, attempt_id, ledger_reference)
    scopes = witness_subjects(package=package, nomination=nomination, cohort=cohort,
        report_sha=report_sha, checkpoint_sha=checkpoint_sha,
        membership_sha=proof.verification_digest, ledger_reference=ledger_reference,
        attempt_id=attempt_id)
    witness_sha = verify_signed_witnesses(witnesses, external_roots, trusted_now_ms, scopes)
    fields = dict(schema_version=READY_SCHEMA, status=READY, waiting_intake=waiting.to_dict(),
        original_ledger_reference=ledger_reference, core_f2_report_sha256=report_sha,
        ledger_checkpoint_sha256=checkpoint_sha,
        membership_verification_sha256=proof.verification_digest,
        witnesses=witnesses, witnesses_digest=witness_sha)
    return F4ReadyIntakeV2(**fields, ready_digest=_digest(fields))


def verify_signed_f4(*, intake, package, nomination, cohort, db_path,
                     external_roots, trusted_now_ms, pinned_f2_report_sha256):
    F4ReadyIntakeV2(**intake.to_dict())
    from tools.strategy_discoverer_offline.historical_f4_intake import F4ResearchIntake, WAIT
    waiting = F4ResearchIntake(**intake.waiting_intake)
    if (waiting.status != WAIT or waiting.package_digest != package.package_digest
        or waiting.candidate_id != package.candidate_id
        or waiting.nomination_digest != nomination.nomination_digest
        or waiting.strategy_digest != package.strategy_definition_digest
        or waiting.source_evidence != cohort.to_dict()
        or not waiting.ledger_attempt_id):
        raise F4AuthorityError("original waiting envelope drift")
    if intake.core_f2_report_sha256 != pinned_f2_report_sha256:
        raise F4AuthorityError("independent F2 pin drift")
    _cross_bind(package, nomination, cohort)
    proof = _member(db_path, intake.ledger_checkpoint_sha256, package,
        waiting.ledger_attempt_id, intake.original_ledger_reference)
    if proof.verification_digest != intake.membership_verification_sha256:
        raise F4AuthorityError("original ledger_reference/membership mismatch")
    scopes = witness_subjects(package=package, nomination=nomination, cohort=cohort,
        report_sha=intake.core_f2_report_sha256, checkpoint_sha=intake.ledger_checkpoint_sha256,
        membership_sha=proof.verification_digest, ledger_reference=intake.original_ledger_reference,
        attempt_id=waiting.ledger_attempt_id)
    if verify_signed_witnesses(intake.witnesses, external_roots, trusted_now_ms, scopes) != intake.witnesses_digest:
        raise F4AuthorityError("external witness digest drift")
    return True
