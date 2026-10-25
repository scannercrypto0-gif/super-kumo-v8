# G2 Core position journal — #92 / Draft #93

**Offline experimental scope only. No activation, production readiness or merge approval.**
This document supersedes earlier partial-proposal wording. Branch `core/g2-92-recovery-evidence`
started at `f3067fc497d1a762097310f2bfecf27e94648b58`; inspected main was
`20f28986e33b5079a3c8b8b866f2d8841e715271`. Exact final head/CI are in the PR report.

## Implemented boundary and compatible hardening

DurablePositionJournal retains the original JSONL schema (`previous`, `event`, `digest`),
canonical SHA-256 algorithm and PID-only sidecar format. No checkpoint/index format,
rotation, operator-unlock API or new fencing protocol has been introduced.

- Every append still verifies the **entire disk hash chain and lifecycle** under the
  existing cooperating-writer O_EXCL lease; duplicate IDs are idempotent and conflicts
  reject. Torn records fail closed, without truncation, repair or implicit recovery.
- Reuse that verified disposable replay as the candidate ledger. Removed the second
  O(n) rebuild from publicly mutable `self.ledger`; corrupting that public cache cannot
  manufacture history. Full verification remains O(n) per append / O(n^2) over growth.
- Reject duplicate JSON keys, symlink/reparse journal paths, nonregular files and
  observed file-identity replacements, including identical bytes at a different file.
- A writer checks acquired lock identity and its original PID bytes before normal
  release. It refuses to unlink a replaced/missing/modified lock. This is protection
  of the existing lease, **not** a new fenced lease or an orphan-cleanup mechanism.
- PositionEvent identity/source/kind and optional reason must be strings as annotated;
  mutable values previously admitted there could make a frozen event mutable/unsafe.
  Valid existing string-valued events, temporal rules, prices and hashes are unchanged.
- A short write or fsync/path failure never returns successful insertion. A process
  exit can leave durable bytes without an ACK; reopen/inspection and duplicate replay
  are needed, never assumed loss or success.

Only `position_journal.py`, compatible validation in `positions.py`, scoped journal
unit/diagnostic files, this document and its focused workflow are modified. There are
**no new production helper modules**, Factory/research/storage/pipeline edits or
network calls. PR83's paused worker is not launched or used as a dependency.

## Controlled backup/restore and operator recovery evidence

`tests/test_g2_operator_journal_recovery.py` supplies a **test-only** verified_copy
helper: retain an expected primary byte digest/count/tail/final state before copying;
acquire the existing source writer lease; revalidate; exclusively create/fsync the
copy; independently replay and compare its inventory. An isolated restore is another
exclusive verified copy. Existing destinations, absent/wrong expected inventory,
corrupt chains and even well-formed but different backups reject before publication.
No primary overwrite, automatic partial cleanup or retention deletion exists.

The source is quiescent/fenced within a controlled test, not arbitrary production.
Same-machine temporary copies are **not** offsite protection or independently trusted
custody. SHA-256 does not authenticate an attacker-controlled full replacement or
protect a rewritten journal plus rewritten external evidence. Expected digest/tail
in these drills is local evidence, not a newly approved persisted checkpoint format.

The orphan drill starts a known child, observes its deliberate process exit via
wait/communicate and exit status, records the actual interpreter PID from the child
and PID bytes in the lock. Windows venv launcher PID can differ: both are preserved.
Before intervention it saves journal/lock bytes and digests, executable, process
identity and exit evidence in an isolated audit directory and verifies the saved
journal. **Only test code**, after confirming death and absence of a restart
supervisor, explicitly removes its disposable orphan lock. A second real process
is then refused while the recovered writer holds the lease. Original evidence stays
unchanged. No production unlock command, PID-only death inference or automatic
orphan lock deletion is delivered.

Process-exit cases include interruption inside the actual append write (half record,
flush, os._exit), actual append fsync interruption, and preserved orphan lock/torn
bytes. These prove tested process-failure behavior, **not physical power-loss safety**,
directory fsync, hostile same-user pathname races, distributed/network filesystem
semantics or hardware write-cache behavior. Windows reparse rejection is also tested
through mocked reparse metadata without requiring symlink privileges.

## Local Windows evidence (2026-10-25)

Python3.14.3, Windows11 build22000, temporary filesystem **NTFS**, as observed through
GetVolumeInformationW. C: disk query reported TOSHIBA KBG30ZMV256G NVMe; underlying
virtualization/cache guarantees were not established. Get-Volume/fsutil telemetry
was unavailable/denied; no configuration/privilege changes were made.

Focused ordinary journal discovery: **35 collected /33PASS /2 intentional manual
benchmark skips**. Additional PositionLedger lifecycle suite: **12PASS**. The two
skips are not successful performance checks. Separate manual diagnostics actually
ran: larger replay **1PASS**, contention + blocked-backup isolation **2PASS**.
An initial orphan-test assertion incorrectly equated the Windows launcher PID with
interpreter PID; it was corrected to record both, then all focused tests passed.

### Measured before/after, no invented speedup

Same harness builds a valid batched fixture (setup NOT measured as per-event durable
throughput), independently replays it, times20 real append/fsync operations at its
tail, then three complete reopens. Percentiles use nearest rank: p99 with20samples
is merely that sample's maximum, not a population bound or SLA. Separate cProfile
and tracemalloc runs are excluded from latency samples. Before journal source SHA256
`228fd238a04d2e63adcc2831ca16ec8750f63e14d524f06401c3696f1352fea4`;
after `945835f9eeeb8d5529770056606307c80c083ad6e73d5c3ef1460e7893958307`.

| Seed events | Before append p50/p95/p99 ms | Hardened append p50/p95/p99 ms | Hardened reopen3samples ms |
|---|---|---|---|
|250|45.0955 /54.2714 /55.6404|57.8906 /65.3025 /66.4256|24.865 /13.830 /13.617|
|1000|64.7577 /70.9081 /96.5801|75.0244 /89.5184 /95.4265|47.336 /33.781 /30.530|
|5000|171.1889 /182.5860 /190.5470|162.0581 /179.0551 /183.2157|152.559 /145.565 /136.880|
|10000|273.3966 /319.9559 /341.3033|328.7635 /399.3563 /414.6365|357.541 /294.511 /288.000|

Largest journal3,053,135bytes after21appends. At10,020 existing events, profiled
PositionLedger.append calls drop **20,041 ->10,021**; full `_replay` remains1 per
append. Python reopen allocation peak was4,978,046bytes before /5,013,845after
(**not RSS, not append memory**). New validation plus uncontrolled machine/I/O
variance means measured latency did **not consistently improve**:10k p99 worsened.
Removing duplicate work is proven by call counts, not a claimed wall-clock win.
No useful production capacity/latency bound can be accepted from these samples.
A verified index/checkpoint or changed integrity contract is an owner decision,
not silently added here.

### Core Run isolation: bounded dependency PASS, resource acceptance NOT MET

Actual existing G1 DurableJournal.commit succeeded for3 synthetic final bars while
the position backup lease was deliberately blocked; the position writer correctly
refused that lease. No shared ACK or pipeline change was required. **Not** deployed
Core Run evidence: this observation journal is still not wired into that pipeline.

A separate same-interpreter/shared-NTFS contention diagnostic ran30 G1 commits
without load and30 with10k-event replay + byte-copy/fsync/verification background
work (4passes /12,186,684bytes). Baseline p50/p95/p99 **17.9847 /22.4551 /33.7651ms**;
loaded **79.6291 /123.3385 /127.3275ms**. All30commits survived replay, but resource
latency clearly increased: do **not** claim Core Run unaffected. GIL/CPU/disk/cache
contributions were not separately isolated. The module-wide observation writer
mutex also serializes independent observation journals; full synchronous replays
hold the calling thread. There is no hard host CPU/I/O budget in this scope.
Process/resource scheduling or pipeline integration needs separately authorized
cross-component scope; no edits to pipeline/storage/shared infrastructure here.

## Reproduction and focused CI

Routine:
```powershell
python -B -m unittest discover -s tests -p 'test_g2_*journal*.py' -v
python -B -m unittest discover -s tests -p test_g2_position_lifecycle.py -v
```

Explicit manual diagnostics only (sizes bounded at20000, default250/1000/5000/10000):
```powershell
$env:AQL_G2_BENCHMARK='1'
$env:AQL_G2_BENCHMARK_OUTPUT='g2-replay.json'
python -B -m unittest discover -s tests -p test_g2_journal_replay_benchmark.py -v
$env:AQL_G2_CONTENTION='1'
$env:AQL_G2_CONTENTION_OUTPUT='g2-contention.json'
python -B -m unittest discover -s tests -p test_g2_core_journal_contention.py -v
```

The scoped workflow checks out the exact PRhead, records commit/tree/Python, runs
ordinary journal + lifecycle tests on Windows/Ubuntu, and uploads source/test logs.
Heavy diagnostics require explicit workflow_dispatch **and benchmark=true**; then
both platforms retain JSON/raw timing samples and log artifacts. No scheduled or
routine heavy benchmark, generic CI change or Factory routing is added. Final run
IDs and per-platform counts are recorded in PR93/Issue92 after inspection.

## Owner decisions, residuals and rollback

No production custody/fencing decision is made by this PR.

1. **Writer exclusion/recovery:** A) offline maintenance window with all writers and
   restart supervisors stopped, evidence retained and operator-authorized action;
   B) a separately designed supervised local fenced-writer protocol;
   C) distributed fencing/custody service if future requirements justify it.
   Recommend A for current offline experiments only; B needs a separate contract
   before any operational activation. PID files alone are insufficient. Deferral
   means an orphaned operational journal remains blocked, never auto-unlocked.
2. **Backup custody:** owner chooses independent media/location/access/encryption,
   retained expected anchors and RPO/RTO/retention. Recommend independently verified
   encrypted off-device custody before activation. Current same-disk drills do not
   supply it; do not treat restore success as that decision or protection.
3. **Performance/isolation:** agree actual capacity/latency targets and authorize a
   separately bounded worker/resource contract if needed. Recommend no synchronous
   journal replay/backup on Core Run. New checkpoint/index formats and integrity
   tradeoffs require approval. Without these gates, operational isolation remains
   NOT MET rather than a generic claim that threads make it safe.

#92/#87 remain open. No live/paper execution, data pruning, production service,
cloud/secrets/paid resources, Factory/holdout or automatic worker. Rollback is code
reversion on the feature branch after review; preserve journal/lock/evidence bytes.
No data migration or hash rewrite is needed. Never roll back by deleting evidence,
removing orphan locks automatically or overwriting a primary from a candidate copy.
