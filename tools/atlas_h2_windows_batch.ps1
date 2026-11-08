# H2 one-batch Windows bootstrap. Never opens or edits existing working tree.
# The owner must supply a PRE-EXISTING independently authenticated private
# custody packet; this program never manufactures owner rights or source pins.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$EvidenceDir,
  [string]$OutputDir = '',
  [ValidateSet('strict-custodian','official-binance','owner-personal')][string]$Mode = 'strict-custodian',
  [string]$CustodianVerifierKey = '',
  [string]$LicenseReviewerKey = '',
  [string]$OwnerSigningKey = '',
  [switch]$ConfirmOneRun,
  [string]$Python = 'python',
  [string]$Git = 'git'
)
$ErrorActionPreference = 'Stop'
$bootstrapCommit = 'aa0f21bfcbb07d36258c5dca552310bb36f452c8'
$publicCommit = '5a976b8bf04f764b2822d49ff40cc5d60548494b'
$operatorCommit = '9a4ed276913eac202e0c77778371c91dc482ff23'
# Immutable owner-personal research-only route + early manual AST guard.
$personalCommit = '17b0d0216fcc3f76e36317def0a9751e3607c924'
$required = @(
  $bootstrapCommit,
  $publicCommit,
  $operatorCommit,
  '51f3724213e836fa680f589435e418d4b0c4c20f',
  '99c27ea2c1a4d41aaae361141301a8a9ea3b33c3',
  '3c82448702c9ae35783716e4e2c3b640010db97c',
  'a4b887fe7067b89febc339e466652a5fcb1c2bee',
  '6acbcc7fc243b132f58170df4c6469bbf7f4eff8'
)
if ($Mode -eq 'owner-personal') { $required += $personalCommit }
# Default results to a private profile path, not the original E: source.
$localData = [Environment]::GetFolderPath('LocalApplicationData')
if ([string]::IsNullOrWhiteSpace($localData)) {
  throw 'SAFE_LOCAL_PROFILE_OUTPUT_UNAVAILABLE'
}
$allowedOutputRoot = Join-Path $localData 'ATLAS\H2-Local-Batch'
if (-not $OutputDir) {
  $OutputDir = Join-Path $allowedOutputRoot ('run-' + [Guid]::NewGuid().ToString('N'))
}
$normalizedOutput = [IO.Path]::GetFullPath($OutputDir).TrimEnd('\')
$normalizedBase = [IO.Path]::GetFullPath($allowedOutputRoot).TrimEnd('\')
if (-not $normalizedOutput.StartsWith(($normalizedBase + '\'),
    [StringComparison]::OrdinalIgnoreCase)) {
  throw 'OUTPUT_MUST_BE_WITHIN_PRIVATE_LOCAL_PROFILE_ATLAS_H2'
}
$OutputDir = $normalizedOutput
if (-not (Test-Path -LiteralPath $OutputDir -PathType Container)) {
  New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}
Write-Host ('H2_LOCAL_REPORT_DIR: ' + $OutputDir)
# Never scan the user's E: drive or inspect Git working tree.
$root = Join-Path ([IO.Path]::GetTempPath()) ('aql-h2-batch-' + [Guid]::NewGuid().ToString('N'))
$clone = Join-Path $root 'pinned-repo'
$driver = Join-Path $root 'driver'
New-Item -ItemType Directory -Path $clone,$driver -Force | Out-Null
try {
  & $Git -C $clone init -q
  if ($LASTEXITCODE -ne 0) { throw 'GIT_INIT_FAILED' }
  & $Git -C $clone remote add origin 'https://github.com/scannercrypto0-gif/super-kumo-v8.git'
  if ($LASTEXITCODE -ne 0) { throw 'GIT_REMOTE_FAILED' }
  foreach ($sha in $required) {
    & $Git -C $clone fetch --quiet --no-tags origin $sha
    if ($LASTEXITCODE -ne 0) { throw ('PIN_UNAVAILABLE_' + $sha) }
    $actual = (& $Git -C $clone rev-parse --verify ($sha + '^{commit}')).Trim()
    if ($LASTEXITCODE -ne 0 -or $actual -cne $sha) {
      throw ('PIN_MISMATCH_' + $sha)
    }
  }
  $stageCode = @'
import pathlib, subprocess, sys
repo, target, bootstrap, operator, public = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5]
for sha,rel in (
    (bootstrap,'tools/atlas_h2_private_batch_bootstrap_v1.py'),
    (public,'tools/atlas_h2_binance_public_lane_v1.py'),
    (operator,'tools/atlas_h2_owner_local_one_shot_v1.py'),
    (operator,'tools/atlas_h2_historical_policy_v2.py')):
    p=target/rel
    p.parent.mkdir(parents=True,exist_ok=True)
    r=subprocess.run(['git','-C',str(repo),'show',sha+':'+rel],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if r.returncode: raise SystemExit('PINNED_BOOTSTRAP_SOURCE_UNAVAILABLE')
    p.write_bytes(r.stdout)
(target/'tools/__init__.py').touch()
'@
  & $Python -I -c $stageCode $clone $driver $bootstrapCommit $operatorCommit $publicCommit
  if ($LASTEXITCODE -ne 0) { throw 'STAGING_FAILED' }
  # Personal authority is a separate explicit, immutable 2026 research class.
  # Original licensed branch remains on its prior independently reviewed freeze.
  if ($Mode -eq 'owner-personal') {
    $stagePersonal = @'
import pathlib, subprocess, sys
repo, target, sha = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
for rel in (
    'tools/atlas_h2_owner_personal_batch_v1.py',
    'tools/atlas_h2_owner_research_authority_v1.py',
    'tools/atlas_h2_binance_public_lane_v1.py'):
    p=target/rel
    p.parent.mkdir(parents=True, exist_ok=True)
    r=subprocess.run(['git','-C',str(repo),'show',sha+':'+rel],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if r.returncode: raise SystemExit('PERSONAL_PINNED_CODE_NOT_AVAILABLE')
    p.write_bytes(r.stdout)
'@
    & $Python -I -c $stagePersonal $clone $driver $personalCommit
    if ($LASTEXITCODE -ne 0) { throw 'PERSONAL_STAGE_FAILED' }
  }
  $runner = @'
import sys
sys.path.insert(0,sys.argv[1])
if sys.argv[2] == 'official-binance':
    from tools.atlas_h2_binance_public_lane_v1 import main
elif sys.argv[2] == 'owner-personal':
    from tools.atlas_h2_owner_personal_batch_v1 import main
else:
    from tools.atlas_h2_private_batch_bootstrap_v1 import main
raise SystemExit(main(sys.argv[3:]))
'@
  $argsForBatch = @(
    '--private-evidence-dir', $EvidenceDir,
    '--isolated-output-dir', $OutputDir,
    '--pinned-git-repo', $clone
  )
  if ($Mode -eq 'strict-custodian') {
    if ($CustodianVerifierKey) {
      $argsForBatch += @('--trusted-custodian-key', $CustodianVerifierKey)
    }
  } elseif ($Mode -eq 'official-binance') {
    if ($LicenseReviewerKey) {
      $argsForBatch += @('--license-reviewer-key', $LicenseReviewerKey)
    }
  } else {
    if ($LicenseReviewerKey -or $CustodianVerifierKey) {
      throw 'PERSONAL_LANE_CANNOT_IMPERSONATE_EXTERNAL_RIGHTS_OR_CUSTODIAN'
    }
  }
  if ($OwnerSigningKey) {
    $argsForBatch += @('--owner-signing-key', $OwnerSigningKey)
  }
  if ($ConfirmOneRun.IsPresent) {
    $argsForBatch += '--confirm-one-run'
  }
  & $Python -I -c $runner $driver $Mode @argsForBatch
  $exit = $LASTEXITCODE
  if ($exit -eq 0) {
    Write-Host 'H2 engineering-only completed. Inspect h2-batch-summary.json.'
  } elseif ($exit -eq 2) {
    Write-Host 'H2 BLOCKED safely. See the ONE local h2-batch-summary.json report.'
  } else {
    Write-Error ('H2 bootstrap failed before full report. Exit=' + $exit)
  }
  exit $exit
} finally {
  # Only scratch Git/driver; original 43 staged files are untouched.
  if (Test-Path -LiteralPath $root) {
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
  }
}
