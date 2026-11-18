param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][string]$MarkerSha256,
    [switch]$CheckOnly
)
$ErrorActionPreference='Stop'
$parent=[IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'ATLAS-May08-Operations-bdf91943'))
$target=[IO.Path]::GetFullPath($Root)
if ((Split-Path -Parent $target) -cne $parent -or (Split-Path -Leaf $target) -notmatch '^stage6-durable-[A-Za-z0-9-]+$') {
    throw 'STAGE6_CLEANUP_TARGET_DENIED'
}
if (-not (Test-Path -LiteralPath $target)) { exit 0 }
$item=Get-Item -LiteralPath $target
if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'STAGE6_REPARSE_DENIED' }
$marker=Join-Path $target 'retention-owner.json'
if ((Get-FileHash -LiteralPath $marker -Algorithm SHA256).Hash -ine $MarkerSha256) {
    throw 'STAGE6_CLEANUP_MARKER_CHANGED'
}
$policy=Get-Content -LiteralPath $marker -Raw|ConvertFrom-Json
if ($policy.scope -cne 'ATLAS_STAGE6_ISOLATED_TEST' -or $policy.root -cne $target) {
    throw 'STAGE6_CLEANUP_SCOPE_DENIED'
}
if ($CheckOnly) { 'STAGE6_CLEANUP_TARGET_VERIFIED';exit 0 }
if ([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() -lt [long]$policy.expires_ms) {
    throw 'STAGE6_RETENTION_NOT_EXPIRED'
}
if (@(Get-ChildItem -LiteralPath $target -Recurse -Force |
        Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) {
    throw 'STAGE6_NESTED_REPARSE_DENIED'
}
Remove-Item -LiteralPath $target -Recurse -Force
'STAGE6_EXPIRED_ARTIFACT_REMOVED'
