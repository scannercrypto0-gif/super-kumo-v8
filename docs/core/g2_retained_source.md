# G2 retained source — offline adapter only

Owner order: PR #118 comment 6398564073 (supersedes overlapping follow-ups).
Dependency: PR #118 at 3b1d02f64f1986eebfa782d368f1f6cd20966147,
still unmerged. Review/merge #118 first; then re-evaluate this isolated adapter
diff against main. No automatic merge or retargeting is authorized.

## Reuse and missing boundary

G1 DurableJournal already persists MarketBar in SQLite WAL/FULL and
JournalConsumer acknowledges storage success. BackgroundLane already provides
bounded scheduling. Neither is a G2 PositionEvent source: no bar-to-position or
Factory strategy mapping is invented. ObservationWorker has bounded volatile
admission, composite diagnostics and fail-stop errors. DurablePositionJournal
validates JSONL chains and composite duplicate identity and fsyncs appends.
This adapter adds only retained PositionEvent input and verified per-event ACKs.
It does not import unmerged #93 hardening or change #115/#117.

## Format, bounds and receipt

RetainedObservationSource uses canonical UTF-8 JSONL envelopes with SHA-256
previous/digest chaining. Header fixes version=1, owner-supplied generation UUID,
absolute dedicated target path and max_events. Event records have contiguous
source_sequence (seq), immutable PositionEvent and canonical payload_hash.
ACK records have the next contiguous seq and matching payload hash. Generation
plus sequence identifies a source record; (position_id,event_id) identifies the
target event. Identical retain retries return the original sequence; conflicting
payloads fail closed. There is no automatic conversion from G1 bar identities.

Admission writes/flushes/fsyncs the source before successful return. A prior
ambiguous sync is revalidated/resynced before successful duplicate retain or offer.
step() replays at most one next sequence, offering with worker.submit(). Accepted
RAM work, health, queue removal and aggregate counters cannot ACK. Before ACK it
independently reopens/verifies the target chain, matches the exact immutable event
and fsyncs the target under its cooperating writer lease. Only then does it
append/flush/fsync an ACK. On reopen, ACK prefix is rechecked against target and
resynced; an absent/conflicting target or skipped cursor fails closed.

Default cap=32, configurable integer 1..128 total events INCLUDING ACKed events.
Event payload <=4096 bytes, source line <=8192 bytes, source <=1+2*cap records,
target <=cap*8192 bytes and <=cap events. Memory/scan work is finite under these
limits; target verification still scans history. No throughput/SLO claim.
There is no compaction, eviction or automatic generation rotation: full admission
raises SourceFullError and has NOT accepted that input. The producer must keep it
elsewhere. Retained events survive worker/lane rejection and remain retryable.
Unacked input is never automatically deleted. This is a small offline acceptance
fixture, not a long-running retention/storage architecture.

## Independent lane and usage boundary

Create/retain/status/step perform IO and MUST run outside G1 callback. schedule()
only submits one bounded job to an existing independent BackgroundLane; false
means scheduling backpressure and does not change retained data. The owner of
that lane must poll/schedule further steps off the core path, observe lane errors,
and stop on integrity failures. This module starts no thread, network, scheduler
or pipeline hook. Actual G1 callback has no dependency on adapter source/journal
locks; synthetic tests hold adapter IO while a real G1 durable commit completes.
That is cooperative isolation evidence, not host-wide CPU/disk independence.

## Crash-window acceptance

| Window | Outcome / recovery |
|---|---|
| Source fsync before offer | Event retained; reopen offers next unacked sequence |
| Worker dequeue before target fsync | Source remains unacked; replay after restart |
| Target fsync before source ACK | Verify existing exact target, fsync receipt, ACK; one physical event |
| Source ACK write interrupted | Valid full row is revalidated/resynced; torn row fails closed |
| Worker full, stopped or failed | Backpressure/blocked; source remains retained |
| Target fsync/receipt fails | No ACK; stop, preserve evidence, diagnose/retry |
| Source/journal corrupt, ambiguous identity or missing ACK prefix | No offer/ACK; no silent repair |
| Process dies holding source/journal lease | Fail closed on orphan; explicit fenced operator recovery required |

Tests use actual exited subprocesses for the first three windows. A source lease
may remain when process termination races offer completion: tests assert refusal,
verify the child exited, then explicitly unlink ONLY that disposable child's
temporary lease before replay. Runtime has no auto-unlock or repair. On real
storage, owner must fence all old writers, preserve evidence and inspect chain
before separately authorizing orphan recovery; tests do not authorize file deletion.

## Limits and future Core/Factory interface (not implemented)

Trusted local directories and cooperating writers are assumed. Hash chaining has
no separately trusted anchor and cannot prove absence of whole-file rollback or
suffix removal; coherent media rollback/replacement, hostile symlinks/path swaps,
power loss, directory-entry persistence and offsite custody are not solved.
File fsync is an OS-level boundary, not proven physical power-loss survival.
Reuses private journal lease/mutex helpers, so their lock contract is a dependency.
Receipt may wait on G2 IO; only the independent lane may call it. No sustained
capacity/resource isolation, production source contract or runtime wiring is proven.

Future coordinated Core/Factory bridge must preserve immutable event identity,
decision-time UTC timestamp, PIT context provenance/freshness/missing-data, durable
delivery, and distinct dev/OOS/forward results. Existing PositionEvent millisecond
provenance is reused, not represented as proof of external UTC clock accuracy or
PIT strategy evidence. Propose a separately reviewed producer/callback interface
before wiring real decisions; no strategy mapping, bridge or trading activation here.

Focused command (Python >=3.10, existing project dependencies):

```text
python -m pytest tests/test_g2_retained_source.py tests/test_g2_observation_worker.py tests/test_g2_position_journal.py -q
```

Dedicated Windows/Ubuntu workflow checks exact published head and retains JUnit.
No broad benchmark, G1/Factory rerun or production acceptance is requested.
