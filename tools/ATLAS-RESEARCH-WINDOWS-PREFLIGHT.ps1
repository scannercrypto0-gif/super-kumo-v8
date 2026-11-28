# ATLAS research-only Windows preflight; does not stop/start tasks or access network.
[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$StateRoot = "C:\\dev\\ATLAS\\g1-completion",
    [string]$OutputDirectory = "$env:TEMP\\atlas-research-preflight"
)
$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location -LiteralPath $repoRoot
try {
$tasks = @("ATLAS-Research-Sustained-Spot-WS", "ATLAS-Research-Sustained-BTCUSDT-Daily")
$report = [ordered]@{
    schema = "aql.windows.research-preflight.v1"
    checked_at_utc = [DateTime]::UtcNow.ToString("o")
    repository_head = $null
    state_root_exists = (Test-Path -LiteralPath $StateRoot -PathType Container)
    tasks = @()
    offline_tests = "NOT_RUN"
    operational_research_e2e = "NOT_ATTESTED"
    source_authenticity = "NOT_ATTESTED"
    trading_authority = "NONE"
}
try {
    $head = (& git rev-parse HEAD 2>$null)
    if ($LASTEXITCODE -eq 0) { $report.repository_head = "$head".Trim() }
} catch {}
foreach ($name in $tasks) {
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    $report.tasks += [ordered]@{
        name = $name
        exists = ($null -ne $task)
        state = if ($null -ne $task) { "$($task.State)" } else { "NOT_FOUND" }
    }
}
$testPaths = @(
    "tests/test_research_timeframes.py",
    "tests/test_research_bar_store.py",
    "tests/test_research_vision_import.py",
    "tests/test_research_ws_1m_ingest.py",
    "tests/test_research_ws_capture_import.py",
    "tests/test_research_durability_readback.py",
    "tests/test_research_offline_one_shot.py",
    "tests/test_research_service_bridge_gate.py",
    "tests/test_research_capture_spool.py",
    "tests/test_research_1m_collector.py",
    "tests/test_research_live_1m_capture.py",
    "tests/test_research_live_one_shot.py",
    "tests/test_research_forward_scanner_boundary.py",
    "tests/test_research_forward_core_read.py",
    "tests/test_research_warehouse_plan.py"
)
$missing = @($testPaths | Where-Object { -not (Test-Path -LiteralPath $_ -PathType Leaf) })
if ($missing.Count -gt 0) {
    $report.offline_tests = "BLOCKED_MISSING_TEST_FILES"
    $report.missing_tests = $missing
} else {
    & $Python -m pytest -q @testPaths
    $report.offline_tests = if ($LASTEXITCODE -eq 0) { "PASS" } else { "FAIL" }
}
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$output = Join-Path $OutputDirectory "research-preflight.json"
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $output -Encoding UTF8
Write-Output ($report | ConvertTo-Json -Depth 6)
Write-Output "RECEIPT_PATH=$output"
} finally {
    Pop-Location
}
if ($report.offline_tests -ne "PASS") { exit 1 }
