# Owner-authorized PONG recovery deployment. Run under the Windows task account.
$ErrorActionPreference='Stop'
$name='ATLAS-Research-Sustained-Spot-WS'
$expectedOld='ac2f74c0a4d0fc93200e871bb244ec40ffc199a5c4fe64fc922819551f9c3aec'
$expectedNew='2e675cf610555e6d5b7145d62c278c1fe7efdb175570ed10ef759b958b8b9faa'
$task=@(Get-ScheduledTask -TaskName $name)
if($task.Count -ne 1 -or @($task[0].Actions).Count -ne 1){throw 'TASK_NOT_UNIQUE'}
$task=$task[0]
$oldAction=$task.Actions[0]
$match=[regex]::Match($oldAction.Arguments,'(?i)(?:^|\s)-Config\s+(?:"([^"]+)"|''([^'']+)''|(\S+))')
$pin=[regex]::Match($oldAction.Arguments,'(?i)(?:^|\s)-ConfigSha256\s+["'']?([a-f0-9]{64})(?=["''\s]|$)')
if(-not ($match.Success -and $pin.Success)){throw 'TASK_CONFIG_ARGUMENTS'}
$config=[Environment]::ExpandEnvironmentVariables(($match.Groups[1].Value+$match.Groups[2].Value+$match.Groups[3].Value))
if((Get-FileHash -LiteralPath $config -Algorithm SHA256).Hash -ine $pin.Groups[1].Value){throw 'CONFIG_PIN_MISMATCH'}
$cfg=Get-Content -LiteralPath $config -Raw | ConvertFrom-Json
$root=Split-Path -Parent $config
$holdPath=Join-Path $root 'hold.json'
$cycle=Join-Path $cfg.tree 'tools/atlas_live_research_cycle.py'
$source=Join-Path $PSScriptRoot 'atlas_live_research_cycle.py'
if((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ine $expectedNew){throw 'NEW_CYCLE_HASH_MISMATCH'}
$entry=@($cfg.files | Where-Object {[IO.Path]::GetFullPath($_.path) -ieq [IO.Path]::GetFullPath($cycle)})
if($entry.Count -ne 1 -or $entry[0].sha256 -ine $expectedOld -or
   (Get-FileHash -LiteralPath $cycle -Algorithm SHA256).Hash -ine $expectedOld){throw 'CURRENT_CYCLE_PIN_MISMATCH'}
foreach($item in $cfg.files){
    if((Get-FileHash -LiteralPath $item.path -Algorithm SHA256).Hash -ine $item.sha256){throw 'RUNTIME_PIN_MISMATCH'}
}
if(Test-Path -LiteralPath (Join-Path $root 'stop.request')){throw 'OPERATOR_STOP_PRESENT'}
if((Test-Path -LiteralPath (Join-Path $root 'reset-recovery.pending')) -or
   (Test-Path -LiteralPath (Join-Path $root 'reset-recovery.claimed'))){throw 'RECOVERY_STATE_REQUIRES_REVIEW'}
$hold=Get-Content -LiteralPath $holdPath -Raw | ConvertFrom-Json
if($hold.reason -cne 'PILOT_STOP_PONG_QUOTA_STOP' -or [long]$hold.slot_ms -ne 1794929400000){throw 'HOLD_CHANGED'}
$lock=[IO.File]::Open((Join-Path $root 'supervisor.lock'),'OpenOrCreate','ReadWrite','None')
try {
    $current=Get-ScheduledTask -TaskName $name -TaskPath $task.TaskPath
    if(-not $current.Settings.Enabled -or $current.Actions[0].Arguments -cne $oldAction.Arguments){throw 'TASK_CHANGED'}
    $backup=Join-Path $root ('pong-backup-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ'))
    New-Item -ItemType Directory -Path $backup | Out-Null
    Copy-Item -LiteralPath $cycle -Destination (Join-Path $backup 'cycle.py')
    Copy-Item -LiteralPath $config -Destination (Join-Path $backup 'config.json')
    Copy-Item -LiteralPath $holdPath -Destination (Join-Path $backup 'hold.json')
    Export-ScheduledTask -TaskName $name -TaskPath $task.TaskPath | Set-Content -LiteralPath (Join-Path $backup 'task.xml') -Encoding Unicode
    $activation=Join-Path $root 'activation.json'
    $hasActivation=Test-Path -LiteralPath $activation
    if($hasActivation){
        $active=Get-Content -LiteralPath $activation -Raw | ConvertFrom-Json
        if($active.config_sha256 -ine $pin.Groups[1].Value){throw 'ACTIVATION_PIN_MISMATCH'}
        Copy-Item -LiteralPath $activation -Destination (Join-Path $backup 'activation.json')
    }
    try {
        Copy-Item -LiteralPath $source -Destination $cycle -Force
        $entry[0].sha256=$expectedNew
        [IO.File]::WriteAllText($config,($cfg | ConvertTo-Json -Depth 100),[Text.UTF8Encoding]::new($false))
        $newPin=(Get-FileHash -LiteralPath $config -Algorithm SHA256).Hash.ToLowerInvariant()
        if($hasActivation){
            $active.config_sha256=$newPin
            [IO.File]::WriteAllText($activation,($active | ConvertTo-Json -Depth 100),[Text.UTF8Encoding]::new($false))
        }
        $argsNew=$oldAction.Arguments.Remove($pin.Groups[1].Index,64).Insert($pin.Groups[1].Index,$newPin)
        $params=@{Execute=$oldAction.Execute;Argument=$argsNew}
        if($oldAction.WorkingDirectory){$params.WorkingDirectory=$oldAction.WorkingDirectory}
        Set-ScheduledTask -TaskName $name -TaskPath $task.TaskPath -Action (New-ScheduledTaskAction @params) | Out-Null
        $readback=Get-ScheduledTask -TaskName $name -TaskPath $task.TaskPath
        if($readback.Actions[0].Arguments -cne $argsNew -or
           (Get-FileHash -LiteralPath $cycle -Algorithm SHA256).Hash -ine $expectedNew){throw 'INSTALL_READBACK_FAILED'}
    } catch {
        Copy-Item -LiteralPath (Join-Path $backup 'cycle.py') -Destination $cycle -Force
        Copy-Item -LiteralPath (Join-Path $backup 'config.json') -Destination $config -Force
        if($hasActivation){Copy-Item -LiteralPath (Join-Path $backup 'activation.json') -Destination $activation -Force}
        Set-ScheduledTask -TaskName $name -TaskPath $task.TaskPath -Action $oldAction | Out-Null
        throw
    }
    Rename-Item -LiteralPath $holdPath -NewName ('hold.pong-archived-'+[guid]::NewGuid().ToString('N')+'.json')
    $receipt=[ordered]@{status='PONG_FIX_INSTALLED_WAITING_FOR_SCHEDULED_RUN';utc=[DateTimeOffset]::UtcNow.ToString('o');cycle_sha256=$expectedNew;config_sha256=$newPin}
    [IO.File]::WriteAllText((Join-Path $backup 'installation.json'),($receipt | ConvertTo-Json),[Text.UTF8Encoding]::new($false))
    $receipt | ConvertTo-Json -Compress
} finally {$lock.Dispose()}
