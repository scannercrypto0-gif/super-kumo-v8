# Owner-local, bounded research capture. Does not modify scheduled tasks or trading.
[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$StateRoot = "C:\dev\ATLAS\g1-completion",
    [string]$OutputDirectory = "$env:TEMP\atlas-research-1m",
    [switch]$AuthorizeOriginal1mResearchCapture
)
$ErrorActionPreference = "Stop"
$preflight = Join-Path $PSScriptRoot "ATLAS-RESEARCH-WINDOWS-PREFLIGHT.ps1"
if (-not (Test-Path -LiteralPath $preflight -PathType Leaf)) {
    throw "PREFLIGHT_NOT_FOUND"
}
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$preflightDir = Join-Path $OutputDirectory "preflight"
& $preflight -Python $Python -StateRoot $StateRoot -OutputDirectory $preflightDir
if ($LASTEXITCODE -ne 0) { throw "RESEARCH_PREFLIGHT_FAILED" }
if (-not $AuthorizeOriginal1mResearchCapture) {
    Write-Output "READY_OFFLINE_ONLY: live capture requires explicit -AuthorizeOriginal1mResearchCapture"
    exit 0
}
$spool = Join-Path $OutputDirectory "spool"
$store = Join-Path $OutputDirectory "research-1m.sqlite"
# This invokes the separate bounded 1m research stream, not the running 15m task.
& $Python -m aql.research_live_one_shot --spool-dir $spool --store $store --frame-limit 5 --wall-seconds 900 --interval 5m --authorize-original-1m-research-capture
if ($LASTEXITCODE -ne 0) { throw "ORIGINAL_1M_CAPTURE_OR_READBACK_FAILED" }
Write-Output "OWNER_LOCAL_RESEARCH_CAPTURE_COMMAND_COMPLETED; review receipt for authenticity limits"
