# Delayed research and reconciliation proof

The command below runs only synthetic fixtures. It uses native Binance-format
microsecond rows, the pinned #304 archive QA and the native #286 Core, Scanner
and Factory read path. A separately generated receipt fixture supplies the
original ACK and decision hashes for reconciliation. The archive fixture uses
simulated receipt times solely to exercise the existing TEST_ONLY consumer
adapter. Neither fixture represents exchange-observed or publisher-witnessed
availability. The output blocks current entry and contains no executable quote.

In a #271 draft checkout with Git objects for #286 and #304 available locally,
run this Windows PowerShell batch using Python 3.11 or later:

```powershell
$repo = (Get-Location).Path
$python = 'C:\Users\dell\Desktop\ATLAS-Quant-Lab\.venv\Scripts\python.exe'
$stage = Join-Path $env:TEMP ('atlas-delayed-' + [guid]::NewGuid())
$tree = Join-Path $stage 'src-tree'
$state = Join-Path $stage 'state'
$null = New-Item -ItemType Directory -Path $stage
git -C $repo archive --format=zip "--output=$stage/core.zip" d072544427d6b08473c88b2e36d5857cfd8581dc
if ($LASTEXITCODE) { throw 'PINNED_286_REQUIRED' }
git -C $repo archive --format=zip "--output=$stage/qa.zip" e0e08a8381a8cceaaa44d6ae2721e9cb0d004648 tools/historical_source_qa
if ($LASTEXITCODE) { throw 'PINNED_304_REQUIRED' }
Expand-Archive "$stage/core.zip" $tree
Expand-Archive "$stage/qa.zip" $tree -Force
foreach ($name in 'atlas_bounded_research_cycle.py','atlas_delayed_reconciliation.py','atlas_delayed_fixture_proof.py') {
    Copy-Item "$repo/tools/$name" "$tree/tools"
}
$previous = $env:PYTHONPATH
$env:PYTHONPATH = "$tree/src;$tree"
Push-Location $tree
try {
    $initial = & $python -B -m tools.atlas_delayed_fixture_proof $state
    if ($LASTEXITCODE) { throw 'FIXTURE_FAILED' }
    $reopened = & $python -B -m tools.atlas_delayed_fixture_proof $state
    if ($LASTEXITCODE -or $initial -cne $reopened) { throw 'REOPEN_DRIFT' }
    $reopened
} finally {
    Pop-Location
    $env:PYTHONPATH = $previous
}
```

The append-only store reuses the native G2 hash-chain and transaction primitives.
Exact replays return the original record. A different archive version adds a
linked record, with comparison MATCH, DIFFERENCE or GAP. Changed content under
the same version or changed original receipt/decision rejects. The retained
receipt envelope and archive admission must be verified by their original
consumers before this join. No current-entry route is exposed.

A real delayed run requires one authorized, locally retained native ZIP,
companion checksum, and pinned source/version manifest with exact-use and
retention authorization. This proof does not read existing archives, schedule
a job or contact a market endpoint. Live monitor and strict PIT/OOS are separate
qualification paths.
