$ErrorActionPreference='Stop'
$tokens=$null;$errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'ATLAS-WS-CONTINUOUS-RECOVERY.ps1'),[ref]$tokens,[ref]$errors)
if($errors.Count){throw ($errors|Out-String)}
$f=$ast.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Test-FreshPingBaseline'},$true)
if(!$f){throw 'FRESH_PING_BASELINE_HELPER_MISSING'}
. ([scriptblock]::Create($f.Extent.Text))
$expected='857bea957d1da3fa1ef1c01ace44a0bfda27f84c2750523184455936a48f2cf2'
function Fixture {
    @{identity=@{config_sha256=$expected};hold_reason='LIVE_SERVICE_CONTINUITY_CIRCUIT_OPEN';manifest_scope=@{verification_complete=$true};blockers=@();task_enabled=$true;task_state='Ready';collector_processes=0;supervisor_lock_available=$true}|ConvertTo-Json -Depth 5|ConvertFrom-Json
}
$d=Fixture
if(!(Test-FreshPingBaseline $d $expected).ready){throw 'EMPTY_ARRAY_REJECTED'}
$d.blockers=$null
if(!(Test-FreshPingBaseline $d $expected).ready){throw 'NULL_BLOCKERS_REJECTED'}
foreach($blocker in @('QUOTA_NOT_READY','COMPETING_COLLECTOR_OR_PROCESS_INSPECTION_UNKNOWN','OPERATOR_STOP_PRESENT_OR_UNKNOWN','DISK_RESERVE_LOW','UNKNOWN_BLOCKER')){
    $d=Fixture;$d.blockers=@($blocker);$r=Test-FreshPingBaseline $d $expected
    if($r.ready -or $r.retryable -or $r.failures -notcontains $blocker){throw 'TERMINAL_BLOCKER_LOST'}
}
$d=Fixture;$d.blockers=@('TASK_NOT_QUIESCENT_READY','SUPERVISOR_LOCK_UNPROVEN');$d.task_state='Running'
if(!(Test-FreshPingBaseline $d $expected).retryable){throw 'TRANSIENT_SCHEDULER_NOT_WAITED'}
$d.task_enabled=$false
if((Test-FreshPingBaseline $d $expected).retryable){throw 'DISABLED_TASK_RETRIED'}
$d=Fixture;$d.identity.config_sha256='wrong';$d.hold_reason='wrong';$d.manifest_scope.verification_complete=$false
$r=Test-FreshPingBaseline $d $expected
if($r.ready -or $r.retryable -or $r.failures.Count -ne 3){throw 'MULTIPLE_DRIFTS_HIDDEN'}
$d=Fixture
$r=Test-FreshPingBaseline $d ('a'*64)
if($r.ready -or $r.failures -notcontains 'INSTALLED_CONFIG_PIN_MISMATCH'){throw 'WRONG_EXPECTED_CONFIG_ACCEPTED'}
$tokens=$null;$errors=$null
$paramAst=[System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'ATLAS-WS-CONTINUOUS-RECOVERY.ps1'),[ref]$tokens,[ref]$errors)
$p=$paramAst.ParamBlock.Parameters|Where-Object {$_.Name.VariablePath.UserPath -ceq 'ExpectedPreviousConfigSha256'}
if(!$p){throw 'EXPECTED_PREVIOUS_CONFIG_PARAMETER_MISSING'}
Write-Output 'FRESH_PING_BASELINE_REGRESSIONS_PASS'
