[CmdletBinding()]
param(
  [Parameter(Mandatory)][string]$ExpectedCommit,
  [ValidateSet('Inspect','Monitor')][string]$Mode='Inspect',
  [string]$ConfigFile,
  [string]$FullHistoryReceipt,
  [string]$Python='python',
  [switch]$ConfirmHostActivation,
  [switch]$Continuous
)
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$head=& git -C $repo rev-parse HEAD
if($LASTEXITCODE -ne 0 -or $head -cne $ExpectedCommit){throw 'EXACT_REVIEWED_COMMIT_REQUIRED'}
& git -C $repo diff --quiet HEAD -- tools
if($LASTEXITCODE -ne 0){throw 'REVIEWED_TOOLS_MODIFIED'}
if($Mode -eq 'Inspect'){
  $summary=[ordered]@{schema='atlas.operational016.preflight.v1';host_changes=0;source_calls=0;orders=0;trading_authority='NONE';full_history='TERMINAL_RECEIPT_REQUIRED';daily='NOT_INSPECTED';activation='NOT_PERFORMED'}
  try{
    $task=Get-ScheduledTask -TaskName 'ATLAS-Research-Sustained-BTCUSDT-Daily' -ErrorAction Stop
    $summary.daily=[string]$task.State
    $xml=Export-ScheduledTask -TaskName $task.TaskName
    $hash=[Security.Cryptography.SHA256]::Create()
    try{$summary.daily_xml_sha256=[BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($xml))).Replace('-','').ToLowerInvariant()}finally{$hash.Dispose()}
  }catch{$summary.daily='READ_ONLY_TASK_INSPECTION_UNAVAILABLE'}
  if($ConfigFile){ & $Python -B "$PSScriptRoot\atlas_operational_016.py" --config $ConfigFile --inspect-config; if($LASTEXITCODE -ne 0){throw 'CONFIG_INSPECTION_BLOCKED'} }
  if($FullHistoryReceipt){
    & $Python -B "$PSScriptRoot\atlas_operational_016.py" --receipt $FullHistoryReceipt --exit-code 2
    $summary.full_history=if($LASTEXITCODE -eq 0){'TERMINAL_RECEIPT_CLASSIFIED_SEPARATELY'}else{'RECEIPT_VALIDATION_BLOCKED'}
  }
  $summary|ConvertTo-Json -Depth 5
  exit 0
}
if(-not $ConfirmHostActivation -or -not $ConfigFile){throw 'ONE_SCOPED_HOST_ACTIVATION_AND_CONFIG_REQUIRED'}
# Existing producer/scheduler/warehouse processes are never started or changed.
$argsList=@('-B',"$PSScriptRoot\atlas_operational_016.py",'--config',$ConfigFile)
if($Continuous){$argsList+='--continuous'}
& $Python @argsList
exit $LASTEXITCODE
