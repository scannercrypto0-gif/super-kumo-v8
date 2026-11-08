# H2 one-batch Windows bootstrap. Never opens or edits existing working tree.
# The owner must supply a PRE-EXISTING independently authenticated private
# custody packet; this program never manufactures owner rights or source pins.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$EvidenceDir,
  [Parameter(Mandatory=$true)][string]$OutputDir,
  [string]$CustodianVerifierKey = '',
  [string]$OwnerSigningKey = '',
  [switch]$ConfirmOneRun,
  [string]$Python = 'python',
  [string]$Git = 'git'
)
$ErrorActionPreference = 'Stop'
$bootstrapCommit = 'f93cdaa684bcae1861145f027346486428fb217f'
$operatorCommit = '43903d82e85c272a17183dfbbfbe0c493696d3f2'
$required = @(
  $bootstrapCommit,
  $operatorCommit,
  '51f3724213e836fa680f589435e418d4b0c4c20f',
  '99c27ea2c1a4d41aaae361141301a8a9ea3b33c3',
  '3c82448702c9ae35783716e4e2c3b640010db97c',
  'a4b887fe7067b89febc339e466652a5fcb1c2bee',
  '6acbcc7fc243b132f58170df4c6469bbf7f4eff8'
)
# Only the explicitly named private evidence directory is inspected here.
# Never recursively search the user's E: drive or inspect Git working tree.
if (-not (Test-Path -LiteralPath $OutputDir -PathType Container)) {
  New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}
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
repo, target, bootstrap, operator = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3], sys.argv[4]
for sha,rel in (
    (bootstrap,'tools/atlas_h2_private_batch_bootstrap_v1.py'),
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
  & $Python -I -c $stageCode $clone $driver $bootstrapCommit $operatorCommit
  if ($LASTEXITCODE -ne 0) { throw 'STAGING_FAILED' }
  $runner = @'
import sys
sys.path.insert(0,sys.argv[1])
from tools.atlas_h2_private_batch_bootstrap_v1 import main
raise SystemExit(main(sys.argv[2:]))
'@
  $argsForBatch = @(
    '--private-evidence-dir', $EvidenceDir,
    '--isolated-output-dir', $OutputDir,
    '--pinned-git-repo', $clone
  )
  if ($CustodianVerifierKey) {
    $argsForBatch += @('--trusted-custodian-key', $CustodianVerifierKey)
  }
  if ($OwnerSigningKey) {
    $argsForBatch += @('--owner-signing-key', $OwnerSigningKey)
  }
  if ($ConfirmOneRun.IsPresent) {
    $argsForBatch += '--confirm-one-run'
  }
  & $Python -I -c $runner $driver @argsForBatch
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
