"""Package E: independently verify Discoverer ledger membership at the sealed checkpoint.

This does not trust caller-supplied attempts or hashes. The verifier replays the
entire immutable prefix and confirms the exact package's candidate/strategy/
family/search-plan/nomination association at its sealed PENDING checkpoint.
The consumer must obtain the independently stored ledger snapshot from custody;
a caller-created snapshot or self-declared 'proof' is not authoritative.
"""
from __future__ import annotations

from dataclasses import dataclass

from tools.strategy_discoverer_offline.contracts import _digest
from tools.strategy_discoverer_offline.ledger import DiscovererLedger


@dataclass(frozen=True)
class VerifiedLedgerMembershipV1:
    ledger_reference: str
    checkpoint_head: str
    ledger_root: str
    entry_index: int
    entry_digest: str
    attempt_id: str
    candidate_id: str
    package_digest: str
    verification_digest: str

    @classmethod
    def build(cls, *, ledger_reference, checkpoint_head, ledger_root,
              entry_index, entry_digest, attempt_id, candidate_id, package_digest):
        fields = dict(ledger_reference=ledger_reference, checkpoint_head=checkpoint_head,
                      ledger_root=ledger_root, entry_index=entry_index,
                      entry_digest=entry_digest, attempt_id=attempt_id,
                      candidate_id=candidate_id, package_digest=package_digest)
        return cls(**fields, verification_digest=_digest(fields))


def verify_ledger_membership(*, entries_data, package, ledger_attempt_id,
                             ledger_head_digest, ledger_reference):
    """Verify all prefix hashes and index continuity, then exact candidate membership.

    The package is sealed while its ledger attempt is PENDING; later COMPLETE
    transitions are allowed *after* the sealed checkpoint, not retroactively.
    Raises ValueError on every failure, never silently upgrades NOT_VERIFIED.
    """
    if not ledger_reference or not isinstance(ledger_reference, str):
        raise ValueError("ledger_reference required")
    if not entries_data or not isinstance(entries_data, (list, tuple)):
        raise ValueError("independent ledger snapshot required")
    # from_dict_list validates digest, predecessor, index and *every* historical
    # entry; verify_chain repeats the full integrity check on the rebuilt ledger.
    try:
        ledger = DiscovererLedger.from_dict_list(list(entries_data),
                                                 max_entries=max(4096, len(entries_data)))
    except (TypeError, ValueError, KeyError) as exc:
        raise ValueError("ledger chain invalid") from exc
    if not ledger.verify_chain():
        raise ValueError("ledger chain invalid")
    entries = ledger.entries()
    checkpoints = [i for i, item in enumerate(entries)
                   if item.entry_digest == ledger_head_digest]
    if len(checkpoints) != 1:
        raise ValueError("sealed ledger checkpoint absent")
    checkpoint_index = checkpoints[0]
    if package.attempt_ledger_head != ledger_head_digest:
        raise ValueError("package checkpoint mismatch")
    # A matching attempt must exist *by* the package checkpoint.
    matches = [(i, entry) for i, entry in enumerate(entries[:checkpoint_index + 1])
               if entry.attempt_id == ledger_attempt_id]
    if not matches:
        raise ValueError("ledger attempt not a member at sealed checkpoint")
    i, entry = matches[-1]
    if entry.state != "PENDING":
        raise ValueError("sealed ledger attempt is not PENDING")
    fields = {
        "candidate_id": (entry.candidate_id, package.candidate_id),
        "family_id": (entry.family_id, package.family_id),
        "strategy_digest": (entry.strategy_digest, package.strategy_definition_digest),
        "search_plan_digest": (entry.search_plan_digest, package.search_plan_digest),
        "nomination_digest": (entry.nomination_digest, package.nomination_evidence_digest),
    }
    bad = [k for k, (actual, expected) in fields.items() if actual != expected]
    if bad:
        raise ValueError("ledger candidate binding mismatch: " + ",".join(bad))
    if not package.package_digest or not package.candidate_id:
        raise ValueError("package identity missing")
    return VerifiedLedgerMembershipV1.build(
        ledger_reference=ledger_reference,
        checkpoint_head=ledger_head_digest,
        ledger_root=ledger.head_digest(),
        entry_index=i,
        entry_digest=entry.entry_digest,
        attempt_id=ledger_attempt_id,
        candidate_id=package.candidate_id,
        package_digest=package.package_digest,
    )
