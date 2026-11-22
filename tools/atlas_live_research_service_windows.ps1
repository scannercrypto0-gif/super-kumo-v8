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
$operatorTicket=Join-Path $root 'operator-resume.authorized.json'
$operatorActive=Join-Path $root 'operator-recovery.active.json'
$executionActive=Join-Path $root 'segment-execution.active.json'

function Record([string]$status, [string]$reason, [long]$slot) {
    $record=[ordered]@{utc=[DateTimeOffset]::UtcNow.ToString('o');status=$status;reason=$reason;slot_ms=$slot}
    $bytes=[Text.Encoding]::UTF8.GetBytes(($record | ConvertTo-Json -Compress)+"`n")
    $stream=[IO.File]::Open($log,[IO.FileMode]::Append,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    try {$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)} finally {$stream.Dispose()}
}

function Save-ServiceHold([string]$Reason, [long]$SlotMs) {
    $destination=$hold
    if (Test-Path -LiteralPath $destination) {
        $destination=Join-Path $root ('hold-rejection-'+[guid]::NewGuid().ToString('N')+'.json')
    }
    $bytes=[Text.Encoding]::UTF8.GetBytes((@{reason=$Reason;utc=[DateTimeOffset]::UtcNow.ToString('o');slot_ms=$SlotMs} | ConvertTo-Json -Compress))
    $stream=[IO.File]::Open($destination,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    try {$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)} finally {$stream.Dispose()}
}

function Archive-ExecutionClaim([string]$Outcome) {
    if ($executionClaim -and (Test-Path -LiteralPath $executionActive)) {
        [IO.File]::Move($executionActive,(Join-Path $root ('segment-execution.'+$Outcome+'-'+[guid]::NewGuid().ToString('N')+'.json')))
    }
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


function Test-ContinuousFault($Event) {
    if ($Event.status -cne 'TRANSPORT_INTERRUPTED' -or $Event.retry_eligible -isnot [bool] -or
        !$Event.retry_eligible -or $Event.is_transport_fault -ne $true) {return $false}
    if ($Event.fault_stage -ceq 'FRAME_READ') {
        return ($Event.receive_phase -ceq 'FRAME_BOUNDARY' -and $Event.fault_class -ceq 'FRAME_BOUNDARY_TRANSIENT')
    }
    if ($Event.fault_stage -ceq 'CONNECT') {
        return @('CONNECT_TIMEOUT','CONNECT_RESET_OR_REFUSED','DNS_FAILURE','HTTP_REJECTION') -ccontains $Event.fault_class
    }
    return ($Event.fault_stage -ceq 'PONG' -and $Event.fault_class -ceq 'PONG_LIVENESS_EXPIRED')
}

function Test-ContinuousRecovery([string]$HealthLog,[string]$Reason) {
    try {
        $events=@(Get-Content -LiteralPath $HealthLog | ForEach-Object {$_ | ConvertFrom-Json} |
            Where-Object status -in @('CONNECTING','TRANSPORT_INTERRUPTED','FAULT_CLASSIFIED','STOPPED_ERROR'))
        if ($Reason -ceq 'PILOT_STOP_FINALIZED_SOURCE_GAP') {
            return ($events.Count -ge 2 -and $events[-1].status -ceq 'STOPPED_ERROR' -and
                $events[-1].error -ceq 'FINALIZED_SOURCE_GAP' -and $events[-2].status -ceq 'FAULT_CLASSIFIED' -and
                $events[-2].fault_stage -ceq 'CLOCK_GUARD')
        }
        return ($events.Count -eq 5 -and $events[0].status -ceq 'CONNECTING' -and $events[0].attempt -eq 1 -and
            (Test-ContinuousFault $events[1]) -and
            $events[2].status -ceq 'CONNECTING' -and $events[2].attempt -eq 2 -and
            (Test-ContinuousFault $events[3]) -and
            $events[4].status -ceq 'STOPPED_ERROR' -and
            $Reason -ceq ('PILOT_STOP_'+$events[4].error))
    } catch {return $false}
}

function Continuous-Decision([string]$Mode,[long]$SlotMs) {
    $command=@('-B','-m','tools.atlas_ws_continuity',$Mode,'--root',$root,'--config-pin',$ConfigSha256)
    if ($Mode -cne 'status') {$command+=@('--slot',[string]$SlotMs)}
    $oldPythonPath=$env:PYTHONPATH
    try {
        $env:PYTHONPATH="$($cfg.tree)/src;$($cfg.tree)"
        $answer=& $cfg.python @command
        if ($LASTEXITCODE) {throw 'LIVE_SERVICE_CONTINUITY_STATE_FAILED'}
        $decision=$answer | ConvertFrom-Json
        if (!$decision.enabled) {throw 'LIVE_SERVICE_CONTINUITY_AUTHORITY_MISSING'}
        return $decision
    } finally {$env:PYTHONPATH=$oldPythonPath}
}

function Archive-OperatorClaim {
    if (Test-Path -LiteralPath $operatorActive) {
        [IO.File]::Move($operatorActive,(Join-Path $root ('operator-recovery.completed-'+[guid]::NewGuid().ToString('N')+'.json')))
    }
}

function Test-OperatorResume([string]$TicketPath, [string]$RootPath, [string]$ConfigPin, [long]$NowMs) {
    if (!(Test-Path -LiteralPath $TicketPath -PathType Leaf) -or
        (Get-Item -LiteralPath $TicketPath).Length -gt 65536) {throw 'LIVE_SERVICE_OPERATOR_TICKET_BOUND'}
    $ticket=Get-Content -LiteralPath $TicketPath -Raw | ConvertFrom-Json
    if ($ticket.schema -cne 'atlas.ws.operator-resume.v1' -or
        $ticket.authorization_sha256 -cnotmatch '^[0-9a-f]{64}$' -or
        $ticket.config_sha256 -cne $ConfigPin -or
        $ticket.issued_ms -isnot [long] -or $ticket.expires_ms -isnot [long] -or
        $NowMs -lt $ticket.issued_ms -or $NowMs -ge $ticket.expires_ms -or
        $ticket.expires_ms-$ticket.issued_ms -gt 1800000L -or
        ($ticket.max_segments -isnot [int] -and $ticket.max_segments -isnot [long]) -or
        ($ticket.max_connections -isnot [int] -and $ticket.max_connections -isnot [long]) -or
        ($ticket.orders -isnot [int] -and $ticket.orders -isnot [long]) -or
        $ticket.max_segments -ne 1 -or $ticket.max_connections -ne 2 -or
        $ticket.orders -ne 0 -or $ticket.trading_authority -cne 'NONE') {
        throw 'LIVE_SERVICE_OPERATOR_TICKET_SCOPE'
    }
    foreach($entry in @(@('hold.json','hold_sha256'),@('reset-recovery.claimed','claimed_sha256'),
                         @('reset-recovery.pending','pending_sha256'))) {
        $path=Join-Path $RootPath $entry[0]
        $expected=$ticket.($entry[1])
        if (Test-Path -LiteralPath $path) {
            if ($expected -cnotmatch '^[0-9a-f]{64}$' -or
                (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $expected) {
                throw 'LIVE_SERVICE_OPERATOR_EVIDENCE_CHANGED'
            }
        } elseif ($null -ne $expected) {throw 'LIVE_SERVICE_OPERATOR_EVIDENCE_MISSING'}
    }
    $held=Get-Content -LiteralPath (Join-Path $RootPath 'hold.json') -Raw | ConvertFrom-Json
    if (@('PILOT_STOP_TimeoutError','PILOT_STOP_ConnectionResetError') -cnotcontains $held.reason -and
        !($held.reason -ceq 'LIVE_SERVICE_CONTINUITY_CIRCUIT_OPEN' -and $ticket.fresh_ping_correction -is [bool] -and $ticket.fresh_ping_correction)) {
        throw 'LIVE_SERVICE_OPERATOR_HOLD_NOT_ELIGIBLE'
    }
    return $ticket
}

function Claim-OperatorResume([string]$TicketPath, [string]$RootPath, [string]$ConfigPin, [long]$NowMs) {
    $ticket=Test-OperatorResume $TicketPath $RootPath $ConfigPin $NowMs
    $active=Join-Path $RootPath 'operator-recovery.active.json'
    if (Test-Path -LiteralPath $active) {throw 'LIVE_SERVICE_OPERATOR_RECOVERY_ALREADY_CLAIMED'}
    # Claim first: a crash at any later stage cannot authorize another collector.
    [IO.File]::Move($TicketPath,$active)
    $stream=[IO.File]::Open($active,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::Read)
    try {$stream.Flush($true)} finally {$stream.Dispose()}
    $archive=Join-Path (Join-Path $RootPath 'recovery-evidence') $ticket.authorization_sha256
    if (Test-Path -LiteralPath $archive) {throw 'LIVE_SERVICE_OPERATOR_ARCHIVE_EXISTS'}
    New-Item -ItemType Directory -Path $archive | Out-Null
    foreach($name in @('hold.json','reset-recovery.pending','reset-recovery.claimed')) {
        $path=Join-Path $RootPath $name
        if (Test-Path -LiteralPath $path) {[IO.File]::Move($path,(Join-Path $archive $name))}
    }
    return $ticket
}

if ((Test-Path -LiteralPath $stop) -or
    ((Test-Path -LiteralPath $hold) -and !(Test-Path -LiteralPath $operatorTicket))) {return}
function Measure-ClockSamples([string]$Text){
    $lines=@($Text -split '[\r\n]+' | ForEach-Object Trim)
    $culture=[Globalization.CultureInfo]::InvariantCulture
    $offset=@($lines|ForEach-Object {if($_ -match 'd:([+-][0-9.]+)s\s+o:([+-][0-9.]+)s'){
        [Math]::Abs([double]::Parse($Matches[2],$culture))+[Math]::Abs([double]::Parse($Matches[1],$culture))/2}})
    $delay=@($lines|ForEach-Object {if($_ -match '^Root Delay:.*\(([+-]?[0-9.]+)s\)'){[Math]::Abs([double]::Parse($Matches[1],$culture))/2}})
    $disp=@($lines|ForEach-Object {if($_ -match '^Root Dispersion:.*\(([+-]?[0-9.]+)s\)'){[Math]::Abs([double]::Parse($Matches[1],$culture))}})
    $leap=@($lines|Where-Object {$_ -match '^Leap Indicator: 0(?:\D|$)'}).Count
    $script:clockSampleCounts=@{offset=$offset.Count;root_delay=$delay.Count;root_dispersion=$disp.Count;leap_ok=$leap}
    if($offset.Count -ne 4 -or $delay.Count -ne 4 -or $disp.Count -ne 4 -or $leap -ne 4){throw 'HOST_CLOCK_SAMPLE_INVALID'}
    $uncertainty=[int][Math]::Ceiling(20+1000*(($offset|Measure-Object -Maximum).Maximum+
        ($delay|Measure-Object -Maximum).Maximum+($disp|Measure-Object -Maximum).Maximum))
    if($uncertainty -gt 250){throw 'HOST_CLOCK_UNCERTAINTY'}
    return @{checked_ms=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds();uncertainty_ms=$uncertainty}
}
function Read-ClockProbe {
    $info=[Diagnostics.ProcessStartInfo]::new()
    $info.FileName='w32tm.exe'
    $info.Arguments='/stripchart /computer:time.cloudflare.com /samples:4 /period:1 /packetinfo'
    $info.UseShellExecute=$false;$info.CreateNoWindow=$true
    $info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    $process=[Diagnostics.Process]::new();$process.StartInfo=$info
    try{
        if(!$process.Start()){throw 'HOST_CLOCK_PROBE_FAILED'}
        $stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync()
        if(!$process.WaitForExit(15000)){$process.Kill();$process.WaitForExit();throw 'HOST_CLOCK_PROBE_TIMEOUT'}
        $text=$stdout.GetAwaiter().GetResult();$errorText=$stderr.GetAwaiter().GetResult()
        if($process.ExitCode -ne 0 -or $text.Length -gt 65536 -or $errorText.Length -gt 65536){throw 'HOST_CLOCK_PROBE_FAILED'}
        return $text
    }finally{$process.Dispose()}
}
function Qualified-Clock {
    $script:clockFailure=$null
    $attempts=@()
    for($attempt=1;$attempt -le 3;$attempt++){
        $script:clockSampleCounts=$null
        try{
            $measurement=Measure-ClockSamples (Read-ClockProbe)
            $measurement['probe_attempts']=$attempt
            $measurement['prior_failures']=@($attempts)
            return $measurement
        }catch{
            $reason=$_.Exception.Message
            $attempts+=@{attempt=$attempt;reason=if($reason -cmatch '^HOST_CLOCK_[A-Z_]+$'){$reason}else{'HOST_CLOCK_PRIVATE_FAILURE'};counts=$script:clockSampleCounts}
            $script:clockFailure=@{attempts=@($attempts);max_attempts=3;uncertainty_limit_ms=250}
            # Never pool partial samples, accept an uncertain result or retry an
            # unknown error. A new bounded probe must independently pass all four.
            if($reason -cnotin @('HOST_CLOCK_SAMPLE_INVALID','HOST_CLOCK_PROBE_FAILED','HOST_CLOCK_PROBE_TIMEOUT') -or $attempt -eq 3){throw}
            Start-Sleep -Milliseconds 500
        }
    }
}
$lockPath=Join-Path $root 'supervisor.lock'
try { $lock=[IO.File]::Open($lockPath,'OpenOrCreate','ReadWrite','None') }
catch [IO.IOException] { return }
$slot=0
$route='Ethernet'
$recovery=$null
$operatorRecovery=$null
$segmentFailure=$false
$executionClaim=$false
$continuous=$false
try {
    if ((Test-Path -LiteralPath $stop) -or
        ((Test-Path -LiteralPath $hold) -and !(Test-Path -LiteralPath $operatorTicket))) {return}
    if (Test-Path -LiteralPath $executionActive) {throw 'LIVE_SERVICE_INCOMPLETE_SEGMENT_REVIEW_REQUIRED'}
    $continuous=Test-Path -LiteralPath (Join-Path $root 'continuous-research.authorized.json')
    if ((Test-Path -LiteralPath $operatorActive) -and !$continuous) {throw 'LIVE_SERVICE_OPERATOR_RECOVERY_ALREADY_CLAIMED'}
    if (Test-Path -LiteralPath (Join-Path $root 'operator-deployment.in-progress')) {throw 'LIVE_SERVICE_DEPLOYMENT_IN_PROGRESS'}
    if (Test-Path -LiteralPath $operatorTicket) {
        $operatorRecovery=Test-OperatorResume $operatorTicket $root $ConfigSha256 ([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())
    }
    if ((Test-Path -LiteralPath $claimed) -and -not $operatorRecovery) {throw 'LIVE_SERVICE_RESET_RECOVERY_ALREADY_CLAIMED'}
    $now=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    $slot=$now-($now%900000L)
    if ((Test-Path -LiteralPath $pending) -and -not $operatorRecovery) {
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
    if ($continuous) {
        $decision=Continuous-Decision 'status' 0
        if ($decision.circuit_open) {throw 'LIVE_SERVICE_CONTINUITY_CIRCUIT_OPEN'}
        if ([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() -lt $decision.wait_until_ms) {return}
    }
    $paths=@(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction Stop |
        Select-Object -ExpandProperty InterfaceAlias -Unique)
    if ($paths.Count -ne 1 -or $paths[0] -cne $route) {throw 'LIVE_SERVICE_ROUTE_CHANGED'}
    $inet=Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
    if ($inet.ProxyEnable -or $inet.AutoConfigURL -or
        @(Get-ChildItem Env: | Where-Object Name -match '^(HTTPS?_PROXY|ALL_PROXY)$').Count -or
        !(netsh winhttp show proxy | Select-String 'Direct access')) {throw 'LIVE_SERVICE_PROXY_ROUTE_CHANGED'}

    try{$clock=Qualified-Clock}catch{
        switch -CaseSensitive ($_.Exception.Message){
            'HOST_CLOCK_UNCERTAINTY' {throw 'LIVE_SERVICE_CLOCK_UNCERTAINTY'}
            'HOST_CLOCK_SAMPLE_INVALID' {throw 'LIVE_SERVICE_CLOCK_SAMPLE'}
            default {throw 'LIVE_SERVICE_CLOCK_PROBE'}
        }
    }
    $uncertainty=$clock.uncertainty_ms
    $checked=$clock.checked_ms
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
        if ($operatorRecovery) {
            $operatorRecovery=Claim-OperatorResume $operatorTicket $root $ConfigSha256 ([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())
            $recovery=$operatorRecovery
            Record 'OPERATOR_RECOVERY_STARTED' '' $slot
        } elseif ($recovery) {
            if ($checked-$recovery.failed_ms -ge 1800000L) {throw 'LIVE_SERVICE_RESET_RECOVERY_INVALID_OR_EXPIRED'}
            Rename-Item -LiteralPath $pending -NewName (Split-Path -Leaf $claimed)
            Record 'RESET_RECOVERY_STARTED' '' $slot
        }
        $claimBytes=[Text.Encoding]::UTF8.GetBytes((@{slot_ms=$slot;config_sha256=$ConfigSha256;plan_sha256=$plan.sha256} | ConvertTo-Json -Compress))
        $claimFile=[IO.File]::Open($executionActive,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
        try {$claimFile.Write($claimBytes,0,$claimBytes.Length);$claimFile.Flush($true)} finally {$claimFile.Dispose()}
        $executionClaim=$true
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
            Archive-ExecutionClaim 'operator-stopped'
            return
        }
        if ($last.bars.Count -ne 8 -or $last.orders -ne 0 -or $last.dispatch -ne $null) {
            throw 'LIVE_SERVICE_SEGMENT_SCOPE'
        }
        Record 'COMPLETE' '' $slot
        if ($continuous) {
            $decision=Continuous-Decision 'complete' $slot
            Archive-OperatorClaim
        } elseif ($operatorRecovery) {
            # One explicitly authorized segment, not an ongoing service release.
            Save-ServiceHold 'LIVE_SERVICE_OPERATOR_RECOVERY_COMPLETE_REVIEW_REQUIRED' $slot
            Record 'OPERATOR_RECOVERY_COMPLETE_REVIEW_REQUIRED' '' $slot
        } elseif ($recovery) {Remove-Item -LiteralPath $claimed}
        Archive-ExecutionClaim 'complete'
    } finally {Pop-Location}
} catch {
    $reason=$_.Exception.Message
    if ($reason -cnotmatch '^[A-Za-z][A-Za-z0-9_]{1,159}$') {$reason='LIVE_SERVICE_LOCAL_FAILURE'}
    Record 'FAILED' $reason $slot
    if ($continuous -and $segmentFailure -and
        -not (Test-Path -LiteralPath $stop) -and
        (Test-ContinuousRecovery (Join-Path $state 'health.jsonl') $reason)) {
        try {
            $decision=Continuous-Decision 'failed' $slot
            if ($decision.circuit_open) {
                Save-ServiceHold 'LIVE_SERVICE_CONTINUITY_CIRCUIT_OPEN' $slot
                Record 'CONTINUITY_CIRCUIT_OPEN' $reason $slot
            } else {Record 'CONTINUITY_BACKOFF_PENDING' $reason $slot}
            Archive-OperatorClaim
            Archive-ExecutionClaim 'continuous-failed-outage-recorded'
            exit 1
        } catch {$reason='LIVE_SERVICE_CONTINUITY_PERSIST_FAILED'}
    }
    if (-not $continuous -and $segmentFailure -and -not $recovery -and
        -not (Test-Path -LiteralPath $stop) -and
        (Test-ResetRecovery (Join-Path $state 'health.jsonl') $reason)) {
        try {
            $bytes=[Text.Encoding]::UTF8.GetBytes((@{slot_ms=$slot;config_sha256=$ConfigSha256;
                failed_ms=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()} | ConvertTo-Json -Compress))
            $file=[IO.File]::Open($pending,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write)
            try {$file.Write($bytes,0,$bytes.Length);$file.Flush($true)} finally {$file.Dispose()}
            Record 'RESET_RECOVERY_PENDING' $reason $slot
            Archive-ExecutionClaim 'failed-recovery-pending'
            exit 1
        } catch {$reason='LIVE_SERVICE_RESET_RECOVERY_PERSIST_FAILED'}
    }
    if ((Test-Path -LiteralPath $operatorTicket) -and (Test-Path -LiteralPath $hold)) {
        # Invalid/expired requests do not keep waking the held service, nor
        # overwrite the original safety evidence. A new permit is required.
        [IO.File]::Move($operatorTicket,(Join-Path $root ('operator-resume.rejected-'+[guid]::NewGuid().ToString('N')+'.json')))
    }
    Save-ServiceHold $reason $slot
    Archive-ExecutionClaim 'failed-held'
    exit 1
} finally {$lock.Dispose()}
