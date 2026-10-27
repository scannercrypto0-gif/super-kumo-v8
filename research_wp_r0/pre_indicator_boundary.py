"""Offline pre-indicator boundary for externally scheduled Factory opportunities.

A blocked/unknown Core revision is retained as a scheduled slot, NEVER
converted to an indicator vector, decision or synthetic execution request.
This is a narrow negative-path integration, not a live PIT/PAPER pipeline.
"""
from .core_proof_bridge import review_core_envelope


def block_unproven_opportunities(*, scheduled, envelope, pinned_digest, cutoff_ms):
    if type(scheduled) is not list or not scheduled:
        raise ValueError("explicit nonempty externally scheduled universe required")
    if len(scheduled) > 256:
        raise ValueError("bounded supplied opportunity universe required")
    receipts = review_core_envelope(envelope, pinned_digest=pinned_digest, cutoff_ms=cutoff_ms)
    by_version = {receipt.version_id: receipt for receipt in receipts if receipt.version_id}
    if len(by_version) != sum(receipt.version_id is not None for receipt in receipts):
        raise ValueError("ambiguous repeated receipt")
    slots, seen = [], set()
    for item in scheduled:
        if type(item) is not dict or set(item) != {"event_id", "version_id"}:
            raise ValueError("explicit scheduled event/version identity required")
        event_id, version_id = item["event_id"], item["version_id"]
        if type(event_id) is not str or not event_id or event_id in seen:
            raise ValueError("invalid or duplicate scheduled event")
        seen.add(event_id)
        receipt = by_version.get(version_id)
        # Even a future empirical review eligibility is NOT a real-PIT gate pass.
        slots.append(dict(event_id=event_id, version_id=version_id,
                          status="BLOCKED_BEFORE_INDICATOR",
                          reason=receipt.reason if receipt else "NO_CORE_REVISION_RECEIPT",
                          indicator_features=None, execution_request=None))
    return dict(scope="OFFLINE_UNATTESTED_NEGATIVE_ONLY",
                scheduled_total=len(scheduled),
                blocked_total=len(slots), slots=slots)
