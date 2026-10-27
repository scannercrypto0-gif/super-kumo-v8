"""Only Core #137-shaped deterministic offline envelope fixtures, no Core imports."""
from hashlib import sha256
import json
from research_wp_r0.core_proof_bridge import review_core_envelope

def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode()).hexdigest()

def fixture(*, first=1201, gap="CONFIRMED"):
    record = dict(logical_bar_id="BTC:1m:0", version_number=1, payload_digest="a"*64,
                  bar_open_ms=0, bar_close_ms=1200, first_local_seen_ms=first,
                  source_id="ws", supersedes_version_id=None,
                  provider_available_ms=None, provider_evidence_ref=None,
                  clock_evidence_ref="local-clock", local_commit_evidence_ref="receipt")
    body = dict(schema="core-data-proof-envelope-v1", consumer="factory",
                epoch=1, provenance_scope="LOCAL_ONLY_UNATTESTED",
                versions=[dict(version_id="obs-v1:"+digest(record), record=record)],
                gap_states={"BTC:1m:0": gap})
    return dict(body, manifest_sha256=digest(body))

def test_local_only_cannot_claim_empirical():
    obj=fixture()
    result=review_core_envelope(obj, pinned_digest=obj["manifest_sha256"], cutoff_ms=1202)[0]
    assert result.status == "UNKNOWN_PENDING_EVIDENCE"
    assert not result.empirical_eligible and not result.real_pit_accepted

def test_late_arriving_original_is_blocked():
    obj=fixture(first=1205)
    result=review_core_envelope(obj, pinned_digest=obj["manifest_sha256"], cutoff_ms=1202)[0]
    assert result.status == "UNKNOWN_PENDING_EVIDENCE" or result.status == "REJECT_FOR_EMPIRICAL"
    assert not result.real_pit_accepted

def test_invalid_pin_and_changed_version_reject():
    obj=fixture()
    obj["versions"][0]["record"]["payload_digest"]="b"*64
    assert review_core_envelope(obj, pinned_digest=obj["manifest_sha256"], cutoff_ms=1202)[0].status == "REJECT_FOR_EMPIRICAL"

def test_sparse_unknown_preserved():
    obj=fixture(gap="IN_DOUBT")
    result=review_core_envelope(obj, pinned_digest=obj["manifest_sha256"], cutoff_ms=1202)[0]
    assert result.reason == "SPARSE_OR_UNCONFIRMED"

def test_stale_epoch_refused():
    obj=fixture()
    assert review_core_envelope(obj, pinned_digest=obj["manifest_sha256"], cutoff_ms=1202, minimum_epoch=2)[0].status == "REJECT_FOR_EMPIRICAL"

def test_invalid_sparse_state_rejected():
    obj=fixture(gap="DELIVERED")
    body={k:v for k,v in obj.items() if k!="manifest_sha256"}
    obj["manifest_sha256"]=digest(body)
    assert review_core_envelope(obj, pinned_digest=obj["manifest_sha256"], cutoff_ms=1202)[0].reason=="INVALID_CORE_GAP_STATE"

def test_duplicate_revision_rejected():
    obj=fixture()
    obj["versions"].append(obj["versions"][0])
    body={k:v for k,v in obj.items() if k!="manifest_sha256"}
    obj["manifest_sha256"]=digest(body)
    assert review_core_envelope(obj, pinned_digest=obj["manifest_sha256"], cutoff_ms=1202)[0].reason=="DUPLICATE_CORE_VERSION"

def test_core_shared_fixture_shape_preserves_late_and_missing():
    original=dict(logical_bar_id="BTCUSDT:1m:0", version_number=1, payload_digest="a"*64,
                  bar_open_ms=0, bar_close_ms=59999, first_local_seen_ms=60001,
                  source_id="synthetic-ws", supersedes_version_id=None,
                  provider_available_ms=None, provider_evidence_ref=None,
                  clock_evidence_ref="synthetic-clock",
                  local_commit_evidence_ref="synthetic-local-receipt",
                  ingest_committed_ms=60002)
    original_id="obs-v1:"+digest(original)
    revised=dict(original, version_number=2, payload_digest="b"*64,
                 first_local_seen_ms=90000, ingest_committed_ms=90001,
                 supersedes_version_id=original_id)
    missing=dict(original, logical_bar_id="ETHUSDT:1m:0", payload_digest="c"*64,
                 first_local_seen_ms=None, ingest_committed_ms=None,
                 clock_evidence_ref=None, local_commit_evidence_ref=None)
    body=dict(schema="core-data-proof-envelope-v1", consumer="factory", epoch=1,
              provenance_scope="LOCAL_ONLY_UNATTESTED",
              versions=[dict(version_id="obs-v1:"+digest(v),record=v) for v in
                        [original,revised,missing]],
              gap_states={"gap:unknown":"IN_DOUBT"})
    packet=dict(body,manifest_sha256=digest(body))
    outcomes=review_core_envelope(packet,pinned_digest=packet["manifest_sha256"],
                                  cutoff_ms=70000)
    assert [o.status for o in outcomes]==[
        "UNKNOWN_PENDING_EVIDENCE","REJECT_FOR_EMPIRICAL",
        "UNKNOWN_PENDING_EVIDENCE"]
    assert outcomes[1].reason=="NOT_KNOWN_AT_CUTOFF"
    assert not any(o.real_pit_accepted or o.empirical_eligible for o in outcomes)
