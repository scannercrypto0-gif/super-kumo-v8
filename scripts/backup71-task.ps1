param(
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$Repository,
    [Parameter(Mandatory=$true)][string]$Config,
    [ValidateSet('Backup','Preflight','Health')][string]$Mode='Preflight',
    [Parameter(Mandatory=$true)][string]$LogDirectory
)
$ErrorActionPreference='Stop'
# Fixed argv, no Invoke-Expression, secrets, downloads or security-policy bypass.
try {
    if (!(Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Interpreter unavailable' }
    if (!(Test-Path -LiteralPath $Config -PathType Leaf)) { throw 'Approved config unavailable' }
    [System.Diagnostics.Process]::GetCurrentProcess().PriorityClass='BelowNormal'
    [void][System.IO.Directory]::CreateDirectory($LogDirectory)
    $log=Join-Path $LogDirectory (([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))+'-'+[Guid]::NewGuid().ToString('N')+'.jsonl')
    $env:PYTHONPATH=Join-Path $Repository 'src'
    $arguments=@('-B','-m','aql.archive.automation')
    if ($Mode -eq 'Health') { $arguments+= 'health' }
    else { $arguments+= 'backup' }
    $arguments+=@('--config',$Config)
    if ($Mode -eq 'Backup') { $arguments+='--execute' }
    # Python CLI prints only typed errors and non-secret results. Full local paths
    # remain local; this wrapper never sends Telegram/Drive messages.
    & $Python @arguments | Out-File -LiteralPath $log -Encoding utf8 -NoClobber
    $result=$LASTEXITCODE
    exit $result
} catch {
    Write-Output '{"status":"SCHEDULER_WRAPPER_FAILED_NO_ACCEPTANCE"}'
    exit 1
}
