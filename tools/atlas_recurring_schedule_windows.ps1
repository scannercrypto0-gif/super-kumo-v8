param(
    [ValidateSet('prepare','install','start','status','health','stop','rearm','recover','tick','enable','disable','remove')][string]$Mode,
    [Parameter(Mandatory=$true)][string]$Config,
    [string]$Python, [string]$State, [string]$TaskName,
    [string]$AuthorizedPlan, [string]$AuthorizedPlanSha256,
    [string]$DailyPolicy, [string]$DailyPolicySha256,
    [ValidateRange(1,60)][int]$IntervalMinutes = 1,
    [ValidateRange(2,60)][int]$Ticks = 2,
    [switch]$InstallDisabled
)
$ErrorActionPreference = 'Stop'
$Config = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Config)

function Invoke-Cycle {
    param($Settings, [string[]]$Arguments)
    $previous = $env:PYTHONPATH
    $env:PYTHONPATH = "$($Settings.tree)/src;$($Settings.tree)"
    Push-Location -LiteralPath $Settings.tree
    try {
        if ($Settings.daily_policy) {
            $mode = switch ($Arguments[0]) { 'recover' { 'tick' } default { $Arguments[0] } }
            & $Settings.python -B -m tools.atlas_vision_daily $mode --state $Settings.state `
                --policy $Settings.daily_policy --pin $Settings.pin
            return
        }
        if ($Settings.authorized_plan) {
            $Arguments += @('--authorized-plan',$Settings.authorized_plan,
                            '--authorized-plan-sha256',$Settings.pin)
        }
        & $Settings.python -B -m tools.atlas_recurring_research @Arguments
    }
    finally { Pop-Location; $env:PYTHONPATH = $previous }
}

function Test-Runtime {
    param($Settings)
    if ($Settings.runtime_pin_version -ne 2 -or !$Settings.runtime) {
        throw 'RUNTIME_PIN_MISMATCH'
    }
    foreach ($item in $Settings.runtime) {
        if (!(Test-Path -LiteralPath $item.path -PathType Leaf) -or
            (Get-FileHash -LiteralPath $item.path).Hash -cne $item.sha256) {
            throw 'RUNTIME_PIN_MISMATCH'
        }
    }
}

function Read-TickHealth {
    param($Settings, [long]$NowMs)
    $latest = $null
    $lastSuccess = $null
    $lastFailure = $null
    $ageMs = $null
    $invalid = $false
    if (Test-Path -LiteralPath $Settings.log -PathType Leaf) {
        foreach ($line in (Get-Content -LiteralPath $Settings.log -Tail 64)) {
            try {
                $row = $line | ConvertFrom-Json -ErrorAction Stop
                if (!$row.utc) { throw 'INVALID_TICK' }
                $stamp = if ($row.utc -is [DateTime]) { ([DateTimeOffset]$row.utc).ToUnixTimeMilliseconds() }
                         else { [DateTimeOffset]::Parse([string]$row.utc).ToUnixTimeMilliseconds() }
                if ($stamp -gt $NowMs -or $null -eq $row.exit_code -or !$row.status) { throw 'INVALID_TICK' }
                $latest = $row
                $ageMs = $NowMs - $stamp
                $invalid = $false
                if ($row.exit_code -eq 0 -and $row.status -eq 'COMPLETE' -and
                    @($row.receipts | Where-Object { $_ -cmatch '^[0-9a-f]{64}$' }).Count -gt 0) {
                    $lastSuccess = $row
                }
                if ($row.exit_code -ne 0) { $lastFailure = $row }
            } catch {
                $invalid = $true
            }
        }
    }
    $cadenceMs = if ($Settings.daily_policy) { 86400000L } else { [long]$Settings.interval_minutes * 60000 }
    $cycle = if ($invalid) { 'LOG_UNREADABLE' }
             elseif (!$latest) { 'NO_TICK_EVIDENCE' }
             elseif ($latest.exit_code -ne 0) { 'LAST_TICK_FAILED' }
             elseif ($cadenceMs -le 0) { 'CADENCE_UNVERIFIED' }
             elseif ($ageMs -gt $cadenceMs + 30000) { 'LAST_TICK_STALE' }
             elseif ($latest.status -eq 'WAIT_FOR_SOURCE') { 'WAIT_FOR_SOURCE' }
             elseif ($latest.status -ne 'COMPLETE') { 'LAST_TICK_INCOMPLETE' }
             elseif ($lastSuccess -ne $latest) { 'LAST_TICK_RECEIPT_MISSING' }
             else { 'RECENT_RESEARCH_RECEIPT' }
    [ordered]@{cycle_evidence=$cycle; tick_age_ms=$ageMs; latest=$latest; last_success=$lastSuccess
               last_failure=$lastFailure; freshness_limit_ms=if ($cadenceMs -gt 0) {$cadenceMs + 30000}}
}

if ($Mode -in 'prepare','install') {
    if ($TaskName -notmatch '^ATLAS-Research-[A-Za-z0-9-]+$' -or !$Python -or !$State) {
        throw 'TASK_NAME_PYTHON_AND_STATE_REQUIRED'
    }
    if ($Mode -eq 'prepare' -and ($AuthorizedPlan -or $DailyPolicy)) { throw 'PREPARE_TEST_ONLY' }
    if ($DailyPolicy -and ($AuthorizedPlan -or $DailyPolicySha256 -cnotmatch '^[0-9a-f]{64}$')) {
        throw 'DAILY_POLICY_SCOPE_PIN_REQUIRED'
    }
    if ($DailyPolicy -and [TimeZoneInfo]::Local.SupportsDaylightSavingTime) {
        throw 'DAILY_UTC_SCHEDULE_REQUIRES_FIXED_LOCAL_OFFSET'
    }
    if ((Test-Path -LiteralPath $Config) -or
        ($Mode -eq 'install' -and (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue))) {
        throw 'EXISTING_TASK_OR_CONFIG'
    }
    $Python = (Resolve-Path -LiteralPath $Python).Path
    $State = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($State)
    $repo = Split-Path -Parent $PSScriptRoot
    $stage = Join-Path (Split-Path -Parent $Config) ($TaskName + '-runtime')
    $null = New-Item -ItemType Directory -Path $stage
    $tree = Join-Path $stage 'tree'
    $zip = Join-Path $stage 'core.zip'
    git -C $repo archive --format=zip "--output=$zip" d072544427d6b08473c88b2e36d5857cfd8581dc
    if ($LASTEXITCODE) { throw 'PINNED_286_REQUIRED' }
    Expand-Archive -LiteralPath $zip -DestinationPath $tree
    foreach ($file in 'atlas_bounded_research_cycle.py','atlas_recurring_research.py') {
        Copy-Item "$repo/tools/$file" "$tree/tools"
    }
    if ($AuthorizedPlan -or $DailyPolicy) {
        if ($AuthorizedPlan) {
            if ($AuthorizedPlanSha256 -cnotmatch '^[0-9a-f]{64}$') { throw 'AUTHORIZED_PLAN_PIN_REQUIRED' }
            $AuthorizedPlan = (Resolve-Path -LiteralPath $AuthorizedPlan).Path
        }
        $dependencies = @(
            @{sha='d0782682eba2cf842ec00b75fa85a273c76323be'; path='research_wp_r0/aql_native_binance_zip_v1.py'},
            @{sha='e0e08a8381a8cceaaa44d6ae2721e9cb0d004648'; path='tools/historical_source_qa'},
            @{sha='831fe426ea55f6b30fbbb86ddfe01a7ed194eba2'; path='research_wp_r0/aql_factory_e_research_results_store_v1.py'}
        )
        foreach ($dependency in $dependencies) {
            $bundle = Join-Path $stage ($dependency.sha + '.zip')
            git -C $repo archive --format=zip "--output=$bundle" $dependency.sha $dependency.path
            if ($LASTEXITCODE) { throw 'PINNED_ARCHIVE_DEPENDENCY_REQUIRED' }
            Expand-Archive -LiteralPath $bundle -DestinationPath $tree -Force
        }
        Copy-Item "$repo/tools/atlas_authorized_archive_research.py" "$tree/tools"
    }
    $launcher = Join-Path $stage 'schedule.ps1'
    Copy-Item -LiteralPath $PSCommandPath -Destination $launcher
    $runtime = @($launcher, $Python, "$tree/tools/atlas_recurring_research.py",
                 "$tree/tools/atlas_bounded_research_cycle.py",
                 "$tree/tools/atlas_prospective_observe.py",
                 "$tree/tools/atlas_april_archive.py",
                 "$tree/tools/strategy_service_offline/fixtures/strategies.json",
                 "$tree/research_wp_r0/aql_factory_prospective_read_v1.py")
    $runtime += @(Get-ChildItem -LiteralPath "$tree/src/aql" -Recurse -File -Filter '*.py' |
                  Select-Object -ExpandProperty FullName)
    if ($AuthorizedPlan -or $DailyPolicy) {
        $runtime += @("$tree/tools/atlas_authorized_archive_research.py",
                      "$tree/tools/historical_source_qa/qa.py",
                      "$tree/research_wp_r0/aql_native_binance_zip_v1.py",
                      "$tree/research_wp_r0/aql_factory_e_research_results_store_v1.py")
    }
    if ($DailyPolicy) {
        $DailyPolicy = (Resolve-Path -LiteralPath $DailyPolicy).Path
        $opening = [DateTimeOffset]::FromUnixTimeMilliseconds(
            (Get-Content -LiteralPath $DailyPolicy -Raw | ConvertFrom-Json).first_open_ms)
        Copy-Item "$repo/tools/atlas_vision_daily.py" "$tree/tools"
        $runtime += @("$tree/tools/atlas_vision_daily.py", $DailyPolicy)
    }
    $first = (Get-Date).AddSeconds(35)
    $duration = New-TimeSpan -Minutes ($IntervalMinutes * ($Ticks - 1)) -Seconds 15
    $settings = [ordered]@{
        python = $Python; tree = $tree; state = $State; task = $TaskName
        log = Join-Path $stage 'ticks.jsonl'
        interval_minutes = $IntervalMinutes
        deadline_ms = ([DateTimeOffset]$first.Add($duration).AddSeconds(10)).ToUnixTimeMilliseconds()
        pin = if ($DailyPolicy) {$DailyPolicySha256} else {$AuthorizedPlanSha256}
        authorized_plan = $AuthorizedPlan
        daily_policy = $DailyPolicy
        daily_first_check_ms = if ($DailyPolicy) {$opening.AddDays(1).AddHours(6).ToUnixTimeMilliseconds()}
        prepared_only = ($Mode -eq 'prepare')
        runtime_pin_version = 2
        runtime = @($runtime | ForEach-Object { @{path=$_;sha256=(Get-FileHash -LiteralPath $_).Hash} })
    }
    if ($DailyPolicy) {
        $null = Invoke-Cycle $settings @('preflight')
        if ($LASTEXITCODE) { throw 'DAILY_POLICY_PREFLIGHT_FAILED' }
    } elseif ($AuthorizedPlan) {
        $null = Invoke-Cycle $settings @('status','--state',$State)
        if ($LASTEXITCODE) { throw 'AUTHORIZED_PLAN_PREFLIGHT_FAILED' }
    } else {
        $plan = Invoke-Cycle $settings @('plan') | ConvertFrom-Json
        if ($LASTEXITCODE) { throw 'PLAN_FAILED' }
        $settings.pin = $plan.sha256
    }
    $settings | ConvertTo-Json | Set-Content -LiteralPath $Config -Encoding utf8
    if ($Mode -eq 'prepare') {
        [pscustomobject]@{status='PREPARED_TEST_ONLY'; pin=$settings.pin; log=$settings.log} | ConvertTo-Json
        return
    }
    $engine = (Get-Process -Id $PID).Path
    $action = New-ScheduledTaskAction -Execute $engine -Argument (
        '-NoProfile -NonInteractive -File "{0}" -Mode tick -Config "{1}"' -f $launcher,$Config
    )
    $trigger = if ($DailyPolicy) {
        foreach ($hour in 6,12) {
            New-ScheduledTaskTrigger -Daily -At $opening.AddDays(1).AddHours($hour).LocalDateTime
        }
    } else {
        New-ScheduledTaskTrigger -Once -At $first -RepetitionInterval (
            New-TimeSpan -Minutes $IntervalMinutes) -RepetitionDuration $duration
    }
    $policy = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
    $user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $policy -Principal $principal | Out-Null
    if ($InstallDisabled) { Disable-ScheduledTask -TaskName $TaskName | Out-Null }
    [pscustomobject]@{task=$TaskName; first=if ($DailyPolicy) {$opening.AddDays(1).AddHours(6)} else {$first}
                      pin=$settings.pin; log=$settings.log} | ConvertTo-Json
    return
}

$settings = Get-Content -LiteralPath $Config -Raw | ConvertFrom-Json
if ($settings.prepared_only -and $Mode -in 'start','enable','disable','remove') {
    throw 'PREPARED_CONFIG_HAS_NO_TASK'
}
switch ($Mode) {
    'start' {
        if (!$settings.daily_policy -and [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() -gt $settings.deadline_ms) { throw 'SCHEDULE_EXPIRED' }
        Test-Runtime $settings
        Start-ScheduledTask -TaskName $settings.task
    }
    'enable' {
        if (!$settings.daily_policy -and [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() -gt $settings.deadline_ms) { throw 'SCHEDULE_EXPIRED' }
        Test-Runtime $settings
        Enable-ScheduledTask -TaskName $settings.task | Out-Null
    }
    'disable' { Disable-ScheduledTask -TaskName $settings.task | Out-Null }
    'health' {
        $task = if (!$settings.prepared_only) {
            Get-ScheduledTask -TaskName $settings.task -ErrorAction SilentlyContinue
        }
        $info = if ($task) { $task | Get-ScheduledTaskInfo }
        $nowMs = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
        $evidence = Read-TickHealth $settings $nowMs
        $runtimeState = 'PIN_VERIFIED'
        try { Test-Runtime $settings } catch { $runtimeState = 'RUNTIME_PIN_MISMATCH' }
        $schedulerState = if ($settings.prepared_only) { 'NOT_REGISTERED' }
                          elseif (!$task) { 'REMOVED' }
                          elseif (!$settings.daily_policy -and $nowMs -gt $settings.deadline_ms) { 'EXPIRED' }
                          else { [string]$task.State }
        $view = [ordered]@{schema='aql.recurring-runtime.health.v1'; observed_at_ms=$nowMs
                   task=$settings.task; task_state=if ($task) {[string]$task.State} else {'REMOVED'}
                   source_mode=if ($settings.authorized_plan -or $settings.daily_policy) {'AUTHORIZED_RETAINED_ARCHIVE'} else {'TEST_ONLY'}
                   last_task_result=$info.LastTaskResult; missed_runs=$info.NumberOfMissedRuns
                   deadline_ms=if (!$settings.daily_policy) {$settings.deadline_ms}; scheduler_state=$schedulerState
                   runtime_state=$runtimeState; cycle_evidence=$evidence.cycle_evidence
                   tick_age_ms=$evidence.tick_age_ms; latest=$evidence.latest
                   freshness_limit_ms=$evidence.freshness_limit_ms
                   last_success=$evidence.last_success; last_failure=$evidence.last_failure
                   market_feed_health='NOT_MEASURED'
                   current_entry='NO_CURRENT_ENTRY'; trading_authority='NONE'}
        if ($settings.daily_policy) {
            $view.source_cadence = 'DAILY_UTC'
            $view.next_check_ms = if ($info.NextRunTime) { ([DateTimeOffset]$info.NextRunTime).ToUnixTimeMilliseconds() }
                                  elseif ($evidence.latest.next_check_ms) { $evidence.latest.next_check_ms }
            if ($task -and $task.State -ne 'Disabled' -and !$evidence.latest -and
                $runtimeState -eq 'PIN_VERIFIED' -and $nowMs -lt $settings.daily_first_check_ms) {
                $view.cycle_evidence = 'WAIT_FOR_SOURCE'
            }
            $today = $nowMs - ($nowMs % 86400000L)
            $latestDue = $today - 86400000L
            if (($nowMs - $today) -lt 21600000L) { $latestDue -= 86400000L }
            $view.source_freshness = if (!$evidence.last_success) {'NOT_AVAILABLE'}
                                     elseif ($evidence.last_success.source_day_ms -lt $latestDue) {'STALE'}
                                     else {'LATEST_DUE_DAY_RECEIVED'}
        }
        $view | ConvertTo-Json -Depth 8
    }
    'remove' { Unregister-ScheduledTask -TaskName $settings.task -Confirm:$false }
    'tick' {
        if (!$settings.daily_policy -and [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() -gt $settings.deadline_ms) { return }
        $record = [ordered]@{ utc = [DateTimeOffset]::UtcNow.ToString('o'); exit_code = 1; status = 'FAILED' }
        try {
            Test-Runtime $settings
            $result = Invoke-Cycle $settings @('recover','--state',$settings.state,'--pin',$settings.pin)
            $record.exit_code = $LASTEXITCODE
            if ($record.exit_code -eq 0 -or ($settings.daily_policy -and $result)) {
                $readback = $result | ConvertFrom-Json
                $record.status = $readback.status
                if ($readback.reason) { $record.reason = $readback.reason }
                if ($settings.daily_policy) {
                    $record.source_day_ms = $readback.source_day_ms
                    $record.next_check_ms = $readback.next_check_ms
                }
                $record.receipts = @($readback.windows | ForEach-Object { if ($_.receipt) { $_.receipt.sha256 } })
            } else {
                $record.reason = 'CYCLE_EXIT_NONZERO'
            }
        } catch {
            $record.exit_code = 1
            $record.reason = if ($_.Exception.Message -eq 'RUNTIME_PIN_MISMATCH') {
                'RUNTIME_PIN_MISMATCH'
            } else { 'LOCAL_INVOCATION_FAILED' }
        }
        $record | ConvertTo-Json -Compress | Add-Content -LiteralPath $settings.log -Encoding utf8
        exit $record.exit_code
    }
    default {
        Test-Runtime $settings
        $arguments = @($Mode,'--state',$settings.state)
        if ($Mode -eq 'recover') { $arguments += @('--pin',$settings.pin) }
        Invoke-Cycle $settings $arguments
        exit $LASTEXITCODE
    }
}
