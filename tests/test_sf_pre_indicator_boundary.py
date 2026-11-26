"""Cross-boundary negative test: supplied denominator survives admission refusal."""
from hashlib import sha256
import json

from research_wp_r0.pre_indicator_boundary import block_unproven_opportunities

def sha(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode()).hexdigest()

def test_shared_core_shaped_slots_never_enter_indicator():
    one=dict(logical_bar_id="BTCUSDT:1m:0", version_number=1,
             payload_digest="a"*64, bar_open_ms=0, bar_close_ms=59999,
             first_local_seen_ms=60001, source_id="synthetic-ws",
             supersedes_version_id=None, provider_available_ms=None,
             provider_evidence_ref=None, clock_evidence_ref="synthetic-clock",
             local_commit_evidence_ref="synthetic-local-receipt",
             ingest_committed_ms=60002)
    first="obs-v1:"+sha(one)
    late=dict(one,version_number=2,payload_digest="b"*64,
              first_local_seen_ms=90000, ingest_committed_ms=90001,
              supersedes_version_id=first)
    second="obs-v1:"+sha(late)
    missing=dict(one,logical_bar_id="ETHUSDT:1m:0",payload_digest="c"*64,
                 first_local_seen_ms=None,ingest_committed_ms=None,
                 local_commit_evidence_ref=None,clock_evidence_ref=None)
    third="obs-v1:"+sha(missing)
    body=dict(schema="core-data-proof-envelope-v1",consumer="factory",epoch=1,
              provenance_scope="LOCAL_ONLY_UNATTESTED",
              versions=[dict(version_id="obs-v1:"+sha(v),record=v) for v in (one,late,missing)],
              gap_states={"BTCUSDT:1m:0":"CONFIRMED",
                          "ETHUSDT:1m:0":"IN_DOUBT","gap:unknown":"IN_DOUBT"})
    envelope=dict(body,manifest_sha256=sha(body))
    events=[dict(event_id=k,version_id=v) for k,v in
            (("original",first),("late_corrected",second),("missing",third),
             ("unprovided","not-in-core"))]
    report=block_unproven_opportunities(scheduled=events,envelope=envelope,
                                         pinned_digest=envelope["manifest_sha256"],
                                         cutoff_ms=70000)
    assert report["scheduled_total"]==4
    assert report["blocked_total"]==4
    assert [s["reason"] for s in report["slots"]]==[
        "PROVIDER_AS_OF_UNVERIFIED","NOT_KNOWN_AT_CUTOFF",
        "SPARSE_OR_UNCONFIRMED","NO_CORE_REVISION_RECEIPT"]
    assert all(s["indicator_features"] is None and s["execution_request"] is None
               for s in report["slots"])
