# Read Task Scheduler and existing sanitized evidence. No market or scheduler commands that write.
param(
    [Parameter(Mandatory=$true)][string]$LiveRoot,
    [Parameter(Mandatory=$true)][string]$ConfigSha256,
    [Parameter(Mandatory=$true)][string]$Output
)
$ErrorActionPreference='Stop'
$stage=Split-Path -Parent $PSScriptRoot
$activation=Get-Content -LiteralPath "$LiveRoot/activation.json" -Raw | ConvertFrom-Json
$configFile="$LiveRoot/config.json"
if ((Get-FileHash -LiteralPath $configFile).Hash.ToLowerInvariant() -cne $ConfigSha256 -or
    $activation.config_sha256 -cne $ConfigSha256){throw 'LIVE_OPERATOR_CONFIG_PIN'}
$cfg=Get-Content -LiteralPath $configFile -Raw | ConvertFrom-Json
$task=Get-ScheduledTask -TaskName $activation.task
$info=$task | Get-ScheduledTaskInfo
$daily=Get-ScheduledTask -TaskName 'ATLAS-Research-Sustained-BTCUSDT-Daily'
$dailyInfo=$daily | Get-ScheduledTaskInfo
$xml="$LiveRoot/daily-definition-before.xml"
if ((Get-FileHash -LiteralPath $xml).Hash.ToLowerInvariant() -cne $activation.protected_daily_xml_sha256){
    throw 'LIVE_OPERATOR_DAILY_REFERENCE_PIN'
}
$supervisor=@(Get-Content -LiteralPath "$LiveRoot/supervisor.jsonl" -Tail 80 |
    ForEach-Object {$_ | ConvertFrom-Json})
$segments=@(Get-ChildItem -LiteralPath "$LiveRoot/segments" -Directory |
    Where-Object Name -match '^[0-9]{13}$' | Sort-Object Name | Select-Object -Last 3)
$transport=@()
$heartbeat=$null
foreach ($segment in $segments) {
    $log=Join-Path $segment.FullName 'health.jsonl'
    if (!(Test-Path -LiteralPath $log)){continue}
    $events=@(Get-Content -LiteralPath $log -Tail 500 | ForEach-Object {$_ | ConvertFrom-Json})
    $transport+=@($events | Where-Object status -eq 'TRANSPORT_INTERRUPTED')
    $observing=$events | Where-Object status -eq 'OBSERVING' | Select-Object -Last 1
    if ($observing){$heartbeat=$observing.utc_ms}
}
$hold=$null
if (Test-Path -LiteralPath "$LiveRoot/hold.json"){
    $hold=Get-Content -LiteralPath "$LiveRoot/hold.json" -Raw | ConvertFrom-Json
}
$receipts=@()
$originalPythonPath=$env:PYTHONPATH
try {
    $env:PYTHONPATH="$($cfg.tree)/src;$($cfg.tree)"
    Push-Location -LiteralPath $cfg.tree
    try {
        $saved=Get-ChildItem -LiteralPath "$LiveRoot/segments/receipts" -File -Filter '*.json' |
            Where-Object BaseName -match '^[0-9]{13}$' | Sort-Object Name | Select-Object -Last 16
        foreach ($receipt in $saved) {
            $row=& $cfg.python -B -m tools.atlas_live_research_cycle status --service-receipt $receipt.FullName
            if ($LASTEXITCODE){throw 'LIVE_OPERATOR_RECEIPT_READBACK'}
            $receipts+=@($row | ConvertFrom-Json)
        }
    } finally {Pop-Location}
    $snapshot=@{as_of_ms=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
        task_state=[string]$task.State;task_enabled=$task.Settings.Enabled
        writer_policy=[string]$task.Settings.MultipleInstances;last_task_result=$info.LastTaskResult
        last_heartbeat_ms=$heartbeat;supervisor=$supervisor;transport=$transport;hold=$hold
        receipts=$receipts;stop_requested=(Test-Path -LiteralPath "$LiveRoot/stop.request")
        config_sha256=$ConfigSha256
        daily=@{state=[string]$daily.State;next_run=$dailyInfo.NextRunTime.ToUniversalTime().ToString('o')
            reference_sha256=$activation.protected_daily_xml_sha256
            unchanged=((Export-ScheduledTask -TaskName $daily.TaskName).Trim() -ceq
                (Get-Content -LiteralPath $xml -Raw).Trim())}}
    $env:PYTHONPATH="$stage/src;$stage"
    Push-Location -LiteralPath $stage
    try {
        $report=($snapshot | ConvertTo-Json -Depth 20 -Compress) |
            & $cfg.python -B -m tools.atlas_operator_report --live-windows-saved
        if ($LASTEXITCODE){throw 'LIVE_OPERATOR_FACTORY_PROJECTION'}
    } finally {Pop-Location}
    $stream=[IO.File]::Open($Output,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write)
    try {
        $bytes=[Text.Encoding]::UTF8.GetBytes([string]$report)
        $stream.Write($bytes,0,$bytes.Length)
        $stream.Flush($true)
    } finally {$stream.Dispose()}
    ($report | ConvertFrom-Json).sha256
} finally {$env:PYTHONPATH=$originalPythonPath}
