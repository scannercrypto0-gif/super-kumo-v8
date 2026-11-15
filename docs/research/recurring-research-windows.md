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
