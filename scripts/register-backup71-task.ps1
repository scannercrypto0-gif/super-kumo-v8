param(
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$Repository,
    [Parameter(Mandatory=$true)][string]$Config,
    [Parameter(Mandatory=$true)][string]$LogDirectory,
    [Parameter(Mandatory=$true)][string]$XmlOutput,
    [string]$TaskName='ATLAS Backup71 Daily',
    [ValidatePattern('^\d{2}:\d{2}$')][string]$At='02:00',
    [ValidateSet('Backup','Preflight','Health')][string]$Mode='Preflight',
    [switch]$Register
)
$ErrorActionPreference='Stop'
if (!$IsWindows -and $PSVersionTable.PSEdition -eq 'Core') { throw 'Windows Task Scheduler required' }
foreach ($value in @($Python,$Repository,$Config,$LogDirectory)) {
    if ($value.Contains('"') -or $value.Contains("`n") -or $value.Contains("`r")) { throw 'Unsafe argument' }
}
if (Test-Path -LiteralPath $XmlOutput) { throw 'XML output must be new; no replacement' }
# Preflight reads approved config/media/source/key without creating a backup.
$env:PYTHONPATH=Join-Path $Repository 'src'
& $Python -B -m aql.archive.automation backup --config $Config
if ($LASTEXITCODE -ne 0) { throw 'Preflight failed; task not registered' }
$wrapper=Join-Path $Repository 'scripts\backup71-task.ps1'
$hostPath=(Get-Process -Id $PID).Path
$arguments='-NoProfile -NonInteractive -File "'+$wrapper+'" -Python "'+$Python+'" -Repository "'+$Repository+'" -Config "'+$Config+'" -LogDirectory "'+$LogDirectory+'" -Mode '+$Mode
$action=New-ScheduledTaskAction -Execute $hostPath -Argument $arguments -WorkingDirectory $Repository
$trigger=New-ScheduledTaskTrigger -Daily -At $At
$settings=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$identity=[System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal=New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$task=New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal
$xml=Export-ScheduledTask -InputObject $task
$stream=[System.IO.File]::Open($XmlOutput,[System.IO.FileMode]::CreateNew,[System.IO.FileAccess]::Write,[System.IO.FileShare]::None)
$writer=[System.IO.StreamWriter]::new($stream,[System.Text.Encoding]::Unicode)
try { $writer.Write($xml); $writer.Flush(); $stream.Flush($true) }
finally { $writer.Dispose() }
if ($Register) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) { throw 'Existing task preserved; choose new task name' }
    Register-ScheduledTask -TaskName $TaskName -InputObject $task | Select-Object TaskName,State
} else { Write-Output 'XML_PREPARED_NOT_REGISTERED' }
# Interactive token avoids stored credentials/elevation. Runs only while this
# user is logged on; unattended logoff execution needs a separately scoped identity.
