# Pinned supervisor-only deployment under the existing writer lock.
$ErrorActionPreference='Stop'
$name='ATLAS-Research-Sustained-Spot-WS'
$task=@(Get-ScheduledTask -TaskName $name)
if($task.Count -ne 1 -or @($task[0].Actions).Count -ne 1){throw 'TASK_NOT_UNIQUE'}
$task=$task[0]; $old=$task.Actions[0]
$pattern='(?:"([^"]+)"|''([^'']+)''|(\S+))'
$file=[regex]::Match($old.Arguments,"(?i)(?:^|\s)-File\s+$pattern")
$conf=[regex]::Match($old.Arguments,"(?i)(?:^|\s)-Config\s+$pattern")
$pin=[regex]::Match($old.Arguments,'(?i)(?:^|\s)-ConfigSha256\s+["'']?([a-f0-9]{64})(?=["''\s]|$)')
if(-not ($file.Success -and $conf.Success -and $pin.Success)){throw 'TASK_ARGUMENTS_UNEXPECTED'}
$oldFile=[Environment]::ExpandEnvironmentVariables(($file.Groups[1].Value+$file.Groups[2].Value+$file.Groups[3].Value))
$config=[Environment]::ExpandEnvironmentVariables(($conf.Groups[1].Value+$conf.Groups[2].Value+$conf.Groups[3].Value))
if((Get-FileHash -LiteralPath $oldFile).Hash -ine '562f0602038b8a54e7f9e3295b4cebc548b0b1314ffcc066ec610cb892a6801a'){throw 'SUPERVISOR_PIN_MISMATCH'}
if((Get-FileHash -LiteralPath $config).Hash -ine $pin.Groups[1].Value){throw 'CONFIG_PIN_MISMATCH'}
$cfg=Get-Content -LiteralPath $config -Raw | ConvertFrom-Json
foreach($entry in $cfg.files){if((Get-FileHash -LiteralPath $entry.path).Hash -ine $entry.sha256){throw 'RUNTIME_PIN_MISMATCH'}}
$root=Split-Path -Parent $config
$holdPath=Join-Path $root 'hold.json'
$hold=Get-Content -LiteralPath $holdPath -Raw | ConvertFrom-Json
if($hold.reason -cne 'PILOT_STOP_ConnectionResetError' -or [long]$hold.slot_ms -ne 1794981600000){throw 'HOLD_CHANGED'}
foreach($marker in @('stop.request','reset-recovery.pending','reset-recovery.claimed')){
    if(Test-Path -LiteralPath (Join-Path $root $marker)){throw 'STOP_OR_RECOVERY_STATE_PRESENT'}
}
$source=Join-Path $PSScriptRoot 'atlas_live_research_service_windows.ps1'
$newHash='51f130f6e49a5ccbbbe80f9bad7475d2d0d4f10e1711beff0a196bb462d00785'
if((Get-FileHash -LiteralPath $source).Hash -ine $newHash){throw 'NEW_SUPERVISOR_PIN_MISMATCH'}
$lock=[IO.File]::Open((Join-Path $root 'supervisor.lock'),'OpenOrCreate','ReadWrite','None')
try {
    $current=Get-ScheduledTask -TaskName $name -TaskPath $task.TaskPath
    if(-not $current.Settings.Enabled -or $current.Actions[0].Arguments -cne $old.Arguments){throw 'TASK_CHANGED'}
    $stage=Join-Path $root ('mixed-recovery-'+[guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $stage | Out-Null
    Export-ScheduledTask -TaskName $name -TaskPath $task.TaskPath | Set-Content -LiteralPath (Join-Path $stage 'task-before.xml') -Encoding Unicode
    Copy-Item -LiteralPath $holdPath -Destination (Join-Path $stage 'hold-before.json')
    $newFile=Join-Path $stage 'supervisor.ps1'
    Copy-Item -LiteralPath $source -Destination $newFile
    $argsNew=$old.Arguments.Remove($file.Index,$file.Length).Insert($file.Index,(' -File "'+$newFile+'"'))
    $params=@{Execute=$old.Execute;Argument=$argsNew}
    if($old.WorkingDirectory){$params.WorkingDirectory=$old.WorkingDirectory}
    try {
        Set-ScheduledTask -TaskName $name -TaskPath $task.TaskPath -Action (New-ScheduledTaskAction @params) | Out-Null
        $readback=Get-ScheduledTask -TaskName $name -TaskPath $task.TaskPath
        if($readback.Actions[0].Arguments -cne $argsNew){throw 'TASK_READBACK_FAILED'}
        Rename-Item -LiteralPath $holdPath -NewName ('hold.mixed-archived-'+[guid]::NewGuid().ToString('N')+'.json')
    } catch {
        Set-ScheduledTask -TaskName $name -TaskPath $task.TaskPath -Action $old | Out-Null
        throw
    }
    [ordered]@{status='MIXED_RECOVERY_INSTALLED_WAITING_FOR_SCHEDULED_RUN';utc=[DateTimeOffset]::UtcNow.ToString('o');supervisor_sha256=$newHash} | ConvertTo-Json -Compress
} finally {$lock.Dispose()}
