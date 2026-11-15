param(
    [ValidateSet('install','start','status','stop','rearm','recover','tick','remove')][string]$Mode,
    [Parameter(Mandatory=$true)][string]$Config,
    [string]$Python, [string]$State, [string]$TaskName,
    [string]$AuthorizedPlan, [string]$AuthorizedPlanSha256,
    [ValidateRange(1,60)][int]$IntervalMinutes = 1,
    [ValidateRange(2,60)][int]$Ticks = 2
)
$ErrorActionPreference = 'Stop'
$Config = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Config)

function Invoke-Cycle {
    param($Settings, [string[]]$Arguments)
    $previous = $env:PYTHONPATH
    $env:PYTHONPATH = "$($Settings.tree)/src;$($Settings.tree)"
    Push-Location -LiteralPath $Settings.tree
    try {
        if ($Settings.authorized_plan) {
            $Arguments += @('--authorized-plan',$Settings.authorized_plan,
                            '--authorized-plan-sha256',$Settings.pin)
        }
        & $Settings.python -B -m tools.atlas_recurring_research @Arguments
    }
    finally { Pop-Location; $env:PYTHONPATH = $previous }
}

if ($Mode -eq 'install') {
    if ($TaskName -notmatch '^ATLAS-Research-[A-Za-z0-9-]+$' -or !$Python -or !$State) {
        throw 'TASK_NAME_PYTHON_AND_STATE_REQUIRED'
    }
    if ((Test-Path -LiteralPath $Config) -or (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)) {
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
    if ($AuthorizedPlan) {
        if ($AuthorizedPlanSha256 -cnotmatch '^[0-9a-f]{64}$') { throw 'AUTHORIZED_PLAN_PIN_REQUIRED' }
        $AuthorizedPlan = (Resolve-Path -LiteralPath $AuthorizedPlan).Path
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
    $first = (Get-Date).AddSeconds(35)
    $duration = New-TimeSpan -Minutes ($IntervalMinutes * ($Ticks - 1)) -Seconds 15
    $settings = [ordered]@{
        python = $Python; tree = $tree; state = $State; task = $TaskName
        log = Join-Path $stage 'ticks.jsonl'
        deadline_ms = ([DateTimeOffset]$first.Add($duration).AddSeconds(10)).ToUnixTimeMilliseconds()
        pin = $AuthorizedPlanSha256
        authorized_plan = $AuthorizedPlan
    }
    if ($AuthorizedPlan) {
        $null = Invoke-Cycle $settings @('status','--state',$State)
        if ($LASTEXITCODE) { throw 'AUTHORIZED_PLAN_PREFLIGHT_FAILED' }
    } else {
        $plan = Invoke-Cycle $settings @('plan') | ConvertFrom-Json
        if ($LASTEXITCODE) { throw 'PLAN_FAILED' }
        $settings.pin = $plan.sha256
    }
    $settings | ConvertTo-Json | Set-Content -LiteralPath $Config -Encoding utf8
    $engine = (Get-Process -Id $PID).Path
    $action = New-ScheduledTaskAction -Execute $engine -Argument (
        '-NoProfile -NonInteractive -File "{0}" -Mode tick -Config "{1}"' -f $launcher,$Config
    )
    $trigger = New-ScheduledTaskTrigger -Once -At $first -RepetitionInterval (
        New-TimeSpan -Minutes $IntervalMinutes) -RepetitionDuration $duration
    $policy = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
    $user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $policy -Principal $principal | Out-Null
    [pscustomobject]@{task=$TaskName; first=$first; pin=$settings.pin; log=$settings.log} | ConvertTo-Json
    return
}

$settings = Get-Content -LiteralPath $Config -Raw | ConvertFrom-Json
switch ($Mode) {
    'start' { Start-ScheduledTask -TaskName $settings.task }
    'remove' { Unregister-ScheduledTask -TaskName $settings.task -Confirm:$false }
    'tick' {
        if ([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() -gt $settings.deadline_ms) { return }
        $result = Invoke-Cycle $settings @('recover','--state',$settings.state,'--pin',$settings.pin)
        $exitCode = $LASTEXITCODE
        $record = [ordered]@{ utc = [DateTimeOffset]::UtcNow.ToString('o'); exit_code = $exitCode }
        if ($exitCode -eq 0) {
            $readback = $result | ConvertFrom-Json
            $record.status = $readback.status
            if ($readback.reason) { $record.reason = $readback.reason }
            $record.receipts = @($readback.windows | ForEach-Object { if ($_.receipt) { $_.receipt.sha256 } })
        }
        $record | ConvertTo-Json -Compress | Add-Content -LiteralPath $settings.log -Encoding utf8
        exit $exitCode
    }
    default {
        $arguments = @($Mode,'--state',$settings.state)
        if ($Mode -eq 'recover') { $arguments += @('--pin',$settings.pin) }
        Invoke-Cycle $settings $arguments
        exit $LASTEXITCODE
    }
}
