# Called as the sole action of the EXISTING daily task after authorized binding.
# The original action finishes successfully before the warehouse imports output.
[CmdletBinding()]
param([Parameter(Mandatory)][string]$BindingFile)
$ErrorActionPreference = 'Stop'
$fullBinding = [IO.Path]::GetFullPath($BindingFile)
if (-not $fullBinding.StartsWith('E:\ATLAS\DataWarehouse\catalog\',[StringComparison]::OrdinalIgnoreCase)) { throw 'BINDING_PATH_ESCAPE' }
$bindingPin = [IO.Path]::GetFileNameWithoutExtension($fullBinding)
if ((Get-FileHash -LiteralPath $fullBinding -Algorithm SHA256).Hash.ToLowerInvariant() -cne $bindingPin) { throw 'BINDING_HASH_MISMATCH' }
$selfPin = [IO.Path]::GetFileNameWithoutExtension($PSCommandPath)
if ((Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $selfPin) { throw 'HOOK_HASH_MISMATCH' }
$binding = Get-Content -LiteralPath $BindingFile -Raw | ConvertFrom-Json
if ($binding.schema -ne 'aql.warehouse.daily-binding.v1' -or
    $binding.task -ne 'ATLAS-Research-Sustained-BTCUSDT-Daily' -or
    $binding.root -ine 'E:\ATLAS\DataWarehouse') { throw 'DAILY_BINDING_SCOPE' }
$start = @{FilePath=[string]$binding.execute;Wait=$true;PassThru=$true;NoNewWindow=$true}
if ($binding.arguments) { $start.ArgumentList = [string]$binding.arguments }
if ($binding.working_directory) { $start.WorkingDirectory = [string]$binding.working_directory }
$process = Start-Process @start
if ($process.ExitCode -ne 0) { throw "ORIGINAL_DAILY_ACTION_EXIT_$($process.ExitCode)" }
& $binding.python -B -m aql.warehouse.daily --root $binding.root --input-directory $binding.input_directory
if ($LASTEXITCODE -ne 0) { throw "WAREHOUSE_DAILY_IMPORT_EXIT_$LASTEXITCODE" }
