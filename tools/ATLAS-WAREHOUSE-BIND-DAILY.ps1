# Prepare is read-only. Activate requires a scoped host-task change reference,
# exact current task XML hash, installed package and retained 1m output directory.
[CmdletBinding()]
param(
    [ValidateSet('Prepare','Activate')][string]$Mode = 'Prepare',
    [string]$DailyArchiveRoot,
    [string]$Python = 'python',
    [string]$ExpectedTaskXmlSha256,
    [string]$HostTaskChangeRef
)
$ErrorActionPreference = 'Stop'
$taskName = 'ATLAS-Research-Sustained-BTCUSDT-Daily'
$root = 'E:\ATLAS\DataWarehouse'
$task = Get-ScheduledTask -TaskName $taskName
if (@($task.Actions).Count -ne 1) { throw 'EXISTING_SINGLE_EXEC_ACTION_REQUIRED' }
$action = $task.Actions[0]
if (-not $action.Execute) { throw 'EXEC_ACTION_REQUIRED' }
$xml = Export-ScheduledTask -TaskName $taskName
$hash = [BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($xml))).Replace('-','').ToLowerInvariant()
if ($Mode -eq 'Prepare') {
    [ordered]@{task=$taskName;xml_sha256=$hash;actions=1;state=[string]$task.State;
        original_executable=[string]$action.Execute;source_interval_required='1m';
        daily_archive_root=$DailyArchiveRoot;changes=0;
        activation='Run this same script with -Mode Activate -ExpectedTaskXmlSha256 <this hash> -HostTaskChangeRef <scoped owner permission> -DailyArchiveRoot <existing retained 1m ZIP directory> -Python <installed environment python.exe>'} | ConvertTo-Json
    return
}
if (-not $HostTaskChangeRef -or $hash -cne $ExpectedTaskXmlSha256) { throw 'HOST_AUTHORITY_OR_TASK_XML_PIN_REQUIRED' }
if (-not $DailyArchiveRoot -or -not (Test-Path -LiteralPath $DailyArchiveRoot -PathType Container)) { throw 'EXISTING_1M_ARCHIVE_DIRECTORY_REQUIRED' }
if ([IO.Path]::GetFullPath($DailyArchiveRoot).StartsWith($root,[StringComparison]::OrdinalIgnoreCase)) { throw 'DAILY_INPUT_MUST_BE_SEPARATE' }
# Validate importer and approved-root policy BEFORE updating the existing task.
& $Python -c 'import aql.warehouse.daily; from aql.warehouse.engine import HistoricalWarehouse; w=HistoricalWarehouse("E:/ATLAS/DataWarehouse"); print(w.report()["source_class"])'
if ($LASTEXITCODE -ne 0) { throw 'INSTALLED_PACKAGE_AND_WAREHOUSE_REQUIRED' }
$binding = [ordered]@{schema='aql.warehouse.daily-binding.v1';task=$taskName;root=$root;
    execute=[string]$action.Execute;arguments=[string]$action.Arguments;
    working_directory=[string]$action.WorkingDirectory;input_directory=[IO.Path]::GetFullPath($DailyArchiveRoot);
    python=(Get-Command $Python).Source;original_xml_sha256=$hash;host_task_change_ref=$HostTaskChangeRef}
# Binding files are private and confined by the warehouse writer. Originals,
# including the task XML and executable hook bytes, are saved create-only.
$payload = $binding | ConvertTo-Json -Compress
$hook = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'ATLAS-WAREHOUSE-DAILY-HOOK.ps1'))
$env:ATLAS_WAREHOUSE_BINDING_PAYLOAD = $payload
$env:ATLAS_WAREHOUSE_BINDING_XML = $xml
$env:ATLAS_WAREHOUSE_BINDING_HOOK = $hook
try {
    $paths = & $Python -c @'
import os,json
from aql.warehouse.engine import HistoricalWarehouse
from aql.warehouse.storage import seal
w=HistoricalWarehouse('E:/ATLAS/DataWarehouse')
with w.writer():
    out={}
    for key,suffix in [('PAYLOAD','json'),('XML','xml'),('HOOK','ps1')]:
        raw=os.environ['ATLAS_WAREHOUSE_BINDING_'+key].encode('utf-8')
        out[key]=str(w.write_once('catalog/'+seal(raw)+'.'+suffix,raw))
    print(json.dumps(out))
'@
    if ($LASTEXITCODE -ne 0) { throw 'BINDING_CUSTODY_FAILED' }
    $saved = $paths | ConvertFrom-Json
} finally {
    Remove-Item Env:ATLAS_WAREHOUSE_BINDING_PAYLOAD,Env:ATLAS_WAREHOUSE_BINDING_XML,Env:ATLAS_WAREHOUSE_BINDING_HOOK -ErrorAction SilentlyContinue
}
$taskAgain = Export-ScheduledTask -TaskName $taskName
if ($taskAgain -cne $xml) { throw 'TASK_CHANGED_DURING_PREPARATION' }
$newAction = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument "-NoProfile -NonInteractive -File `"$($saved.HOOK)`" -BindingFile `"$($saved.PAYLOAD)`""
# No new task, trigger, principal, settings, enabled state or immediate start.
Set-ScheduledTask -TaskName $taskName -Action $newAction | Out-Null
$readback = Get-ScheduledTask -TaskName $taskName
if ($readback.Actions[0].Arguments -cne $newAction.Arguments) { throw 'TASK_ACTION_READBACK_FAILED' }
[ordered]@{status='EXISTING_DAILY_ACTION_BOUND_WAITING_SCHEDULED_EVIDENCE';task=$taskName;
    original_xml=$saved.XML;binding=$saved.PAYLOAD;schedule_changes=0;principal_changes=0;
    original_execution='PRESERVED_FIRST';orders_enabled=$false} | ConvertTo-Json
