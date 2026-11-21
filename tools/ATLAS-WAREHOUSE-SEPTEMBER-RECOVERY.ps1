[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ExpectedCommit,
    [ValidateSet('Diagnose','ApplyApprovedCorrection','RebuildRegistry','FullHistory')][string]$Mode = 'Diagnose',
    [string]$AuthorizationFile,
    [string]$Python = 'python',
    [string]$DailyArchiveRoot,
    [string]$Root = 'E:\ATLAS\DataWarehouse'
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
if ([IO.Path]::GetFullPath($Root).TrimEnd('\') -ine 'E:\ATLAS\DataWarehouse') { throw 'APPROVED_ROOT_REQUIRED' }
$actual = & git -C $repo rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $actual -cne $ExpectedCommit) { throw 'REVIEWED_COMMIT_REQUIRED' }
& git -C $repo diff --quiet HEAD -- src/aql/warehouse tools/ATLAS-WAREHOUSE-SEPTEMBER-RECOVERY.ps1
if ($LASTEXITCODE -ne 0) { throw 'REVIEWED_CODE_MODIFIED' }
$taskName = 'ATLAS-Research-Sustained-BTCUSDT-Daily'
$inspection = [ordered]@{task=$taskName;scheduler_changes=0;finite_action='NOT_PROVEN';
    original_1m_output='NOT_INSPECTED_NO_DIRECTORY';task_status='NOT_INSPECTED'}
if ($Mode -notin @('RebuildRegistry','FullHistory')) {
try {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
    $inspection.task_status = 'READ_ONLY_INSPECTED'
    $inspection.state = [string]$task.State
    $inspection.action_count = @($task.Actions).Count
    $xml = Export-ScheduledTask -TaskName $taskName
    $inspection.xml_sha256 = [BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($xml))).Replace('-','').ToLowerInvariant()
    $inspection.executables = @($task.Actions | ForEach-Object {$_.Execute})
    # Arguments/XML are deliberately not emitted: they can contain private data.
    $info = Get-ScheduledTaskInfo -TaskName $taskName
    $inspection.last_task_result = $info.LastTaskResult
} catch {
    $inspection.task_status = 'READ_ONLY_INSPECTION_UNAVAILABLE'
    $inspection.error_type = $_.Exception.GetType().Name
}
if ($DailyArchiveRoot) {
    if (-not (Test-Path -LiteralPath $DailyArchiveRoot -PathType Container)) { throw 'DAILY_ARCHIVE_DIRECTORY_MISSING' }
    $oneMinute = @(Get-ChildItem -LiteralPath $DailyArchiveRoot -Filter 'BTCUSDT-1m-*.zip' -File | Select-Object -First 1000)
    $pairs = @($oneMinute | Where-Object {Test-Path -LiteralPath ($_.FullName + '.CHECKSUM') -PathType Leaf})
    $inspection.original_1m_output = if ($pairs.Count) {'RETAINED_ZIP_CHECKSUM_PAIRS_SEEN_NOT_VALIDATED'} else {'NO_1M_ZIP_CHECKSUM_PAIRS_SEEN'}
    $inspection.pairs_seen_max_1000 = $pairs.Count
}
}
$oldPath = $env:PYTHONPATH
$oldInspection = $env:ATLAS_WAREHOUSE_RECOVERY_TASK_INSPECTION
Push-Location $repo
try {
    $env:PYTHONPATH = "$repo\src;$repo"
    $env:ATLAS_WAREHOUSE_RECOVERY_TASK_INSPECTION = $inspection | ConvertTo-Json -Depth 5 -Compress
    if ($Mode -eq 'RebuildRegistry') {
        $argsList = @('-B','-m','aql.warehouse.registry','--root',$Root)
    } elseif ($Mode -eq 'ApplyApprovedCorrection') {
        $argsList = @('-B','-m','aql.warehouse.september_correction','--root',$Root)
    } elseif ($Mode -eq 'FullHistory') {
        $argsList = @('-B','-m','aql.warehouse.full_history','--root',$Root)
        if ($AuthorizationFile) { $argsList += @('--authorization',$AuthorizationFile) }
    } else {
        $argsList = @('-B','-m','aql.warehouse.diagnose','--root',$Root,'--archive-limit','3')
        if ($AuthorizationFile) { $argsList += @('--authorization',$AuthorizationFile) }
    }
    & $Python @argsList
    $code = $LASTEXITCODE
} finally {
    $env:PYTHONPATH = $oldPath
    $env:ATLAS_WAREHOUSE_RECOVERY_TASK_INSPECTION = $oldInspection
    Pop-Location
}
# Code 2 reports a fatal stop, pending work or quarantined coverage; inspect the receipt.
exit $code
