# Execute the actual Apply helper against an exclusive filesystem lock and
# mocked snapshots/private authorization: no Windows task or network calls.
$ErrorActionPreference='Stop'
$ast=[System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'atlas_ws_resilience_windows.ps1'),[ref]$null,[ref]$null)
$f=$ast.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Get-AuthorizedApplySnapshot'},$true)
. ([scriptblock]::Create($f.Extent.Text))
$root=Join-Path ([IO.Path]::GetTempPath()) ('atlas-apply-lock-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root|Out-Null
[IO.File]::WriteAllText((Join-Path $root 'supervisor.lock'),'')
$script:checks=0;$script:failTerminal=$false
function Get-UniqueTask {return @{State='Ready'}}
function Snapshot($task,[bool]$locked){
    if(!$locked -or !$script:lock){throw 'UNLOCKED_SNAPSHOT'}
    return @{python='not-executed';supervisor_lock_available=$locked}
}
function Invoke-PrivateCheck($mode,$snapshot){
    $probe=$null;$blocked=$false
    try{$probe=[IO.File]::Open((Join-Path $root 'supervisor.lock'),'Open','ReadWrite','None')}catch [IO.IOException]{$blocked=$true}finally{if($probe){$probe.Dispose()}}
    if(!$blocked){throw 'AUTHORIZATION_NOT_UNDER_EXCLUSIVE_LOCK'}
    $script:checks++
    if($script:failTerminal){$script:privateFailure=@{preflight=@{retryable_scheduler_only=$false}};throw 'OWNER_HOST_PREFLIGHT_BLOCKED'}
    if($script:checks -eq 1){$script:privateFailure=@{preflight=@{retryable_scheduler_only=$true}};throw 'OWNER_HOST_PREFLIGHT_BLOCKED'}
    return @{status='EXPLICIT_OWNER_AUTHORIZATION_VERIFIED'}
}
try{
    $null=Get-AuthorizedApplySnapshot $root 5
    if($script:checks -ne 2 -or !$script:lock){throw 'TRANSIENT_RETRY_OR_COMMIT_LOCK_LOST'}
    $script:lock.Dispose();$script:lock=$null
    $script:failTerminal=$true;$before=$script:checks;$caught=$false
    try{$null=Get-AuthorizedApplySnapshot $root 5}catch{$caught=$_.Exception.Message -ceq 'OWNER_HOST_PREFLIGHT_BLOCKED'}
    if(!$caught -or $script:checks -ne ($before+1) -or $script:lock){throw 'TERMINAL_RETRIED_OR_LOCK_LEAKED'}
    Write-Output 'WS_APPLY_EXCLUSIVE_LOCK_AND_TRANSIENT_REGRESSION_PASS'
}finally{if($script:lock){$script:lock.Dispose();$script:lock=$null};Remove-Item -LiteralPath $root -Recurse -Force}
