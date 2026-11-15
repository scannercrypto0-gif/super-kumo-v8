# Manual recurring research on Windows

This operator path runs two to eight consecutive four-bar TEST_ONLY windows
locally. It never opens an original archive. The earlier owner-authorized
real archive run remains a separate, retained retrospective result.

In the #271 draft checkout, stage the exact Core commit already used by the
bounded fixture runner. Run all commands below in the same PowerShell session.

```powershell
$repo = (Get-Location).Path
$python = 'C:\Users\dell\Desktop\ATLAS-Quant-Lab\.venv\Scripts\python.exe'
$stage = Join-Path $env:TEMP ('atlas-recur-' + [guid]::NewGuid())
$tree = Join-Path $stage 'tree'
$state = Join-Path $env:LOCALAPPDATA ('atlas-recur-' + [guid]::NewGuid())
$null = New-Item -ItemType Directory -Path $stage
git -C $repo archive --format=zip "--output=$stage/core.zip" d072544427d6b08473c88b2e36d5857cfd8581dc
if ($LASTEXITCODE) { throw 'PINNED_286_REQUIRED' }
Expand-Archive "$stage/core.zip" $tree
foreach ($file in 'atlas_bounded_research_cycle.py','atlas_recurring_research.py') {
    Copy-Item "$repo/tools/$file" "$tree/tools"
}
$env:PYTHONPATH = "$tree/src;$tree"
Set-Location $tree
$plan = & $python -B -m tools.atlas_recurring_research plan | ConvertFrom-Json
& $python -B -m tools.atlas_recurring_research start --state $state --pin $plan.sha256
```

Use the same staged tree, Python and state on restart. Keep the original
plan pin. The defaults are two adjacent fixture windows starting at
1735689600000 UTC milliseconds. If changed, pass the same start and count
to plan, start and recover.

```powershell
& $python -B -m tools.atlas_recurring_research status --state $state
& $python -B -m tools.atlas_recurring_research stop --state $state
& $python -B -m tools.atlas_recurring_research rearm --state $state
& $python -B -m tools.atlas_recurring_research recover --state $state --pin $plan.sha256
```

Stop requests take effect between fixture windows. An exclusive writer lock
prevents overlapping runs and is released on process exit. SQLite persists
the sealed schedule and the append-only completion receipts. A restarted
operator skips committed windows and resumes any incomplete native state.
READY denotes a pending window, RUNNING denotes an active writer, COMPLETE
denotes an immutable receipt and BLOCKED denotes an operator stop. No timer,
scheduler, autonomous retry, original-source intake or live connection is
enabled. A failed process is restarted explicitly with recover.

For isolated acceptance use a fresh fixture state, add
--fixture-interrupt before-ack, after-ack, before-append or after-append
to start, expect exit 73, then recover with the same pin. A subsequent
start and a separate status should match the recovered JSON exactly.
The original retained archive's result remains RETROSPECTIVE_NON_PIT.
The recurring path has no Lab, live, orders or current entry output.

## Bounded automatic fixture qualification

The Windows Task Scheduler wrapper stages the same pinned runtime and calls
its existing recover command. Register under the logged-in user with limited
rights. Use a fresh state and an existing private directory for configuration.
Install registers a finite two-tick schedule by default and starts it at the
first trigger. The staged config remains available for readback after removal.

```powershell
$ctl = '.\tools\atlas_recurring_schedule_windows.ps1'
$config = Join-Path $env:LOCALAPPDATA 'atlas-research-proof.json'
$state = Join-Path $env:LOCALAPPDATA 'atlas-research-proof-state'
$python = 'C:\Users\dell\Desktop\ATLAS-Quant-Lab\.venv\Scripts\python.exe'
& $ctl -Mode install -Config $config -State $state -Python $python -TaskName ATLAS-Research-Proof
& $ctl -Mode status -Config $config
```

Use the same config with Mode start for an on-demand trigger within the
deadline, stop to pause fixture windows, rearm to clear the request, recover
for explicit offline catch-up, and remove to unregister the task. Review
ticks.jsonl in the staged runtime for exit status and receipt pins. A failed
tick can be retried by the next scheduled trigger within the finite deadline.
The task uses the logged-in user session and cannot run while the PC is off.
Windows may run a missed trigger when available within the deadline. A
recovery invocation picks up unfinished logical windows and skips committed
ones. No automatic original-source execution is configured.

## Periodic authorized retained-archive mode

The same Task Scheduler wrapper accepts a fixed operator-approved JSON array
of up to eight distinct, ascending UTC days. A tick processes at most the
earliest pending day. It waits for the exact local ZIP and checksum pair,
does not download, and leaves unauthorized files outside the queue.
Use one durable private NTFS state directory for all authorized batches on
this host. Never reset or copy that state to rerun a claimed original.

For each job include `start_ms`, `end_ms` (one full UTC day),
`cutoff_ms` (after the end and no later than preflight), `archive`
(`BTCUSDT-1m-YYYY-MM-DD.zip`), `experiment`
(`ATLAS-RETROSPECTIVE-BTCUSDT-YYYYMMDD`), `archive_sha256`,
`checksum_sha256`, `original_reads` (exactly the integer 1),
`source` (absolute folder on a fixed local drive), `host` (Windows
COMPUTERNAME), `rights_ref`, `authorization_ref`, and `retention_scope`.
The references must identify actual permission for one original read on the
specified host. The operator independently seals the JSON with the native
`aql.observation.contracts.digest` and supplies that pin. The pin detects
changes to the approved plan. Keep the plan and runtime under the operator's
private ACL. Jan 1 and May 6 are excluded from this queue.

```powershell
& $ctl -Mode install -Config $config -State $state -Python $python -TaskName ATLAS-Research-Authorized -AuthorizedPlan $planPath -AuthorizedPlanSha256 $approvedPin -IntervalMinutes 15 -Ticks 4 -InstallDisabled
& $ctl -Mode health -Config $config
& $ctl -Mode enable -Config $config
```

The install preflight imports the exact #226, #304, #286 and #267 runtime
and validates the pinned plan without opening original bytes. Files arriving
late are picked up on the next finite tick. Already committed windows return
their immutable receipts. A process death after a claim but before a sealed
result blocks the queue and prevents a second original read. Preserve the
state and inspect the failure; a new authorized recovery disposition is
needed for an incomplete claim. The next tick performs a saved-result read
after a completed commit. Tick failures naturally back off to the configured
interval; no automatic retries occur inside a tick.

Use stop, status, rearm, recover and remove as above. Stop applies before the
next original read and allows an in-flight native commit to finish. Remove
unregisters the task and retains state and logs. Keep the authorized state
for the agreed retention period, then dispose of its private source copies
and derived records under company policy. Do not deploy an authentic task
until the exact archive, company-host use, retention, and any required
acquisition permission are established. Outputs are RETROSPECTIVE_NON_PIT
and NO_CURRENT_ENTRY.

Health reports native task state, last exit, missed-run count and the last
sanitized tick. Disable prevents new scheduled invocations; use stop as well
to hold the next original claim in an active invocation. Enable and start
reject expired schedules. Reinstall a new finite task with a new config and
the same private state for a separately approved batch; an older day's claim
remains durable. The wrapper checks critical staged code, executable and
launcher hashes before dispatch. Treat a runtime mismatch as a deployment
failure and preserve the state. Scheduled actions use their saved paths,
without the installing PowerShell session. The registered limited-user task
survives reboot and requires that user to log on; catch-up applies only while
the finite schedule is still valid. This workflow does not configure a
system-account service, reboot trigger or always-on polling.
