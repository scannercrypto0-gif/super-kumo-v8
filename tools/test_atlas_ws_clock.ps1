$ErrorActionPreference='Stop'
$functionTexts=@()
foreach($path in @('atlas_ws_resilience_windows.ps1','atlas_live_research_service_windows.ps1')){
    $ast=[System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot $path),[ref]$null,[ref]$null)
    $texts=@()
    foreach($name in @('Measure-ClockSamples','Read-ClockProbe','Qualified-Clock')){
        $f=$ast.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name},$true)
        if(!$f){throw 'CLOCK_HELPER_MISSING'}
        $texts+=($f.Extent.Text)
        . ([scriptblock]::Create($f.Extent.Text))
    }
    $functionTexts+=($texts -join "`n")
}
if($functionTexts[0] -cne $functionTexts[1]){throw 'OPERATOR_SERVICE_CLOCK_DRIFT'}
# Numeric evidence transcribed exactly from owner w32tm output, 2026-11-22 14:51 Riyadh.
$fixture=@'
14:51:20, d:+00.0795797s o:+00.0340284s
Leap Indicator: 0(no warning)
Root Delay: 0x0000.047E (+00.0175476s)
Root Dispersion: 0x0000.0008 (0.0001221s)
14:51:21, d:+00.0883368s o:+00.0273249s
Leap Indicator: 0(no warning)
Root Delay: 0x0000.0482 (+00.0176086s)
Root Dispersion: 0x0000.0016 (0.0003357s)
14:51:22, d:+00.0907275s o:+00.0270018s
Leap Indicator: 0(no warning)
Root Delay: 0x0000.0475 (+00.0174103s)
Root Dispersion: 0x0000.0015 (0.0003204s)
14:51:23, d:+00.0787388s o:+00.0326532s
Leap Indicator: 0(no warning)
Root Delay: 0x0000.0482 (+00.0176086s)
Root Dispersion: 0x0000.0017 (0.0003510s)
'@
$priorCulture=[Threading.Thread]::CurrentThread.CurrentCulture
try{
    foreach($culture in @('en-US','de-DE','ar-SA')){
        [Threading.Thread]::CurrentThread.CurrentCulture=[Globalization.CultureInfo]::GetCultureInfo($culture)
        if((Measure-ClockSamples $fixture).uncertainty_ms -ne 103){throw 'OWNER_SAMPLE_NOT_103_MS'}
    }
}finally{[Threading.Thread]::CurrentThread.CurrentCulture=$priorCulture}
$script:probeCalls=0
function Read-ClockProbe {$script:probeCalls++;if($script:probeCalls -eq 1){return 'missing packets'};return $fixture}
$r=Qualified-Clock
if($script:probeCalls -ne 2 -or $r.probe_attempts -ne 2 -or $r.prior_failures[0].reason -cne 'HOST_CLOCK_SAMPLE_INVALID'){throw 'TRANSIENT_PROBE_RECOVERY_FAILED'}
$script:probeCalls=0
function Read-ClockProbe {$script:probeCalls++;return 'missing packets'}
$caught=$false
try{$null=Qualified-Clock}catch{$caught=$_.Exception.Message -ceq 'HOST_CLOCK_SAMPLE_INVALID'}
if(!$caught -or $script:probeCalls -ne 3 -or $script:clockFailure.attempts.Count -ne 3){throw 'CLOCK_RETRY_NOT_BOUNDED'}
$script:probeCalls=0
function Read-ClockProbe {$script:probeCalls++;return ($fixture.Replace('o:+00.0340284s','o:+01.0340284s'))}
$caught=$false
try{$null=Qualified-Clock}catch{$caught=$_.Exception.Message -ceq 'HOST_CLOCK_UNCERTAINTY'}
if(!$caught -or $script:probeCalls -ne 1){throw 'UNCERTAIN_CLOCK_RETRIED_OR_ACCEPTED'}
$script:probeCalls=0
function Read-ClockProbe {$script:probeCalls++;throw 'UNKNOWN_PRIVATE_FAILURE'}
try{$null=Qualified-Clock}catch{}
if($script:probeCalls -ne 1){throw 'UNKNOWN_CLOCK_FAILURE_RETRIED'}
Write-Output 'WS_OWNER_CLOCK_103MS_AND_BOUNDED_RECOVERY_PASS'
