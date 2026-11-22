[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{40}$')][string]$ExpectedCommit,
    [ValidateSet('ActivateAndObserve','Observe','RepairPermitAndObserve','ApplyPingCorrectionAndObserve')][string]$Mode='ActivateAndObserve',
    [string]$OwnerDecisionRef,
    [ValidateRange(6,48)][int]$ObserveHours=24,
    [string]$ExpectedInstalledConfig='34bbaa0d7a419d4a45731b03d103753cff6428e22e11003fb3bc433a0d504dd9'
)
# One local handoff. Uses the existing task, not a second collector/schedule.
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$wrapper=Join-Path $PSScriptRoot 'atlas_ws_resilience_windows.ps1'
$taskName='ATLAS-Research-Sustained-Spot-WS'
$policy='7cf6b4ff865fe5fef43ff59fe3f23d7a0cfb555dd76d8b0eb715e8a43f658915'
$head=& git -C $repo rev-parse HEAD
if($LASTEXITCODE -or $head -cne $ExpectedCommit){throw 'EXACT_CANDIDATE_COMMIT_REQUIRED'}
function Read-ConfigPath($Task){
    $m=[regex]::Match($Task.Actions[0].Arguments,'(?i)(?:^|\s)-Config\s+(?:"([^"]+)"|''([^'']+)''|(\S+))')
    if(!$m.Success){throw 'CONFIG_PATH_NOT_FOUND'}
    return [Environment]::ExpandEnvironmentVariables(($m.Groups[1].Value+$m.Groups[2].Value+$m.Groups[3].Value))
}
function Write-NewJson([string]$Path,$Value){
    $bytes=[Text.Encoding]::UTF8.GetBytes(($Value|ConvertTo-Json -Depth 30 -Compress))
    $stream=[IO.File]::Open($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try{$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)}finally{$stream.Dispose()}
}
function Test-FreshPingBaseline($Diagnostic){
    $failures=@()
    if($Diagnostic.identity.config_sha256 -cne '857bea957d1da3fa1ef1c01ace44a0bfda27f84c2750523184455936a48f2cf2'){$failures+='INSTALLED_CONFIG_PIN_MISMATCH'}
    if($Diagnostic.hold_reason -cne 'LIVE_SERVICE_CONTINUITY_CIRCUIT_OPEN'){$failures+='HOLD_REASON_MISMATCH'}
    if($Diagnostic.manifest_scope.verification_complete -ne $true){$failures+='RUNTIME_MANIFEST_NOT_VERIFIED'}
    $blockers=@($Diagnostic.blockers | Where-Object {$null -ne $_ -and [string]$_ -ne ''})
    $failures+=@($blockers)
    # Only a scheduled supervisor briefly holding its lock is safe to wait out.
    # Quota, collector, integrity, disabled task and unknown conditions stay terminal.
    $transient=($failures.Count -gt 0 -and $Diagnostic.task_enabled -eq $true -and
        $Diagnostic.collector_processes -eq 0 -and
        @($failures | Where-Object {$_ -notin @('TASK_NOT_QUIESCENT_READY','SUPERVISOR_LOCK_UNPROVEN')}).Count -eq 0)
    [pscustomobject]@{schema='atlas.ws.fresh-ping-baseline.v1';ready=($failures.Count -eq 0);
        retryable=$transient;failures=@($failures);installed_config_sha256=$Diagnostic.identity.config_sha256;
        hold_reason=$Diagnostic.hold_reason;manifest_verified=$Diagnostic.manifest_scope.verification_complete;
        task_state=$Diagnostic.task_state;task_enabled=$Diagnostic.task_enabled;
        collector_processes=$Diagnostic.collector_processes;supervisor_lock_available=$Diagnostic.supervisor_lock_available;
        quota=$Diagnostic.quota;orders=0;trading_authority='NONE'}
}
$t=@(Get-ScheduledTask -TaskName $taskName)
if($t.Count -ne 1 -or @($t[0].Actions).Count -ne 1){throw 'TASK_NOT_UNIQUE'}
$config=Read-ConfigPath $t[0];$root=Split-Path -Parent $config
if($Mode -ceq 'ActivateAndObserve' -or $Mode -ceq 'ApplyPingCorrectionAndObserve'){
    if(!$OwnerDecisionRef){throw 'EXPLICIT_CONTINUOUS_OWNER_DECISION_REQUIRED'}
    if($Mode -ceq 'ActivateAndObserve' -and (Test-Path -LiteralPath (Join-Path $root 'continuous-research.authorized.json'))){throw 'CONTINUOUS_ALREADY_ACTIVATED_USE_OBSERVE'}
    $baselineDeadline=[DateTimeOffset]::UtcNow.AddMinutes(3)
    do{
        $raw=@(& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $wrapper -ExpectedCommit $ExpectedCommit -Mode Diagnose)
        if($LASTEXITCODE){$raw|Write-Output;throw 'CONTINUOUS_PREFLIGHT_BLOCKED'}
        $d=($raw -join "`n")|ConvertFrom-Json
        if($Mode -cne 'ApplyPingCorrectionAndObserve'){break}
        $assessment=Test-FreshPingBaseline $d
        if($assessment.ready){break}
        $assessment|ConvertTo-Json -Depth 15 -Compress|Write-Output
        if(!$assessment.retryable -or [DateTimeOffset]::UtcNow -ge $baselineDeadline){
            $outputDir=Join-Path $repo 'owner-results'
            New-Item -ItemType Directory -Force -Path $outputDir|Out-Null
            $blockedFile=Join-Path $outputDir ('ws-baseline-blocked-'+[guid]::NewGuid().ToString('N')+'.json')
            Write-NewJson $blockedFile $assessment
            Write-Output ('REPORT_FILE='+$blockedFile)
            throw ('FRESH_PING_BASELINE_BLOCKED:'+($assessment.failures -join ','))
        }
        Start-Sleep -Seconds 5
    }while($true)
    if($Mode -ceq 'ApplyPingCorrectionAndObserve'){
        # Exact baseline was verified above; no host state was changed while waiting.
    }else{
    if($d.identity.config_sha256 -cne $ExpectedInstalledConfig -or $d.hold_slot_ms -ne 1795329900000L -or
        $d.hold_reason -cne 'PILOT_STOP_ConnectionResetError' -or @($d.blockers).Count -ne 0 -or
        !$d.manifest_scope.verification_complete){throw 'CONTINUOUS_BASELINE_DRIFT'}
    $claim=Get-Content -LiteralPath (Join-Path $root 'operator-recovery.active.json') -Raw|ConvertFrom-Json
    if($claim.authorization_sha256 -cne 'fe42645ec37f9b36f80a0863d24951b67fdd548b231c432e50735bb2e13e0817'){
        throw 'PRIOR_OPERATOR_AUTHORIZATION_DRIFT'
    }
    }
    $now=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    $permit=[ordered]@{schema='atlas.ws.operator-authorization.v1';action='DEPLOY_ONE_RECOVERY';
        identity_sha256=$d.identity_sha256;candidate_commit=$ExpectedCommit;task_name=$taskName;
        issued_ms=$now;expires_ms=($now+1800000L);max_segments=1;max_connections=2;orders=0;trading_authority='NONE';
        allow_task_action_pin_update=$true;allow_clock_probe=$true;existing_pilot_quota_only=$true;
        owner_decision_ref=$OwnerDecisionRef;continuous_research=$true;continuity_policy_sha256=$policy;
        allow_explicit_missing_intervals=$true}
    if($Mode -ceq 'ApplyPingCorrectionAndObserve'){$permit['fresh_ping_correction']=$true;$permit['expected_previous_config_sha256']=$d.identity.config_sha256}
    $file=Join-Path ([IO.Path]::GetTempPath()) ('atlas-continuous-permit-'+[guid]::NewGuid().ToString('N')+'.json')
    Write-NewJson $file $permit
    $applyRaw=@(& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $wrapper -ExpectedCommit $ExpectedCommit -Mode Apply -AuthorizationFile $file)
    $applyExit=$LASTEXITCODE
    $applyRaw|Write-Output
    if($applyExit){
        $outputDir=Join-Path $repo 'owner-results'
        New-Item -ItemType Directory -Force -Path $outputDir|Out-Null
        $blockedFile=Join-Path $outputDir ('ws-apply-blocked-'+[guid]::NewGuid().ToString('N')+'.json')
        $failure=($applyRaw -join "`n")|ConvertFrom-Json
        Write-NewJson $blockedFile $failure
        Write-Output ('REPORT_FILE='+$blockedFile)
        throw 'CONTINUOUS_DEPLOYMENT_BLOCKED_SEE_SAVED_RECEIPT'
    }
}
if($Mode -ceq 'RepairPermitAndObserve'){
    if(!$OwnerDecisionRef){throw 'EXPLICIT_REPAIR_OWNER_DECISION_REQUIRED'}
    $repair=Join-Path $PSScriptRoot 'atlas_ws_permit_repair.py'
    & git -C $repo diff --quiet HEAD -- $repair
    if($LASTEXITCODE){throw 'REPAIR_CODE_DRIFT'}
    $cfg=Get-Content -LiteralPath $config -Raw|ConvertFrom-Json
    $lock=$null
    try{
        $lock=[IO.File]::Open((Join-Path $root 'supervisor.lock'),'Open','ReadWrite','None')
        & $cfg.python -B $repair --config $config --expected-commit $ExpectedCommit --permit-dir ([IO.Path]::GetTempPath()) --owner-ref $OwnerDecisionRef
        if($LASTEXITCODE){throw 'ORIGINAL_PERMIT_REPAIR_BLOCKED'}
    }finally{if($lock){$lock.Dispose()}}
}
$cfg=Get-Content -LiteralPath $config -Raw|ConvertFrom-Json
$configPin=(Get-FileHash -LiteralPath $config -Algorithm SHA256).Hash.ToLowerInvariant()
$oldPythonPath=$env:PYTHONPATH
$deadline=[DateTimeOffset]::UtcNow.AddHours($ObserveHours)
$outputDir=Join-Path $repo 'owner-results'
New-Item -ItemType Directory -Force -Path $outputDir|Out-Null
$output=Join-Path $outputDir ('ws-continuous-'+[guid]::NewGuid().ToString('N')+'.json')
try{
    $env:PYTHONPATH="$($cfg.tree)/src;$($cfg.tree)"
    $lastPrint=[DateTimeOffset]::MinValue
    do{
        $raw=@(& $cfg.python -B -m tools.atlas_ws_continuity report --root $root --config-pin $configPin)
        if($LASTEXITCODE){$raw|Write-Output;throw 'CONTINUOUS_REPORT_INTEGRITY_BLOCKED'}
        $r=($raw -join "`n")|ConvertFrom-Json
        if((Get-FileHash -LiteralPath $config -Algorithm SHA256).Hash.ToLowerInvariant() -cne $configPin){throw 'CONTINUOUS_CONFIG_DRIFT'}
        foreach($binding in $cfg.files){
            if((Get-FileHash -LiteralPath $binding.path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $binding.sha256){throw 'CONTINUOUS_RUNTIME_DRIFT'}
        }
        $task=Get-ScheduledTask -TaskName $taskName
        $r|Add-Member -NotePropertyName host_task_state -NotePropertyValue ([string]$task.State)
        if($r.acceptance_ready -and [string]$task.State -ceq 'Running'){
            $r.status=if(@($r.missing_open_ranges).Count){'CONTINUOUS_RESEARCH_OPERATIONAL_WITH_GAPS_OWNER_LOCAL'}else{'CONTINUOUS_RESEARCH_OPERATIONAL_OWNER_LOCAL'}
            Write-NewJson $output $r
            $r|ConvertTo-Json -Depth 15
            Write-Output ('REPORT_FILE='+$output)
            return
        }
        if($r.hold_reason -and !$r.initial_resume_pending){
            Write-NewJson $output $r
            $r|ConvertTo-Json -Depth 15
            Write-Output ('REPORT_FILE='+$output)
            return
        }
        if(([DateTimeOffset]::UtcNow-$lastPrint).TotalMinutes -ge 5){
            $r|Select-Object status,verified_receipts,confirmed_rollovers,real_fault_events,last_receipt_fresh|ConvertTo-Json -Compress
            $lastPrint=[DateTimeOffset]::UtcNow
        }
        Start-Sleep -Seconds 60
    }while([DateTimeOffset]::UtcNow -lt $deadline)
    $r.status='OBSERVATION_DEADLINE_OPERATION_NOT_ATTESTED'
    Write-NewJson $output $r
    $r|ConvertTo-Json -Depth 15
    Write-Output ('REPORT_FILE='+$output)
}finally{$env:PYTHONPATH=$oldPythonPath}
