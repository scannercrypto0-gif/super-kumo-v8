# Read-only template. Does not install/start Guardian, a task or a service.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Repository,
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$PythonSha256,
    [Parameter(Mandatory=$true)][string]$Contract,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedContractSha256
)
$ErrorActionPreference = 'Stop'
if (-not [IO.Path]::IsPathRooted($Python) -or -not [IO.Path]::IsPathRooted($Repository)) {
    throw 'Absolute reviewed paths required'
}
if ((Get-FileHash -LiteralPath $Python -Algorithm SHA256).Hash.ToLowerInvariant() -ne $PythonSha256) {
    throw 'Python executable drift; HOLD'
}
$priorPythonPath = $env:PYTHONPATH
Push-Location -LiteralPath $Repository
try {
    $env:PYTHONPATH = Join-Path $Repository 'src'
    & $Python -B scripts/evidence_guardian.py --preflight --contract $Contract --expected-contract-sha256 $ExpectedContractSha256
    if ($LASTEXITCODE -ne 0) { throw 'Preflight rejected; HOLD' }
} finally {
    $env:PYTHONPATH = $priorPythonPath
    Pop-Location
}
# Exit means local checks only. No delivery/loop/installation command follows.
