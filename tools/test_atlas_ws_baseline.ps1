$ErrorActionPreference='Stop'
$tokens=$null;$errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'ATLAS-WS-CONTINUOUS-RECOVERY.ps1'),[ref]$tokens,[ref]$errors)
if($errors.Count){throw ($errors|Out-String)}
$f=$ast.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Test-FreshPingBaseline'},$true)
. ([scriptblock]::Create($f.Extent.Text))
function Fixture {
    '{"identity":{"config_sha256":"857bea957d1da3fa1ef1c01ace44a0bfda27f84c2750523184455936a48f2cf2"},"hold_reason":"LIVE_SERVICE_CONTINUITY_CIRCUIT_OPEN","manifest_scope":{"verification_complete":true},"blockers":[],"task_enabled":true,"task_state":"Ready","collector_processes":0,"supervisor_lock_available":true}'|ConvertFrom-Json
}
$d=Fixture
if(!(Test-FreshPingBaseline $d).ready){throw 'EMPTY_ARRAY_REJECTED'}
$d.blockers=$null
if(!(Test-FreshPingBaseline $d).ready){throw 'NULL_BLOCKERS_REJECTED'}
foreach($blocker in @('QUOTA_NOT_READY','COMPETING_COLLECTOR_OR_PROCESS_INSPECTION_UNKNOWN','OPERATOR_STOP_PRESENT_OR_UNKNOWN','DISK_RESERVE_LOW','UNKNOWN_BLOCKER')){
    $d=Fixture;$d.blockers=@($blocker);$r=Test-FreshPingBaseline $d
    if($r.ready -or $r.retryable -or $r.failures -notcontains $blocker){throw 'TERMINAL_BLOCKER_LOST'}
}
$d=Fixture;$d.blockers=@('TASK_NOT_QUIESCENT_READY','SUPERVISOR_LOCK_UNPROVEN');$d.task_state='Running'
if(!(Test-FreshPingBaseline $d).retryable){throw 'TRANSIENT_SCHEDULER_NOT_WAITED'}
$d.task_enabled=$false
if((Test-FreshPingBaseline $d).retryable){throw 'DISABLED_TASK_RETRIED'}
$d=Fixture;$d.identity.config_sha256='wrong';$d.hold_reason='wrong';$d.manifest_scope.verification_complete=$false
$r=Test-FreshPingBaseline $d
if($r.ready -or $r.retryable -or $r.failures.Count -ne 3){throw 'MULTIPLE_DRIFTS_HIDDEN'}
Write-Output 'FRESH_PING_BASELINE_REGRESSIONS_PASS'
