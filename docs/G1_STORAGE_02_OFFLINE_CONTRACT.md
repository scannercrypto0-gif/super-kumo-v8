# Offline archive query V1 — #71 / #77 boundary

`aql.archive.offline.snapshot` consumes only a **quiescent sealed backup** made by
`create_backup`, never a live operational catalog. Required caller input: root,
previously retained `inventory_hash`, explicit symbol/interval and [start,end)
open-time range. The caller must obtain the commitment from its approved trust
channel; the function does not protect that channel.

It verifies the complete backup before selection and again before returning
canonical JSON bytes, including unselected files/source backlog. Default maximum
4096 selected rows; overflow raises rather than returning incomplete success.
Rows sort by open time, stable key, sequence, retaining the full versioned market
envelope and missing temporal fields. Bounds/timeouts are cooperative; a hostile
privileged writer can race local path checks. Use a separately protected,
quiescent copy; no claim of snapshot isolation against such a writer.

Output `aql.offline-archive-query.v1` binds inventory hash, selection, watermark,
record count, exact-envelope content digest and unarchived record count. Empty
selection is permitted and means zero observed matching archived records, not
complete market coverage. Hash identity includes recorded source UUID/provenance;
it is not a provider-independent economic-price identity. Query output does not
contain a new HistoricalLibrary dataset version or manifest.

`retrospective_only=true`, `pit_eligibility=NOT_ATTESTED`,
`independent_custody_verified=false`, `research_evaluation=NOT_PERFORMED` are
mandatory. Selection on bar open does **not** assert availability at that time.
Existing archive availability lower bounds must never become confirmed receipt
or ingestion evidence for an earlier research decision.

```python
from aql.archive.offline import snapshot
raw = snapshot(approved_sealed_copy, expected_digest=retained_inventory_hash,
               symbol="BTCUSDT", interval="1m", start_ms=0, end_ms=180000)
```

#77 integration is an explicit future research-side decision: HistoricalLibrary
and CustodyAccessor require their own immutable bars/manifests, integrity chain,
provenance/availability policy and registration checks. No runtime connection,
schema reinterpretation or implicit registration is introduced here; no unmerged
#46/#105 code is imported. Real retrospective CSV trials demonstrate data
importability, not confirmed historical PIT or empirical evaluation acceptance.
