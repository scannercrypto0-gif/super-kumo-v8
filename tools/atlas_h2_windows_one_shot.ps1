# ATLAS H2 one-command Windows launcher. Existing 43 staged files untouched.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$PrivateManifest,
  [Parameter(Mandatory=$true)][string]$OwnerHmacKey,
  [Parameter(Mandatory=$true)][string]$AuditOutput,
  [string]$Python = 'python',
  [string]$Git = 'git'
)
$ErrorActionPreference = 'Stop'
$operatorCommit = '43903d82e85c272a17183dfbbfbe0c493696d3f2'
$required = @(
  $operatorCommit,
  '51f3724213e836fa680f589435e418d4b0c4c20f',
  '99c27ea2c1a4d41aaae361141301a8a9ea3b33c3',
  '3c82448702c9ae35783716e4e2c3b640010db97c',
  'a4b887fe7067b89febc339e466652a5fcb1c2bee',
  '6acbcc7fc243b132f58170df4c6469bbf7f4eff8'
)
if (-not (Test-Path -LiteralPath $PrivateManifest -PathType Leaf)) {
  throw 'OWNER_PRIVATE_MANIFEST_MISSING: no source accessed'
}
if (-not (Test-Path -LiteralPath $OwnerHmacKey -PathType Leaf)) {
  throw 'OWNER_PRIVATE_HMAC_KEY_MISSING: no source accessed'
}
if (Test-Path -LiteralPath $AuditOutput) {
  throw 'AUDIT_OUTPUT_MUST_BE_FRESH: no source accessed'
}
$root = Join-Path ([IO.Path]::GetTempPath()) ('aql-h2-local-' + [Guid]::NewGuid().ToString('N'))
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
    if ($LASTEXITCODE -ne 0) { throw ('MISSING_PINNED_COMMIT_' + $sha) }
    $actual = (& $Git -C $clone rev-parse --verify ($sha + '^{commit}')).Trim()
    if ($LASTEXITCODE -ne 0 -or $actual -cne $sha) {
      throw ('PIN_MISMATCH_' + $sha)
    }
  }
  $stageCode = @'
import pathlib, subprocess, sys
repo, target, pin = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
for rel in ('tools/atlas_h2_owner_local_one_shot_v1.py',
            'tools/atlas_h2_historical_policy_v2.py'):
    p = target / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(['git','-C',str(repo),'show',pin + ':' + rel],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode: raise SystemExit('PINNED_OPERATOR_NOT_AVAILABLE')
    p.write_bytes(r.stdout)
(target / 'tools/__init__.py').touch()
'@
  & $Python -I -c $stageCode $clone $driver $operatorCommit
  if ($LASTEXITCODE -ne 0) { throw 'PINNED_OPERATOR_STAGING_FAILED' }
  $launch = @'
import sys
sys.path.insert(0,sys.argv[1])
from tools.atlas_h2_owner_local_one_shot_v1 import main
raise SystemExit(main(sys.argv[2:]))
'@
  $argsForOperator = @(
    '--private-manifest', $PrivateManifest,
    '--owner-hmac-key-file', $OwnerHmacKey,
    '--local-git-repo', $clone,
    '--authorize-local-readonly-run',
    '--local-audit-output', $AuditOutput
  )
  & $Python -I -c $launch $driver @argsForOperator
  $code = $LASTEXITCODE
  if ($code -ne 0) {
    Write-Error ('H2 stopped safely; inspect private audit receipt. Exit=' + $code)
    exit $code
  }
  Write-Host 'H2 bounded engineering run completed; inspect local sealed receipt.'
} finally {
  # Never clean/reset or inspect the owner's existing staged worktree.
  if (Test-Path -LiteralPath $root) {
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
  }
}
