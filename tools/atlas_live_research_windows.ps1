param(
    [string]$State,
    [Parameter(Mandatory = $true)][string]$Python,
    [ValidateSet('plan','live','status','recover')][string]$Mode = 'plan',
    [string]$Pin,
    [long]$Slot,
    [string]$AuthorityModule,
    [switch]$StopAfterFirst
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$Python = (Resolve-Path -LiteralPath $Python).Path
if ($State) { $State = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($State) }
$stage = Join-Path ([IO.Path]::GetFullPath([IO.Path]::GetTempPath())) ('atlas-live-cycle-' + [guid]::NewGuid())
$null = New-Item -ItemType Directory -Path $stage
$previous = $env:PYTHONPATH
$code = 1
try {
    $zip = Join-Path $stage 'source.zip'
    $tree = Join-Path $stage 'source'
    git -C $repo archive --format=zip "--output=$zip" d072544427d6b08473c88b2e36d5857cfd8581dc
    if ($LASTEXITCODE -ne 0) { throw 'PINNED_286_OBJECT_REQUIRED' }
    Expand-Archive -LiteralPath $zip -DestinationPath $tree
    $transportZip = Join-Path $stage 'transport.zip'
    git -C $repo archive --format=zip "--output=$transportZip" 0a45cb6de6027b6fba54320e07b0faf3317a5382 tools/binance_live_feed
    if ($LASTEXITCODE -ne 0) { throw 'PINNED_305_OBJECT_REQUIRED' }
    Expand-Archive -LiteralPath $transportZip -DestinationPath $tree -Force
    foreach ($name in @('atlas_live_research_cycle.py', 'atlas_single_receipt.py', 'atlas_single_receipt_runner.py')) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $tree 'tools')
    }
    $env:PYTHONPATH = "$tree\src;$tree"
    $arguments = @('-B', '-m', 'tools.atlas_live_research_cycle', $Mode)
    if ($State) { $arguments += @('--state', $State) }
    if ($Slot) { $arguments += @('--slot', $Slot) }
    if ($Pin) { $arguments += @('--pin', $Pin) }
    if ($AuthorityModule) { $arguments += @('--authority-module', $AuthorityModule) }
    if ($StopAfterFirst) { $arguments += '--stop-after-first' }
    Push-Location -LiteralPath $tree
    try {
        & $Python @arguments
        $code = $LASTEXITCODE
    } finally {
        Pop-Location
    }
} finally {
    $env:PYTHONPATH = $previous
    $resolved = (Resolve-Path -LiteralPath $stage).Path
    if ($resolved -eq $stage -and (Split-Path -Leaf $resolved) -match '^atlas-live-cycle-[0-9a-f-]{36}$') {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
exit $code
