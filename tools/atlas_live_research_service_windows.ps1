param(
    [Parameter(Mandatory=$true)][string]$Config,
    [Parameter(Mandatory=$true)][string]$ConfigSha256
)
$ErrorActionPreference='Stop'
$PSNativeCommandUseErrorActionPreference=$false
if ((Get-FileHash -LiteralPath $Config).Hash.ToLowerInvariant() -cne $ConfigSha256) {
    throw 'LIVE_SERVICE_CONFIG_PIN'
}
$cfg=Get-Content -LiteralPath $Config -Raw | ConvertFrom-Json
$root=Split-Path -Parent $Config
$segments=Join-Path $root 'segments'
$hold=Join-Path $root 'hold.json'
$stop=Join-Path $root 'stop.request'
$log=Join-Path $root 'supervisor.jsonl'
$pending=Join-Path $root 'reset-recovery.pending'
$claimed=Join-Path $root 'reset-recovery.claimed'

function Record([string]$status, [string]$reason, [long]$slot) {
    [ordered]@{utc=[DateTimeOffset]::UtcNow.ToString('o');status=$status;reason=$reason;slot_ms=$slot} |
        ConvertTo-Json -Compress | Add-Content -LiteralPath $log -Encoding utf8
}

function Test-ResetRecovery([string]$HealthLog, [string]$Reason) {
    switch -CaseSensitive ($Reason) {
        'PILOT_STOP_ConnectionResetError' {$errorType='ConnectionResetError'; $origin='CONNECTION_RESET'}
        'PILOT_STOP_TimeoutError' {$errorType='TimeoutError'; $origin='UNDERLYING_RECEIVE_TIMEOUT'}
        default {return $false}
    }
    $allowed=@('ConnectionResetError/CONNECTION_RESET',
        'TimeoutError/UNDERLYING_RECEIVE_TIMEOUT','TimeoutError/PONG_LIVENESS_EXPIRED')
    try {
        $events=@(Get-Content -LiteralPath $HealthLog | ForEach-Object {$_ | ConvertFrom-Json} |
            Where-Object status -in @('CONNECTING','TRANSPORT_INTERRUPTED','STOPPED_ERROR'))
        return ($events.Count -eq 5 -and
            $events[0].status -ceq 'CONNECTING' -and $events[0].attempt -eq 1 -and
            $events[1].status -ceq 'TRANSPORT_INTERRUPTED' -and
            $allowed -ccontains ($events[1].error+'/'+$events[1].deadline_origin) -and
            $events[1].receive_phase -ceq 'FRAME_BOUNDARY' -and
            $events[2].status -ceq 'CONNECTING' -and $events[2].attempt -eq 2 -and
            $events[3].status -ceq 'TRANSPORT_INTERRUPTED' -and
            $events[3].error -ceq $errorType -and
            $allowed -ccontains ($events[3].error+'/'+$events[3].deadline_origin) -and
            $events[3].receive_phase -ceq 'FRAME_BOUNDARY' -and
            $events[4].status -ceq 'STOPPED_ERROR' -and $events[4].error -ceq $errorType)
    } catch {return $false}
}

if ((Test-Path -LiteralPath $hold) -or (Test-Path -LiteralPath $stop)) {return}
$lockPath=Join-Path $root 'supervisor.lock'
try { $lock=[IO.File]::Open($lockPath,'OpenOrCreate','ReadWrite','None') }
catch [IO.IOException] { return }
$slot=0
$route='Ethernet'
$recovery=$null
$segmentFailure=$false
try {
    if ((Test-Path -LiteralPath $hold) -or (Test-Path -LiteralPath $stop)) {return}
    if (Test-Path -LiteralPath $claimed) {throw 'LIVE_SERVICE_RESET_RECOVERY_ALREADY_CLAIMED'}
    $now=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    $slot=$now-($now%900000L)
    if (Test-Path -LiteralPath $pending) {
        $recovery=Get-Content -LiteralPath $pending -Raw | ConvertFrom-Json
        if ($recovery.config_sha256 -cne $ConfigSha256 -or
            $recovery.failed_ms -isnot [long] -or $recovery.slot_ms -isnot [long] -or
            $recovery.failed_ms -lt $recovery.slot_ms -or $now -lt $recovery.failed_ms -or
            $now-$recovery.failed_ms -ge 1800000L) {throw 'LIVE_SERVICE_RESET_RECOVERY_INVALID_OR_EXPIRED'}
        if ($slot -le $recovery.slot_ms -or $slot -le ($recovery.failed_ms-($recovery.failed_ms%900000L))) {return}
    }
    if ($now-$slot -gt 870000L -or (Test-Path -LiteralPath (Join-Path $segments "$slot/plan.json"))) {return}
    foreach($entry in $cfg.files) {
        if (!(Test-Path -LiteralPath $entry.path -PathType Leaf) -or
            (Get-FileHash -LiteralPath $entry.path).Hash.ToLowerInvariant() -cne $entry.sha256) {
            throw 'LIVE_SERVICE_RUNTIME_PIN'
        }
    }
    $paths=@(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction Stop |
        Select-Object -ExpandProperty InterfaceAlias -Unique)
    if ($paths.Count -ne 1 -or $paths[0] -cne $route) {throw 'LIVE_SERVICE_ROUTE_CHANGED'}
    $inet=Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
    if ($inet.ProxyEnable -or $inet.AutoConfigURL -or
        @(Get-ChildItem Env: | Where-Object Name -match '^(HTTPS?_PROXY|ALL_PROXY)$').Count -or
        !(netsh winhttp show proxy | Select-String 'Direct access')) {throw 'LIVE_SERVICE_PROXY_ROUTE_CHANGED'}

    $ntp=@((w32tm.exe /stripchart /computer:time.cloudflare.com /samples:4 /period:1 /packetinfo) -join "`n")
    if ($LASTEXITCODE) {throw 'LIVE_SERVICE_CLOCK_PROBE'}
    $lines=@($ntp -split '[\r\n]+' | ForEach-Object Trim)
    $offset=@($lines | ForEach-Object {if ($_ -match 'd:([+-][0-9.]+)s o:([+-][0-9.]+)s') {
        [Math]::Abs([double]$Matches[2])+[Math]::Abs([double]$Matches[1])/2 }})
    $delay=@($lines | ForEach-Object {if ($_ -match '^Root Delay:.*\(([+-]?[0-9.]+)s\)') {
        [Math]::Abs([double]$Matches[1])/2 }})
    $disp=@($lines | ForEach-Object {if ($_ -match '^Root Dispersion:.*\(([+-]?[0-9.]+)s\)') {
        [Math]::Abs([double]$Matches[1]) }})
    if ($offset.Count -ne 4 -or $delay.Count -ne 4 -or $disp.Count -ne 4 -or
        @($lines | Where-Object {$_ -match '^Leap Indicator: 0'}).Count -ne 4) {throw 'LIVE_SERVICE_CLOCK_SAMPLE'}
    $uncertainty=[int][Math]::Ceiling(20+1000*(($offset|Measure-Object -Maximum).Maximum+
        ($delay|Measure-Object -Maximum).Maximum+($disp|Measure-Object -Maximum).Maximum))
    if($uncertainty -gt 250) {throw 'LIVE_SERVICE_CLOCK_UNCERTAINTY'}
    $checked=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    $slot=$checked-($checked%900000L)
    $state=Join-Path $segments ([string]$slot)
    if ($checked-$slot -gt 885000L -or (Test-Path -LiteralPath "$state/plan.json") -or
        (Test-Path -LiteralPath $stop)) {return}

    $env:PYTHONPATH="$($cfg.tree)/src;$($cfg.tree)"
    Push-Location -LiteralPath $cfg.tree
    try {
        $plan=& $cfg.python -B -m tools.atlas_live_research_cycle plan --slot $slot --bars 8 --sustained-research
        if($LASTEXITCODE){throw 'LIVE_SERVICE_PLAN_FAILED'}
        $plan=$plan | ConvertFrom-Json
        $qualPath=Join-Path $root 'qualification.json'
        @{plan_sha256=$plan.sha256;endpoint=$plan.plan.endpoint;state_path=$state;raw_retention_ms=0;
            clock_checked_ms=$checked;clock_uncertainty_ms=$uncertainty;source_rights_ref=$cfg.source_rights_ref;
            region_ref=$cfg.region_ref;custody_ref='Private Windows NTFS, sanitized receipts only';
            network_permission_ref=$cfg.authorization_ref} |
            ConvertTo-Json | Set-Content -LiteralPath $qualPath -Encoding utf8NoBOM
        $pin=& $cfg.python -B -c 'import json,sys; from pathlib import Path; from aql.observation.contracts import digest; print(digest(json.loads(Path(sys.argv[1]).read_bytes())))' $qualPath
        if($LASTEXITCODE){throw 'LIVE_SERVICE_QUALIFICATION_PIN'}
        if ($recovery) {
            if ($checked-$recovery.failed_ms -ge 1800000L) {throw 'LIVE_SERVICE_RESET_RECOVERY_INVALID_OR_EXPIRED'}
            Rename-Item -LiteralPath $pending -NewName (Split-Path -Leaf $claimed)
            Record 'RESET_RECOVERY_STARTED' '' $slot
        }
        Record 'STARTED' '' $slot
        $result=@(& $cfg.python -B -m tools.atlas_live_research_cycle live --slot $slot --bars 8 --sustained-research --state $state --pin $plan.sha256 --pilot-qualification $qualPath --pilot-qualification-sha256 $pin 2>&1)
        $code=$LASTEXITCODE
        if ($code) {
            $reason='LIVE_SERVICE_SEGMENT_FAILED'
            foreach($line in $result) {
                if ([string]$line -match '^ValueError: (PILOT_STOP_[A-Za-z0-9_]{1,120})$') {$reason=$Matches[1]}
            }
            $segmentFailure=$true
            throw $reason
        }
        $last=$result[-1] | ConvertFrom-Json
        if ($last.status -eq 'STOPPED_BY_OPERATOR') {
            if (!(Test-Path -LiteralPath $stop)) {New-Item -ItemType File -Path $stop | Out-Null}
            Record 'STOPPED' 'OPERATOR_STOP_REQUESTED' $slot
            return
        }
        if ($last.bars.Count -ne 8 -or $last.orders -ne 0 -or $last.dispatch -ne $null) {
            throw 'LIVE_SERVICE_SEGMENT_SCOPE'
        }
        Record 'COMPLETE' '' $slot
        if ($recovery) {Remove-Item -LiteralPath $claimed}
    } finally {Pop-Location}
} catch {
    $reason=$_.Exception.Message
    if ($reason -cnotmatch '^[A-Za-z][A-Za-z0-9_]{1,159}$') {$reason='LIVE_SERVICE_LOCAL_FAILURE'}
    Record 'FAILED' $reason $slot
    if ($segmentFailure -and -not $recovery -and
        -not (Test-Path -LiteralPath $stop) -and
        (Test-ResetRecovery (Join-Path $state 'health.jsonl') $reason)) {
        try {
            $bytes=[Text.Encoding]::UTF8.GetBytes((@{slot_ms=$slot;config_sha256=$ConfigSha256;
                failed_ms=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()} | ConvertTo-Json -Compress))
            $file=[IO.File]::Open($pending,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write)
            try {$file.Write($bytes,0,$bytes.Length);$file.Flush($true)} finally {$file.Dispose()}
            Record 'RESET_RECOVERY_PENDING' $reason $slot
            exit 1
        } catch {$reason='LIVE_SERVICE_RESET_RECOVERY_PERSIST_FAILED'}
    }
    @{reason=$reason;utc=[DateTimeOffset]::UtcNow.ToString('o');slot_ms=$slot} |
        ConvertTo-Json | Set-Content -LiteralPath $hold -Encoding utf8NoBOM
    exit 1
} finally {$lock.Dispose()}
