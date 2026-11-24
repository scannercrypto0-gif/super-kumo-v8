[CmdletBinding()]
param([Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{40}$')][string]$ExpectedCommit,
      [Parameter(Mandatory=$true)][string]$OwnerDecisionRef)
# Manual two-connection diagnostic, not recovery or service activation.
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$head=& git -C $repo rev-parse HEAD
if($LASTEXITCODE -or $head -cne $ExpectedCommit){throw 'EXACT_COMPARISON_COMMIT_REQUIRED'}
$tasks=@(Get-ScheduledTask -TaskName 'ATLAS-Research-Sustained-Spot-WS')
if($tasks.Count -ne 1 -or @($tasks[0].Actions).Count -ne 1 -or [string]$tasks[0].State -cne 'Ready'){throw 'COMPARISON_TASK_NOT_HELD_READY'}
$m=[regex]::Match($tasks[0].Actions[0].Arguments,'(?i)(?:^|\s)-Config\s+(?:"([^"]+)"|''([^'']+)''|(\S+))')
if(!$m.Success){throw 'COMPARISON_CONFIG_PATH'}
$config=[Environment]::ExpandEnvironmentVariables(($m.Groups[1].Value+$m.Groups[2].Value+$m.Groups[3].Value))
$root=Split-Path -Parent $config
$cfg=Get-Content -LiteralPath $config -Raw|ConvertFrom-Json
$collectors=@(Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -match '(?i)atlas_live_research_cycle(?:\.py)?\s+live|atlas_single_receipt_runner|binance_live_feed[./\\]runner|atlas_ws_network_compare\.py'})
if($collectors.Count){throw 'COMPARISON_COMPETING_COLLECTOR'}
$routes=@(Get-NetRoute -DestinationPrefix '0.0.0.0/0'|Select-Object -ExpandProperty InterfaceAlias -Unique)
if($routes.Count -ne 1 -or $routes[0] -cne 'Ethernet'){throw 'COMPARISON_ROUTE_CHANGED'}
$inet=Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
if($inet.ProxyEnable -or $inet.AutoConfigURL -or @(Get-ChildItem Env:|Where-Object Name -match '^(HTTPS?_PROXY|ALL_PROXY)$').Count -or
    !(netsh winhttp show proxy|Select-String 'Direct access')){throw 'COMPARISON_PROXY_CHANGED'}
$lock=$null;$process=$null
try{
    $lock=[IO.File]::Open((Join-Path $root 'supervisor.lock'),'Open','ReadWrite','None')
    $script=Join-Path $PSScriptRoot 'atlas_ws_network_compare.py'
    foreach($value in @($script,$config,$OwnerDecisionRef)){if($value.Contains('"')){throw 'COMPARISON_ARGUMENT_INVALID'}}
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$cfg.python
    $info.Arguments='-B "'+$script+'" --config "'+$config+'" --expected-commit '+$ExpectedCommit+' --owner-ref "'+$OwnerDecisionRef+'"'
    $info.UseShellExecute=$false;$info.CreateNoWindow=$true
    $info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    $info.StandardOutputEncoding=[Text.UTF8Encoding]::new($false);$info.StandardErrorEncoding=[Text.UTF8Encoding]::new($false)
    $process=[Diagnostics.Process]::new();$process.StartInfo=$info
    if(!$process.Start()){throw 'COMPARISON_PROCESS_START'}
    $stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync()
    Write-Output 'NETWORK_COMPARISON_RUNNING: two sequential readers, up to 15 minutes each; existing service stays HOLD.'
    if(!$process.WaitForExit(2400000)){throw 'COMPARISON_PROCESS_DEADLINE'}
    if(!$stdout.Wait(5000) -or !$stderr.Wait(5000)){throw 'COMPARISON_DRAIN_TIMEOUT'}
    if($stdout.Result.Length -gt 1048576 -or $stderr.Result.Length -gt 65536){throw 'COMPARISON_OUTPUT_BOUND'}
    if($process.ExitCode -ne 0){$stdout.Result|Write-Output;throw 'COMPARISON_BLOCKED_REVIEW_RESULT'}
    $stdout.Result|Write-Output
}finally{
    if($process){if(!$process.HasExited){$process.Kill();$null=$process.WaitForExit(5000)};$process.Dispose()}
    if($lock){$lock.Dispose()}
}
