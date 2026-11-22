[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{40}$')][string]$ExpectedCommit,
    [ValidateSet('Diagnose','Apply')][string]$Mode='Diagnose',
    [string]$AuthorizationFile,
    [string]$TaskName='ATLAS-Research-Sustained-Spot-WS'
)
# Diagnose is read-only and never probes clock/network or starts a collector.
# Apply is a separately owner-authorized stage, not an engineering permission.
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$helper=Join-Path $PSScriptRoot 'atlas_ws_resilience_operator.py'
$lock=$null; $gate=$null; $oldAction=$null; $taskChanged=$false; $commitSent=$false; $gateReady=$false; $privateFailure=$null; $gateInput=$null
function Hash-Text([string]$value) {
    $h=[Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($h.ComputeHash([Text.Encoding]::UTF8.GetBytes($value)))).Replace('-','').ToLowerInvariant() }
    finally {$h.Dispose()}
}
function Hash-TaskPolicy([string]$xml) {
    $doc=[xml]$xml
    $parts=@('Triggers','Principals','Settings') | ForEach-Object {
        $node=$doc.DocumentElement.SelectSingleNode("*[local-name()='$_']")
        if(-not $node){throw 'TASK_POLICY_NODE_MISSING'}
        $node.OuterXml
    }
    return (Hash-Text ($parts -join "`n"))
}
function Read-GateLine {
    $pending=$gate.StandardOutput.ReadLineAsync()
    if(-not $pending.Wait(30000)){throw 'PRIVATE_GATE_RESPONSE_TIMEOUT'}
    if(-not $pending.Result){throw 'PRIVATE_GATE_EOF'}
    return $pending.Result
}
function Wait-GateExit {
    if(-not $gate.WaitForExit(30000)){throw 'PRIVATE_GATE_EXIT_TIMEOUT'}
}
function Get-UniqueTask {
    $items=@(Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop)
    if($items.Count -ne 1 -or @($items[0].Actions).Count -ne 1){throw 'TASK_NOT_UNIQUE'}
    return $items[0]
}
function Read-Arg([string]$value,[string]$name) {
    $pattern='(?i)(?:^|\s)-'+$name+'\s+(?:"([^"]+)"|''([^'']+)''|(\S+))'
    $m=[regex]::Match($value,$pattern)
    if(-not $m.Success){throw 'TASK_ARGUMENTS_UNEXPECTED'}
    return [Environment]::ExpandEnvironmentVariables(($m.Groups[1].Value+$m.Groups[2].Value+$m.Groups[3].Value))
}
function Snapshot($task,[bool]$locked) {
    $a=$task.Actions[0]
    $config=Read-Arg $a.Arguments 'Config'
    $pin=Read-Arg $a.Arguments 'ConfigSha256'
    $script=Read-Arg $a.Arguments 'File'
    if($pin -cnotmatch '^[a-f0-9]{64}$' -or (Get-FileHash -LiteralPath $config -Algorithm SHA256).Hash -ine $pin){throw 'CONFIG_PIN_MISMATCH'}
    $cfg=Get-Content -LiteralPath $config -Raw | ConvertFrom-Json
    $root=Split-Path -Parent $config
    $xml=Export-ScheduledTask -TaskName $TaskName -TaskPath $task.TaskPath
    $collectors=@(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
        $_.CommandLine -match '(?i)(?:tools[./\\])?atlas_live_research_cycle(?:\.py)?\s+live|atlas_single_receipt_runner|binance_live_feed[./\\]runner'
    })
    if(-not $locked){
        $probe=$null
        try {
            $probe=[IO.File]::Open((Join-Path $root 'supervisor.lock'),'Open','ReadWrite','None')
            $locked=$true
        } catch [IO.IOException] {$locked=$false}
        finally {if($probe){$probe.Dispose()}}
    }
    return @{task_name=$TaskName;task_state=[string]$task.State;task_enabled=[bool]$task.Settings.Enabled;
        task_xml=$xml;task_xml_sha256=(Hash-Text $xml);task_policy_sha256=(Hash-TaskPolicy $xml);task_config_sha256=$pin;
        task_action=@{Execute=$a.Execute;Arguments=$a.Arguments;WorkingDirectory=$a.WorkingDirectory};
        service_path=$script;config_path=$config;root=$root;python=$cfg.python;
        collector_processes=$collectors.Count;supervisor_lock_available=$locked;
        operator_stop=(Test-Path -LiteralPath (Join-Path $root 'stop.request'))}
}
function Set-PrivateUtf8($info) {
    # Windows PowerShell 5 pipelines default to ASCII. Use an explicit UTF-8
    # pipe on both CLR generations, preserving task XML/config hash identity.
    $utf8=[Text.UTF8Encoding]::new($false)
    $info.StandardOutputEncoding=$utf8
    $info.StandardErrorEncoding=$utf8
    if($info.GetType().GetProperty('StandardInputEncoding')){$info.StandardInputEncoding=$utf8}
    $info.EnvironmentVariables['PYTHONIOENCODING']='utf-8'
    $info.EnvironmentVariables['PYTHONUTF8']='1'
}
function New-PrivateInputWriter($process) {
    # Framework PowerShell lacks StandardInputEncoding: bypass its console-
    # encoded writer and own the UTF-8 pipe explicitly on every CLR version.
    return [IO.StreamWriter]::new($process.StandardInput.BaseStream,[Text.UTF8Encoding]::new($false),4096)
}
function Invoke-PrivateCheck([string]$mode,$snapshot,[ValidateRange(100,30000)][int]$TimeoutMs=30000) {
    $script:privateFailure=$null
    $process=$null
    $payload=$snapshot|ConvertTo-Json -Depth 30 -Compress
    if([Text.Encoding]::UTF8.GetByteCount($payload) -gt 8388608){throw 'PRIVATE_SNAPSHOT_BOUND'}
    if($helper.Contains('"') -or $repo.Contains('"') -or ($AuthorizationFile -and $AuthorizationFile.Contains('"'))){throw 'ARGUMENT_PATH_INVALID'}
    $info=[Diagnostics.ProcessStartInfo]::new()
    $info.FileName=$snapshot.python
    $info.Arguments='-B "'+$helper+'" '+$mode+' --repo "'+$repo+'" --expected-commit '+$ExpectedCommit
    if($AuthorizationFile){$info.Arguments+=' --authorization "'+$AuthorizationFile+'"'}
    $info.UseShellExecute=$false;$info.CreateNoWindow=$true
    $info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    Set-PrivateUtf8 $info
    try {
        $process=[Diagnostics.Process]::new();$process.StartInfo=$info
        if(-not $process.Start()){throw 'PRIVATE_HELPER_START_FAILED'}
        # Read concurrently, with hard bounds; never forward private stderr.
        $outputChars=[char[]](New-Object char[] 2097153)
        $errorChars=[char[]](New-Object char[] 65537)
        $stdout=$process.StandardOutput.ReadBlockAsync($outputChars,0,$outputChars.Length)
        $stderr=$process.StandardError.ReadBlockAsync($errorChars,0,$errorChars.Length)
        $inputWriter=New-PrivateInputWriter $process
        $write=$inputWriter.WriteLineAsync($payload)
        if(-not $write.Wait($TimeoutMs)){throw 'PRIVATE_HELPER_INPUT_TIMEOUT'}
        $inputWriter.Close()
        if(-not $process.WaitForExit($TimeoutMs)){throw 'PRIVATE_HELPER_TIMEOUT'}
        if(-not $stdout.Wait(5000) -or -not $stderr.Wait(5000)){throw 'PRIVATE_HELPER_DRAIN_TIMEOUT'}
        $count=$stdout.Result;$errorCount=$stderr.Result
        if($count -ge $outputChars.Length -or $errorCount -ge $errorChars.Length){throw 'PRIVATE_HELPER_RESPONSE_BOUND'}
        $output=[string]::new($outputChars,0,$count)
        $privateError=[string]::new($errorChars,0,$errorCount)
        $script:privateFailure=[ordered]@{phase=('PRIVATE_HELPER_'+$mode.ToUpperInvariant());child_exit_code=$process.ExitCode;
            stdout_sha256=(Hash-Text $output);stderr_sha256=(Hash-Text $privateError)}
        try {$response=$output|ConvertFrom-Json -ErrorAction Stop} catch {throw 'PRIVATE_HELPER_UNSTRUCTURED_FAILURE'}
        if($process.ExitCode -ne 0){
            if($response.status -ceq 'WS_OPERATOR_BLOCKED' -and
                $response.reason -cmatch '^[A-Z][A-Z0-9_]{1,119}$'){
                $script:privateFailure.reason=$response.reason
                if($response.reason -ceq 'OWNER_HOST_PREFLIGHT_BLOCKED' -and $response.preflight){
                    $script:privateFailure['preflight']=$response.preflight
                }
                throw [string]$response.reason
            }
            throw 'PRIVATE_HELPER_UNSTRUCTURED_FAILURE'
        }
        if(($mode -ceq 'diagnose' -and ($response.schema -cne 'atlas.ws.operator-diagnostic.v1' -or
            $response.identity_sha256 -cnotmatch '^[a-f0-9]{64}$')) -or
           ($mode -ceq 'authorize' -and ($response.status -cne 'EXPLICIT_OWNER_AUTHORIZATION_VERIFIED' -or
            $response.authorization_sha256 -cnotmatch '^[a-f0-9]{64}$'))){throw 'PRIVATE_HELPER_RESPONSE_SCHEMA'}
        $script:privateFailure=$null
        return $response
    } finally {
        if($process){
            if(-not $process.HasExited){try {$process.Kill();$null=$process.WaitForExit(5000)}catch{}}
            $process.Dispose()
        }
    }
}
function Get-AuthorizedApplySnapshot([string]$Root,[int]$WaitSeconds=180){
    $deadline=[DateTimeOffset]::UtcNow.AddSeconds($WaitSeconds)
    do{
        $script:lock=$null
        try{$script:lock=[IO.File]::Open((Join-Path $Root 'supervisor.lock'),'Open','ReadWrite','None')}
        catch [IO.IOException]{
            if(!(Test-Path -LiteralPath (Join-Path $Root 'supervisor.lock')) -or [DateTimeOffset]::UtcNow -ge $deadline){throw 'SUPERVISOR_LOCK_UNAVAILABLE'}
            Start-Sleep -Milliseconds 500
            continue
        }
        try{
            $current=Get-UniqueTask
            $currentSnapshot=Snapshot $current $true
            # Authorization and every preflight predicate are checked while the
            # same exclusive supervisor lock remains held through COMMIT.
            $null=Invoke-PrivateCheck 'authorize' $currentSnapshot
            return $currentSnapshot
        }catch{
            $retry=($_.Exception.Message -ceq 'OWNER_HOST_PREFLIGHT_BLOCKED' -and
                $script:privateFailure.preflight.retryable_scheduler_only -eq $true)
            $script:lock.Dispose();$script:lock=$null
            if(!$retry -or [DateTimeOffset]::UtcNow -ge $deadline){throw}
            Start-Sleep -Milliseconds 500
        }
    }while($true)
}
function Qualified-Clock {
    # Existing supervisor's bounded clock qualification, only after separate consent.
    $clockInfo=[Diagnostics.ProcessStartInfo]::new()
    $clockInfo.FileName='w32tm.exe'
    $clockInfo.Arguments='/stripchart /computer:time.cloudflare.com /samples:4 /period:1 /packetinfo'
    $clockInfo.UseShellExecute=$false;$clockInfo.CreateNoWindow=$true
    $clockInfo.RedirectStandardOutput=$true;$clockInfo.RedirectStandardError=$true
    $clockProcess=[Diagnostics.Process]::new();$clockProcess.StartInfo=$clockInfo
    try {
        if(-not $clockProcess.Start()){throw 'HOST_CLOCK_PROBE_FAILED'}
        if(-not $clockProcess.WaitForExit(15000)){
            $clockProcess.Kill();$null=$clockProcess.WaitForExit(5000)
            throw 'HOST_CLOCK_PROBE_TIMEOUT'
        }
        $text=$clockProcess.StandardOutput.ReadToEnd()
        if($clockProcess.ExitCode -ne 0 -or $text.Length -gt 65536){throw 'HOST_CLOCK_PROBE_FAILED'}
    } finally {$clockProcess.Dispose()}
    $lines=@($text -split '[\r\n]+' | ForEach-Object Trim)
    $offset=@($lines|ForEach-Object {if($_ -match 'd:([+-][0-9.]+)s o:([+-][0-9.]+)s'){
        [Math]::Abs([double]$Matches[2])+[Math]::Abs([double]$Matches[1])/2}})
    $delay=@($lines|ForEach-Object {if($_ -match '^Root Delay:.*\(([+-]?[0-9.]+)s\)'){[Math]::Abs([double]$Matches[1])/2}})
    $disp=@($lines|ForEach-Object {if($_ -match '^Root Dispersion:.*\(([+-]?[0-9.]+)s\)'){[Math]::Abs([double]$Matches[1])}})
    if($offset.Count -ne 4 -or $delay.Count -ne 4 -or $disp.Count -ne 4 -or
        @($lines|Where-Object {$_ -match '^Leap Indicator: 0'}).Count -ne 4){throw 'HOST_CLOCK_SAMPLE_INVALID'}
    $uncertainty=[int][Math]::Ceiling(20+1000*(($offset|Measure-Object -Maximum).Maximum+
        ($delay|Measure-Object -Maximum).Maximum+($disp|Measure-Object -Maximum).Maximum))
    if($uncertainty -gt 250){throw 'HOST_CLOCK_UNCERTAINTY'}
    return @{checked_ms=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds();uncertainty_ms=$uncertainty}
}
try {
    $actual=& git -C $repo rev-parse HEAD
    if($LASTEXITCODE -or $actual -cne $ExpectedCommit){throw 'EXACT_CANDIDATE_COMMIT_REQUIRED'}
    $task=Get-UniqueTask
    $snapshot=Snapshot $task $false
    if($Mode -eq 'Diagnose'){
        Invoke-PrivateCheck 'diagnose' $snapshot | ConvertTo-Json -Depth 30
        return
    }
    if(-not $AuthorizationFile){throw 'SEPARATE_OWNER_AUTHORIZATION_REQUIRED'}
    # Acquire once, then authorize the exact locked snapshot. Do not authorize
    # a transient unlocked scheduler state and only acquire the lock afterward.
    $root=$snapshot.root
    $snapshot=Get-AuthorizedApplySnapshot $root
    $task=Get-UniqueTask
    $snapshot.clock=Qualified-Clock
    $oldAction=$task.Actions[0]
    $psi=[Diagnostics.ProcessStartInfo]::new()
    $psi.FileName=$snapshot.python
    # No shell; paths are quoted arguments to the pinned Python executable.
    if($helper.Contains('"') -or $repo.Contains('"') -or $AuthorizationFile.Contains('"')){throw 'ARGUMENT_PATH_INVALID'}
    $psi.Arguments='-B "'+$helper+'" gate --repo "'+$repo+'" --expected-commit '+$ExpectedCommit+' --authorization "'+$AuthorizationFile+'"'
    $psi.UseShellExecute=$false; $psi.CreateNoWindow=$true
    $psi.RedirectStandardInput=$true; $psi.RedirectStandardOutput=$true; $psi.RedirectStandardError=$true
    Set-PrivateUtf8 $psi
    $gate=[Diagnostics.Process]::new();$gate.StartInfo=$psi
    if(-not $gate.Start()){throw 'PRIVATE_GATE_START_FAILED'}
    $gateInput=New-PrivateInputWriter $gate
    $gateInput.AutoFlush=$true
    $gateInput.WriteLine(($snapshot|ConvertTo-Json -Depth 30 -Compress))
    $gateInput.Flush()
    $ready=(Read-GateLine)|ConvertFrom-Json
    if($ready.status -ceq 'WS_OPERATOR_BLOCKED' -and $ready.reason -cmatch '^[A-Z][A-Z0-9_]{1,119}$'){
        $script:privateFailure=@{phase='PRIVATE_GATE_PREFLIGHT';reason=$ready.reason;preflight=$ready.preflight}
        throw [string]$ready.reason
    }
    if($ready.status -cne 'STAGED_AWAITING_TASK_PIN' -or $ready.config_sha256 -cnotmatch '^[a-f0-9]{64}$'){throw 'PRIVATE_GATE_PREFLIGHT_FAILED'}
    $gateReady=$true
    $current=Get-UniqueTask
    $currentXml=Export-ScheduledTask -TaskName $TaskName -TaskPath $current.TaskPath
    if((Hash-Text $currentXml) -cne $snapshot.task_xml_sha256 -or [string]$current.State -cne 'Ready'){throw 'TASK_CHANGED_DURING_STAGE'}
    $pin=[regex]::Match($oldAction.Arguments,'(?i)(?:^|\s)-ConfigSha256\s+["'']?([a-f0-9]{64})(?=["''\s]|$)')
    if(-not $pin.Success){throw 'TASK_CONFIG_PIN_ARGUMENT'}
    $argsNew=$oldAction.Arguments.Remove($pin.Groups[1].Index,64).Insert($pin.Groups[1].Index,$ready.config_sha256)
    $params=@{Execute=$oldAction.Execute;Argument=$argsNew}
    if($oldAction.WorkingDirectory){$params.WorkingDirectory=$oldAction.WorkingDirectory}
    Set-ScheduledTask -TaskName $TaskName -TaskPath $task.TaskPath -Action (New-ScheduledTaskAction @params) | Out-Null
    $taskChanged=$true
    $after=Get-UniqueTask
    if($after.Actions[0].Arguments -cne $argsNew -or $after.Actions[0].Execute -cne $oldAction.Execute -or
        $after.Actions[0].WorkingDirectory -cne $oldAction.WorkingDirectory -or [string]$after.State -cne 'Ready' -or
        (Hash-TaskPolicy (Export-ScheduledTask -TaskName $TaskName -TaskPath $task.TaskPath)) -cne $snapshot.task_policy_sha256) {throw 'TASK_ACTION_PIN_READBACK_FAILED'}
    $commitSent=$true
    $gateInput.WriteLine('COMMIT');$gateInput.Flush()
    $result=(Read-GateLine)|ConvertFrom-Json
    $gateInput.Close();Wait-GateExit
    if($gate.ExitCode -ne 0 -or $result.status -cne 'WS_ENGINEERING_INSTALLED_ONE_RECOVERY_WAITING_FOR_EXISTING_SCHEDULE'){throw 'PRIVATE_GATE_COMMIT_FAILED'}
    $result | ConvertTo-Json -Depth 15
} catch {
    # Before COMMIT, restore the exact action first, then ask the leased gate to
    # restore config/runtime. After an uncertain commit keep marker/HOLD/backup.
    if($gate -and -not $gate.HasExited -and $taskChanged -and -not $commitSent -and $gateReady){
        try {
            Set-ScheduledTask -TaskName $TaskName -TaskPath $task.TaskPath -Action $oldAction | Out-Null
            $gateInput.WriteLine('ROLLBACK');$gateInput.Flush()
            $null=Read-GateLine;$gateInput.Close();Wait-GateExit
        } catch { }
    } elseif($gate -and -not $gate.HasExited -and -not $commitSent -and $gateReady){
        try {$gateInput.WriteLine('ROLLBACK');$gateInput.Flush();$null=Read-GateLine;$gateInput.Close();Wait-GateExit}catch{}
    }
    $reason=$_.Exception.Message
    if($reason -cnotmatch '^[A-Z][A-Z0-9_]{1,119}$'){$reason='PRIVATE_IO_SCHEMA_OR_GATE_FAILURE'}
    [ordered]@{schema='atlas.ws.operator-result.v1';status='WS_OPERATOR_BLOCKED';reason=$reason;
        hold_preserved=$true;task_started=$false;private_failure=$privateFailure;orders=0;trading_authority='NONE'} | ConvertTo-Json -Depth 10 -Compress
    exit 2
} finally {
    if($gate){
        if(-not $gate.HasExited){
            try {if($gateInput){$gateInput.Close()};if(-not $gate.WaitForExit(5000)){$gate.Kill();$null=$gate.WaitForExit(5000)}}catch{}
        }
        $gate.Dispose()
    }
    if($lock){$lock.Dispose()}
}
