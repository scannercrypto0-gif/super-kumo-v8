[CmdletBinding()]
param(
    [ValidateSet('Inspect','Backfill','DailyImport','Report')][string]$Mode = 'Inspect',
    [string]$Root = 'E:\ATLAS\DataWarehouse',
    [string]$Python = 'python',
    [string]$AuthorizationFile,
    [string]$DailyArchiveRoot,
    [ValidateRange(1,10000)][int]$ArchiveLimit = 10000
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$taskName = 'ATLAS-Research-Sustained-BTCUSDT-Daily'
if ([IO.Path]::GetFullPath($Root).TrimEnd('\') -ine 'E:\ATLAS\DataWarehouse') {
    throw 'APPROVED_ROOT_REQUIRED'
}
Push-Location $repo
$oldPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = "$repo\src;$repo"
    if ($Mode -eq 'Inspect') {
        & $Python -m aql.research_warehouse_plan --root $Root
        if ($LASTEXITCODE -ne 0) { throw 'CAPACITY_PREFLIGHT_FAILED' }
        $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($null -eq $task) {
            [ordered]@{task=$taskName;status='EXISTING_TASK_NOT_FOUND';mutations=0} | ConvertTo-Json
        } else {
            # Do not print task arguments: they may contain private configuration.
            [ordered]@{task=$taskName;state=[string]$task.State;actions=@($task.Actions).Count;
                executables=@($task.Actions | ForEach-Object {$_.Execute});
                schedule_changes=0;permission_changes=0;activation='NOT_PERFORMED';
                next='Bind existing action to daily retained-import hook after scoped host authorization';
                required_archive_interval='1m';daily_archive_root=$DailyArchiveRoot} | ConvertTo-Json
        }
    } elseif ($Mode -eq 'Backfill') {
        if (-not $AuthorizationFile) { throw 'SCOPED_SOURCE_AUTHORIZATION_FILE_REQUIRED' }
        & $Python -m aql.warehouse.runner backfill --root $Root --authorization $AuthorizationFile --archive-limit $ArchiveLimit
        if ($LASTEXITCODE -ne 0) { throw "WAREHOUSE_RUN_EXIT_$LASTEXITCODE" }
    } elseif ($Mode -eq 'DailyImport') {
        if (-not $DailyArchiveRoot) { throw 'EXISTING_DAILY_OUTPUT_DIRECTORY_REQUIRED' }
        & $Python -m aql.warehouse.daily --root $Root --input-directory $DailyArchiveRoot
        if ($LASTEXITCODE -ne 0) { throw "DAILY_IMPORT_EXIT_$LASTEXITCODE" }
    } else {
        & $Python -m aql.warehouse.runner report --root $Root
        if ($LASTEXITCODE -ne 0) { throw "REPORT_EXIT_$LASTEXITCODE" }
    }
} finally {
    $env:PYTHONPATH = $oldPythonPath
    Pop-Location
}
