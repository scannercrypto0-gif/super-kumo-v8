param(
    [Parameter(Mandatory = $true)][string]$State,
    [Parameter(Mandatory = $true)][string]$Python,
    [string]$ExpectedPlan,
    [switch]$InterruptAfterAck
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$Python = (Resolve-Path -LiteralPath $Python).Path
$State = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($State)
$stage = Join-Path ([IO.Path]::GetFullPath([IO.Path]::GetTempPath())) ('atlas-cycle-' + [guid]::NewGuid())
$null = New-Item -ItemType Directory -Path $stage
$previous = $env:PYTHONPATH
$code = 1
try {
    $zip = Join-Path $stage 'source.zip'
    $tree = Join-Path $stage 'source'
    git -C $repo archive --format=zip "--output=$zip" d072544427d6b08473c88b2e36d5857cfd8581dc
    if ($LASTEXITCODE -ne 0) { throw 'PINNED_286_OBJECT_REQUIRED' }
    Expand-Archive -LiteralPath $zip -DestinationPath $tree
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'atlas_bounded_research_cycle.py') -Destination (Join-Path $tree 'tools')
    $env:PYTHONPATH = "$tree\src;$tree"
    $arguments = @('-B', '-m', 'tools.atlas_bounded_research_cycle', $State)
    if ($ExpectedPlan) { $arguments += @('--expected-plan', $ExpectedPlan) }
    if ($InterruptAfterAck) { $arguments += '--interrupt-after-ack' }
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
    if ($resolved -eq $stage -and (Split-Path -Leaf $resolved) -match '^atlas-cycle-[0-9a-f-]{36}$') {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
exit $code
