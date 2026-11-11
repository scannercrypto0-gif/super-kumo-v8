# Issue295 — bounded research capacity, Codex B

Research-only orchestration over existing Factory H evaluation, Discoverer
ledger/checkpoint and Factory v2 immutable store. No new backtester, live order
dispatcher, historical/PIT attestation, winner selection or strategy promotion.
Owned paths: this directory and `.github/workflows/research-capacity-scale.yml`.
Base is the **unmerged** Factory #291 head `ea4ffd5ce278d93588338122ab6ac1af8ec4da26`;
the PR must remain stacked on `codex/pkg02-factory-execution`, not pretend these
dependencies are on main. A future base change requires a fresh pin review.

## Reuse and demonstrated gap (S0)

| Existing component | Disposition |
|---|---|
| Factory F batch ledger | Retained: source-blocked UNKNOWN bookkeeping; no executor or resource caps |
| `research_wp_r0/attempt_ledger.py` | Retained: COMPLETE unsupported; no extension |
| Discoverer #276 native ledger/checkpoint | Reused unchanged: verified chain, transaction, snapshots |
| Factory #291 evaluator and v2 H store | Reused unchanged: cost/exit A/B/C, full reports and idempotent immutable inserts |
| Gateway #292 modeled comparison | Reused read-only as report population/authority/UNKNOWN consumer boundary |
| Core #290 / Integration #293 | Pinned accepted receipts and compatible contract inventory, no original pipeline rerun |
| Audit #134/6775950476 | Accepted four-package synthetic integration reused; not re-executed |
| Codex A #294/#296 | Separate `tools/first_research_cycle/**` and own workflow; no intersecting paths |

The missing capability is fixed bounded parallel dispatch, OS resource control,
full logical status adapters and result-aware durable resume. Native in-process
evaluation is the S0 benchmark, intentionally measured separately: it has no
dispatch or durable orchestration cost. Faster evaluation is **not** presumed.

## Reproduction

Use a disposable checkout of this PR; Python 3.11/3.13 supported by the CI
matrix, Windows and Ubuntu. From repository root, set `PYTHONPATH` to `src;.`
(Windows) or `src:.` (Linux). Only test dependency is `pytest==9.0.2`.
Commands below use scratch directory names that must be absent for fresh runs.
The dependency command fetches only pinned Git source objects; no market data,
provider, cloud, observer or trading connection is used.

```text
python -B -m tools.research_capacity_scale dependencies --destination ../capacity-deps --fetch
python -B -m pytest tools/research_capacity_scale/tests -q --basetemp ../capacity-tests --junitxml=capacity-tests.xml
python -B -m tools.research_capacity_scale.benchmark --deps ../capacity-deps --output ../capacity-benchmark
python -B -m tools.research_capacity_scale plan --count 10 --output ../batch-plan.json
python -B -m tools.research_capacity_scale run --plan ../batch-plan.json --root ../batch-run --deps ../capacity-deps --workers 2
```

The same `run` invocation resumes its root. It never resets terminal failures,
creates replacement scientific identities or silently retries cancelled tasks.
For pytest optionally set `CAPACITY_DEPS` to the prepared absolute dependency
directory; otherwise the session stages the same pinned sources itself.
`dependencies.py` checks the dependency manifest's fixed SHA and every source
byte before activation. Factory's five kernel source hashes must match #291.

## Frozen inputs and scientific limits (S1/S4)

Plan v1 seals family/profile, generated regime tag, period, fold, hypothesis,
seed, config, evaluator, source snapshot, packet, selected cell and budgets.
Existing native Factory admission is applied even to skipped/rejected tasks.
Duplicate logical IDs, experiment IDs or seeds, changed frozen inputs and
unsupported source/authority claims fail closed. Source terms are internal
generated fixture use, not prospective or licensed market-data rights.

Predeclared benchmark: sizes **1/10/50**, seeds **295000+i**, workers **1/2**,
two fresh isolated processes each. New generated workloads scale price,
time/period and two risk profiles from an existing fixture constructor. Three
regime names are generated labels; they do not establish authentic Scanner
families, real regimes or independent market hypotheses. This does not repeat
Codex A's first cycle or accepted G4/285/March/April research.

Every evaluated task retains Factory's 72 outcome rows, 18 candidate/placebo
scenario/policy cells and full failed/unscanned attempt denominator. A task's
NO_FILL means its *predeclared passive candidate A cell* has all nonfills;
it does not erase other report rows. Native UNKNOWN outcomes stay unknown,
with no fabricated PnL/fill. A/B/C, taker/passive/stress, costs and exits all
come from the existing kernel. No gross or cost model is reimplemented.

Holdout starts strictly after every evaluation bar plus 72 hours and is never
opened. Fixed Bonferroni allocation is .05/(all planned tasks ×18), including
failures and skipped tasks. P-values and scientific inference are NOT_ESTIMABLE;
labels/null perturbations are not scientific independence evidence. Real PIT,
OOS, source timing/known-at, alpha and profitability remain unproved. No automatic
strategy promotion, order, actual fill or G0 approval is possible in this API.

## Scheduling and resources (S2)

Admission uses stable sorted logical IDs (finite FIFO), at most two fixed worker
processes, no arbitrary plugin/callback execution. No live G1/G2 queue adapter
is claimed: runner and workers use Windows BELOW_NORMAL or Linux nice+10 and an explicit
read-only control file `{"critical": false, "cancel": []}`. Critical/unknown
control blocks admission; critical saturation cancels within one second;
invalid/missing control fails closed. Cancellation lists contain logical IDs.
Publish changing control files atomically to avoid a partial-read failure.

Default per-worker: 128 MiB, CPU2s, wall5s, output256KiB, sampled IO16MiB.
Per invocation: wall120s, CPU80s, resident-memory512MiB, local files128MiB,
sampled worker IO512MiB, maximum three physical claims/task across resumes.
Static write reservation rejects oversized plans before admission. Worker CPU
and memory are kernel constrained: Windows nested JobObject commit-memory/user
CPU; Linux RLIMIT_AS/CPU/FSIZE. These counters/limits differ across platforms;
RSS is measured separately. Linux/Windows process/file startup is included in
controlled metrics; native baseline reports evaluator-only work.

Parent polls every25ms and stops owned workers at CPU/RSS/IO/wall caps. CPU,
IO and total RSS have sampling overshoot; **this is not a hard bandwidth cap**.
Only fixed worker output writes are bounded and reservations are conservative;
no untrusted user program can be submitted. Worker self-watchdog bounds wall
time, parent death and cleanup cancellation. Generation/parent verification
prevents killing unrelated or reused PIDs, including Windows venv launchers.
Metrics are for the current invocation, not invented aggregate CPU of a process
that crashed before publishing counters. Claims persist across invocations.

## Persistence and recovery (S3)

Native Factory report commit → immutable terminal receipt commit → native
Discoverer terminal checkpoint → ACK. Physical execution claim receipts are
committed before dispatch. No worker writes the result store. A result/outcome
committed before ACK is reconciled without another evaluation; a crash before
commit may evaluate again, but persists only one report/cost population.
Native REGISTERED/PENDING map CREATED/RUNNING; COMPLETE/FAILED/INVALID/ABANDONED
keep every adapter terminal status in the chained reason payload. All seven
terminal statuses are represented: SUCCEEDED, FAILED, SKIPPED, REJECTED,
CANCELLED, TIMEOUT, NO_FILL. Native schemas are unchanged.

One exclusive runner lease prevents duplicate schedulers. Stale generation
leases are archived; a restarted runner waits for bounded old-worker exit
before admission. Checkpoint and result corruption fail closed; no automatic
reset or hidden repair. Explicit restore requires a backup hash retained by the
caller outside the mutable run authority:

```text
python -B -m tools.research_capacity_scale restore --root ../batch-run --backup ../pinned-copy.sqlite --expected-sha INDEPENDENTLY_RETAINED_SHA256
```

Corrupt checkpoint bytes are quarantined. Nonempty corrupt WAL is not discarded.
Immutable outcomes, including failures, reconstruct terminal state from a pinned
initial backup. A corrupt store, bad backup or conflicting terminal receipt
blocks recovery. SQLite local integrity is not independent custody against an
attacker able to replace every local file and all external pins.

## Evidence and acceptance (S5)

`benchmark.json` contains native baseline and final CPU/RAM/time/IO/throughput,
sizes, repeats, exact source head and actual OS/Python. Every controlled run has
native SQLite stores/checkpoints, worker raw responses, full canonical result,
metrics and logs. `manifest.json` SHA256-binds all output files; CI uploads the
complete matrix for30days. A checked-in compact receipt can be retained beyond
artifact expiry. Raw checkpoint event order and retry metrics may differ;
**sorted logical outcomes and sealed report identities** must match1vs2 and
fresh process replays. Do not falsely require concurrent raw event logs to match.

Joined tests exercise all statuses, hard CPU/memory pressure, sampled IO,
critical backpressure, queued/active cancellation, concurrent runner rejection,
real parent death, four crash/commit/ACK windows, exhausted retries, corrupt
checkpoint explicit restore, corrupt store, dependency byte/manifest tamper,
holdout/embargo/future data, false PIT/fills/PnL, nonfinite values, null alias,
multiplicity/promotion and native report conservation/UNKNOWN propagation.

PASS_BOUNDED_RESEARCH_CAPACITY means this bounded generated engineering lane
passes the joined evidence gates. It grants no real-data research acceptance,
merged release, stage, G0 or trading permission. Final exact-head CI and gate
matrix are recorded in the consolidated PR/Issue295 delivery.
