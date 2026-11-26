# Windows AG-F02 investigation

Base main `c6851bbaf0664d19490e374d6019687d1c234be7`. Read pipeline.py, lanes.py,
the actual synthetic collector/restart test and both referenced CI Windows logs.
No production defect is demonstrated by successful replay alone.

## Historical evidence / certainty

[Failed40187827670](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/40187827670):
Windows Python3.11.9,1failed/146passed/10skipped,189.63s. Checkout synthetic merge
5ff8fd2 of5427223b1ef548d1db00292dcbba7a8da1b20553 into base above. Store5,
journal5, replay_errors0, integrityOK, data lag30s, background-work reconcile_error.
It **did not print pending/errors/worker-alive status or shutdown timings**.

[Passed40188604093](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/40188604093):
same Windows Python3.11.9,147passed/10skipped,130.47s. Checkout synthetic merge
ce02a4d of945c2a30a2a7509440a4d06d4a7fe3bcc2da6045 into same base. The only
relevant change between these heads is diagnostic assertion text, **not a fix**.
Production pipeline blob513efe6a0386c233360f61828898e7b4e7e99574 and lanes
blobe31021828a70aabb3f62631b0ac240519b40a179 match failed head/current main.

Unassisted intermittent CI failure was **not reproduced** locally:25 instrumented
isolated temporary-directory executions and5fresh pytest processes passed before
the change. Therefore exact historical cause remains unproven; the mechanism
below is a confirmed, matching controlled reproduction, not invented CI telemetry.

## Confirmed fixture race, not a false HEALTHY rejection

The empty synthetic collector ignores duration_s and returns immediately. Startup
reconciliation is concurrent. Pipeline immediately calls recovery_lane.finish(),
whose unchanged1s budget can expire while five real WAL/FULL store/ACK writes are
in progress on Windows. finish then sets stop_event; the still-running startup
job can enqueue its follow-up trailing-gap recovery after that signal. The worker
exits without running that queued job. The later consumer finish/health query can
observe all five records stored even though background completion is incomplete.

Injecting **.25s per store upsert**,5times (>1s independently of host speed),
reproduced the same health/store/replay-error pattern in **5/5** executions. An
additional instrumented execution observed recovery finish1.004s with pending1,
worker_alive=true, errors[]; consumer finish.434s with errors0/worker_alive=false.
At pipeline return the recovery worker was dead but **one task was actually still
queued/pending**. This is not merely an outdated counter that can safely be cleared.
Durable journal retains authoritative records and existing restart logic retries
work; UNHEALTHY is correct for this deliberately premature shutdown.

## Small correction / preserved behavior

Only test fixture and evidence change. AG-F02's empty collector waits on a test
Event signalled when startup_reconcile returns, before triggering shutdown. The
signal is in finally: it means completion, **not success**, so errors still fail
all strict store/replay/HEALTHY assertions. No polling for a desired HEALTHY value,
status rewrite, skip, ignored worker error or weakening of assertions.

Five-second event guard is a bounded test failure safeguard, **not an increase of
either production1s shutdown timeout**. Measured baseline replay drain was up to
.682s; injected test adds1.25s of work. The guard allows this controlled successful
startup to complete before testing normal shutdown, rather than sleeping a fixed
amount or requiring durable Windows writes to fit an unrelated1s exit window.

Added regression with those five slow real upserts; it remains exactly HEALTHY.
Added negative regression holding a real background startup tail: records5 and
replay_errors0 still yield pending>0/worker_alive=true and exactly UNHEALTHY.
Negative worker is released/joined in finally. Existing production pipeline.py,
lanes.py, all health predicates and budgets are unchanged. Future genuine worker
stall/outage still fails closed. Assertion diagnostics match the independently
proposed diagnostic-only change in openPR110; no Hypothesis/tooling code imported
and no PR110 edit/merge.

## Local evidence / commands

Windows11, existing Python3.14.3/pytest9.1.1; no installations/network test calls.
After correction:25instrumented temporary runs PASS,5controlled slow runs PASS,
10fresh pytest-process executions PASS. Maximum recovery finish after correction
.068s (normal and slow cohorts); consumer finish .018s. These are observations,
not performance guarantees. [Summary data](windows_ag_f02.json).

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
python -B -m pytest -p no:cacheprovider tests/test_g1_wp04_fix01.py -k ag_f02 -q -rs --tb=short
python -B -m pytest -p no:cacheprovider tests/test_g1_wp01.py tests/test_g1_wp02.py tests/test_g1_wp03.py tests/test_g1_wp04.py tests/test_g1_wp04_fix01.py tests/test_g1_completion.py -q -rs --tb=short
```

Targeted:3PASS/9deselected in3.76s. Local G1 regression:149PASS/10existingSKIP,
one existing utcnow deprecation warning,97.18s. Skips:one optional live provider,
six Windows SIGKILL, two Windows load/throughput, one CI-only disposablePostgreSQL.
No new test skipped. Actual checked-out CI commit/tree are recorded in the PR
report after observed completion; no CI
success inferred from local results. A concise reproduction on the old checkout:

```powershell
@'
import importlib.util,tempfile,time
from pathlib import Path
from unittest.mock import patch
from aql.storage.operational_store import OperationalStore
spec=importlib.util.spec_from_file_location('case','tests/test_g1_wp04_fix01.py')
case=importlib.util.module_from_spec(spec);spec.loader.exec_module(case)
original=OperationalStore.upsert
def slow(store,*args,**kwargs):
    time.sleep(.25)
    return original(store,*args,**kwargs)
with tempfile.TemporaryDirectory() as d, patch.object(OperationalStore,'upsert',slow):
    case.TestT_WP04_FIX01_01_PipelineOrchestration().test_ag_f02_pipeline_restart_replays_journal(Path(d))
'@ | python -B -
```

Old fixture fails exact HEALTHY; corrected fixture passes without modifying
production behavior. Remaining uncertainty: historical CI could also have had a
different background error; absent status telemetry prevents attribution with
certainty. Local interpreter3.14 differs from historical3.11, so Windows3.11 CI is
required. No claim of general worker lifecycle certification or host I/O SLA.
No main edits, merge, issue closure, Factory, live exchange or cloud changes.
