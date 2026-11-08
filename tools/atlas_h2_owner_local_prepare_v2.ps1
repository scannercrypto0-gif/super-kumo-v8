# ATLAS H2 OWNER key identity enrollment/revocation (Windows PS5.1).
# Only the owner explicitly runs this locally. NO E: reads, original H2,
# existing key adoption, fabrication of evidence, stdout secret or Git upload.
[CmdletBinding(DefaultParameterSetName='Inspect')]
param(
  [Parameter(ParameterSetName='Enroll', Mandatory=$true)][switch]$EnrollNewIdentity,
  [Parameter(ParameterSetName='Revoke', Mandatory=$true)][switch]$RevokeCurrentIdentity,
  [Parameter(ParameterSetName='Revoke', Mandatory=$true)][switch]$ConfirmRevocation,
  [Parameter(ParameterSetName='Inspect')][switch]$Inspect,
  [string]$OutputRoot = ''
)
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'OWNER_WINDOWS_ONLY_ACL_REQUIRED' }
$root = [Environment]::GetFolderPath('LocalApplicationData')
if ([string]::IsNullOrWhiteSpace($root)) { throw 'PRIVATE_LOCAL_PROFILE_NOT_AVAILABLE' }
$expected = Join-Path $root 'ATLAS\H2-Local-Batch\owner-identity-v2'
if (-not $OutputRoot) { $OutputRoot = $expected }
if ([IO.Path]::GetFullPath($OutputRoot).TrimEnd('\') -cne [IO.Path]::GetFullPath($expected).TrimEnd('\')) {
  throw 'OWNER_IDENTITY_ROOT_MUST_MATCH_PROFILE'
}
$identityFile = Join-Path $expected 'owner-identity.json'
$keyFile = Join-Path $expected 'owner-signing.key'
$registry = Join-Path $expected 'owner-revocations.json'
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
if (-not (Test-Path -LiteralPath $expected -PathType Container)) {
  if ($PSCmdlet.ParameterSetName -eq 'Inspect') { Write-Host 'OWNER_IDENTITY_NOT_ENROLLED'; exit 2 }
  New-Item -LiteralPath $expected -ItemType Directory -Force | Out-Null
}
if ((Get-Item -LiteralPath $expected -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
  throw 'OWNER_IDENTITY_SYMLINK_DENIED'
}
# Explicit deny inherited ACL. Owner SID and local SYSTEM only, full access.
$acl = New-Object System.Security.AccessControl.DirectorySecurity
$acl.SetAccessRuleProtection($true, $false)
$ownerPrincipal = New-Object System.Security.Principal.SecurityIdentifier($sid)
$systemPrincipal = New-Object System.Security.Principal.SecurityIdentifier('S-1-5-18')
foreach ($p in @($ownerPrincipal,$systemPrincipal)) {
  $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
    $p, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
  $acl.AddAccessRule($rule)
}
Set-Acl -LiteralPath $expected -AclObject $acl
if ($EnrollNewIdentity) {
  if ((Test-Path -LiteralPath $keyFile) -or (Test-Path -LiteralPath $identityFile)) {
    throw 'OWNER_EXISTING_IDENTITY_NO_OVERWRITE_USE_EXPLICIT_ROTATION_POLICY'
  }
  $key = New-Object byte[] 32
  $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
  try { $rng.GetBytes($key) } finally { $rng.Dispose() }
  try {
    # Explicit exclusive create; never print key or include in reports.
    $file = New-Object System.IO.FileStream(
      $keyFile, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write,
      [IO.FileShare]::None)
    try { $file.Write($key,0,$key.Length); $file.Flush($true) }
    finally { $file.Dispose() }
    $hash = [Security.Cryptography.SHA256]::Create()
    try {
      $prefix = [Text.Encoding]::UTF8.GetBytes('ATLAS-H2-OWNER-IDENTITY-V2')
      $blob = New-Object byte[] ($prefix.Length + 1 + $key.Length)
      [Array]::Copy($prefix,0,$blob,0,$prefix.Length)
      [Array]::Copy($key,0,$blob,($prefix.Length+1),$key.Length)
      $id = ([BitConverter]::ToString($hash.ComputeHash($blob))).Replace('-','').ToLowerInvariant()
      [Array]::Clear($blob,0,$blob.Length)
    } finally { $hash.Dispose() }
  } finally { [Array]::Clear($key,0,$key.Length) }
  $time = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
  $metadata = [ordered]@{
    schema = 'aql.integration.h2.owner-identity.v2'
    key_id = $id
    created_at_utc = $time
    activation = 'FORWARD_ONLY'
    custody = 'OWNER_LOCAL'
    rights_class = 'OWNER_PERSONAL_NOT_EXTERNAL'
  }
  $metadata | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $identityFile -Encoding UTF8
  if (-not (Test-Path -LiteralPath $registry)) {
    @{schema='aql.integration.h2.owner-revocations.v2';revoked_key_ids=@()} |
      ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $registry -Encoding UTF8
  }
  # Child files inherit only owner and SYSTEM from restricted parent.
  Write-Host ('NEW_FORWARD_ONLY_OWNER_KEY_ID: '+$id)
  Write-Host ('CREATED_AT_UTC: '+$time)
  Write-Host 'OWNER_CUSTODY_ACTION_REQUIRED: independently preserve local key and confirm control'
  Write-Host 'NO_H2_RUN; NO_RETROACTIVE_SIGNATURE; NO_SOURCE_ACCESS'
  exit 0
}
if (-not (Test-Path -LiteralPath $identityFile -PathType Leaf) -or
    -not (Test-Path -LiteralPath $registry -PathType Leaf)) {
  throw 'OWNER_IDENTITY_OR_REVOCATION_REGISTRY_MISSING'
}
$identity = Get-Content -LiteralPath $identityFile -Raw | ConvertFrom-Json
$revs = Get-Content -LiteralPath $registry -Raw | ConvertFrom-Json
if ($identity.schema -ne 'aql.integration.h2.owner-identity.v2' -or
    $revs.schema -ne 'aql.integration.h2.owner-revocations.v2') {
  throw 'OWNER_IDENTITY_METADATA_SCHEMA_DRIFT'
}
if ($RevokeCurrentIdentity) {
  if (-not $ConfirmRevocation) { throw 'EXPLICIT_REVOCATION_CONFIRMATION_REQUIRED' }
  if ($revs.revoked_key_ids -notcontains $identity.key_id) {
    $new = @($revs.revoked_key_ids) + @($identity.key_id)
    $pending = Join-Path $expected 'owner-revocations.pending.json'
    if (Test-Path -LiteralPath $pending) { throw 'OWNER_REVOCATION_PENDING_PRESENT' }
    @{schema='aql.integration.h2.owner-revocations.v2';revoked_key_ids=$new} |
      ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $pending -Encoding UTF8
    Move-Item -LiteralPath $pending -Destination $registry -Force
  }
  Write-Host ('OWNER_IDENTITY_REVOKED: '+$identity.key_id)
  Write-Host 'PREVIOUS SIGNED FUTURE ATTEMPTS MUST FAIL CLOSED; KEY NOT DELETED AUTOMATICALLY'
  exit 0
}
$status = if ($revs.revoked_key_ids -contains $identity.key_id) {'REVOKED'} else {'ACTIVE_METADATA_ONLY'}
Write-Host ('OWNER_KEY_ID: '+$identity.key_id)
Write-Host ('CREATED_AT_UTC: '+$identity.created_at_utc)
Write-Host ('STATE: '+$status)
Write-Host 'THIS IS NOT OWNER_SIGNATURE, COST_APPROVAL OR ORIGINAL H2'
