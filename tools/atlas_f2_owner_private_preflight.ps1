# ATLAS F2 owner-local read-only preflight; no source mutation or diagnostic execution.
# Example: pwsh -NoProfile -File tools/atlas_f2_owner_private_preflight.ps1 -RecoveryFile 'E:\ATLAS\diagnostic-runner\f2-recovery-evidence.json' -MappingFile '...' -FactoryInputFile '...' -WarehouseRoot '...' -VaultRoot '...'
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$RecoveryFile,
  [Parameter(Mandatory=$true)][string]$MappingFile,
  [Parameter(Mandatory=$true)][string]$FactoryInputFile,
  [Parameter(Mandatory=$true)][string]$WarehouseRoot,
  [Parameter(Mandatory=$true)][string]$VaultRoot
)
$ErrorActionPreference = 'Stop'
$failed = $false
function Gate([string]$Code, [bool]$Ok) {
  if ($Ok) { Write-Output "PASS $Code" }
  else { Write-Output "PRIVATE_WAIT $Code"; $script:failed = $true }
}
$expectedBytes = '52b47d7d93f5966fffe41ae16cb21486fb14a0753a2821dccc35f4f09e4903d2'
$expectedInternal = '0428e7b02b7b57bded9906c49f956b76816c179cd8659d61e1c7f1af1df68220'
$months = @('2024-01','2024-03','2024-04','2024-05','2024-06','2024-07','2024-09','2024-10','2024-11','2024-12')
Gate 'RECOVERY_FILE_EXISTS' (Test-Path -LiteralPath $RecoveryFile -PathType Leaf)
Gate 'MAPPING_FILE_EXISTS' (Test-Path -LiteralPath $MappingFile -PathType Leaf)
Gate 'FACTORY_INPUT_FILE_EXISTS' (Test-Path -LiteralPath $FactoryInputFile -PathType Leaf)
Gate 'WAREHOUSE_ROOT_EXISTS' (Test-Path -LiteralPath $WarehouseRoot -PathType Container)
Gate 'VAULT_ROOT_EXISTS' (Test-Path -LiteralPath $VaultRoot -PathType Container)
if (Test-Path -LiteralPath $RecoveryFile -PathType Leaf) {
  $sha = (Get-FileHash -LiteralPath $RecoveryFile -Algorithm SHA256).Hash.ToLowerInvariant()
  Gate 'OWNER_REPORT_RAW_BYTES_SHA' ($sha -ceq $expectedBytes)
  if ($sha -ceq $expectedBytes) {
    try {
      $report = Get-Content -LiteralPath $RecoveryFile -Raw -Encoding UTF8 | ConvertFrom-Json
      Gate 'OWNER_REPORT_INTERNAL_SHA' ($report.recovery_sha256 -ceq $expectedInternal)
      Gate 'OWNER_REPORT_SCHEMA' ($report.schema -ceq 'aql.owner-local.f2-recovery-evidence.v1')
      Gate 'OWNER_REPORT_DISPOSITION' ($report.disposition -ceq 'OWNER_LOCAL_DUAL_READBACK_PASS')
      Gate 'OWNER_REPORT_CENSUS' (($report.verified_months -is [int] -or $report.verified_months -is [long]) -and $report.verified_months -eq 10 -and $report.verified_bars -eq 29376)
      $entries = @($report.entries)
      Gate 'OWNER_REPORT_MONTHS' ($entries.Count -eq 10 -and @($entries | ForEach-Object month | Sort-Object -Unique).Count -eq 10 -and @($entries | Where-Object { $months -cnotcontains $_.month }).Count -eq 0)
    } catch {
      Gate 'OWNER_REPORT_PARSE' $false
    }
  }
}
if (Test-Path -LiteralPath $MappingFile -PathType Leaf) {
  try {
    $mapping = Get-Content -LiteralPath $MappingFile -Raw -Encoding UTF8 | ConvertFrom-Json
    Gate 'UNTRUSTED_MAPPING_SCHEMA' ($mapping.schema -ceq 'aql.integration.f2-recovery-evidence.v1' -and @($mapping.entries).Count -eq 10)
    Gate 'MAPPING_PARENTS_PRESENT' (@($mapping.entries | Where-Object {
      [string]::IsNullOrWhiteSpace($_.warehouse_receipt_sha256) -or
      [string]::IsNullOrWhiteSpace($_.dual_query_map_sha256)
    }).Count -eq 0)
  } catch { Gate 'UNTRUSTED_MAPPING_PARSE' $false }
}
if (Test-Path -LiteralPath $FactoryInputFile -PathType Leaf) {
  try {
    $factory = Get-Content -LiteralPath $FactoryInputFile -Raw -Encoding UTF8 | ConvertFrom-Json
    Gate 'FACTORY_PACKET_SCHEMA' ($factory.schema -ceq 'aql.factory.f.f2-recovery-evidence-diagnostic-input.v1')
    Gate 'FACTORY_NOT_ORIGINAL_F2' ($null -eq $factory.original_f2_report_sha256)
  } catch { Gate 'FACTORY_PACKET_PARSE' $false }
}
if ($failed) { Write-Output 'PRIVATE_WAIT: preflight only; do not run research operator'; exit 2 }
Write-Output 'PREFLIGHT_INPUTS_PRESENT_NOT_ATTESTED: run Core/Scanner/Factory independent readback only after exact-head local overlay and owner authorization'
exit 0
