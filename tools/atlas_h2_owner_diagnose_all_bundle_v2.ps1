# ATLAS PKG-0 ONE-PASS MULTI-FINDING. Preserves signed root report byte-for-byte.
# NO original H2 execution, one-use claim, strategy approval, G0 or trading.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$PrivateEvidenceDir,
  [Parameter(Mandatory=$true)][string]$SignedOutputDir,
  [string]$Python = 'python',
  [string]$Git = 'git'
)
$ErrorActionPreference = 'Stop'
$repoUrl='https://github.com/scannercrypto0-gif/super-kumo-v8.git'
$personal='4098cdde2c1f389e1c3b5821a156bd4acbd39534'
$readiness='885904a5e1df06bee1e32152a43f0fda4d0a4188'
$diagnostic='76479babaf1b05ee5ee4bc918a429d1c301e0d76'
$pins=@(
  '43a3bf3196649c46aed54872f958c323e4ae4913',
  '99c27ea2c1a4d41aaae361141301a8a9ea3b33c3',
  'af3720b6be921444cb83d52f3e975a9c85475ec6',
  '04b63cc9b406b1f3eae2ac7de5d43ebda26dbfdf',
  '6acbcc7fc243b132f58170df4c6469bbf7f4eff8'
)
$profile=[Environment]::GetFolderPath('LocalApplicationData')
if (-not $profile) { throw 'READINESS_LOCAL_PROFILE_MISSING' }
$base=Join-Path $profile 'ATLAS\H2-Local-Batch'
$key=Join-Path $base 'owner-identity-v2\owner-signing.key'
$out=[IO.Path]::GetFullPath($SignedOutputDir).TrimEnd('\')
$b=[IO.Path]::GetFullPath($base).TrimEnd('\')
if (-not $out.StartsWith(($b+'\'),[StringComparison]::OrdinalIgnoreCase)) {
  throw 'READINESS_SIGNED_OUTPUT_NOT_IN_PRIVATE_PROFILE'
}
if (-not (Test-Path -LiteralPath $out -PathType Container) -or
    -not (Test-Path -LiteralPath $PrivateEvidenceDir -PathType Container) -or
    -not (Test-Path -LiteralPath $key -PathType Leaf)) {
  throw 'READINESS_SIGNED_OUTPUT_OR_EXISTING_OWNER_EVIDENCE_MISSING'
}
$existing=Join-Path $out 'h2-readiness-summary.json'
if (-not (Test-Path -LiteralPath $existing -PathType Leaf)) {
  throw 'PREFLIGHT_EXISTING_READINESS_REPORT_MISSING'
}
$previousDigest=(Get-FileHash -LiteralPath $existing -Algorithm SHA256).Hash
$diagDir=Join-Path $base ('diagnose-all-' + [guid]::NewGuid().ToString('N'))
if (Test-Path -LiteralPath $diagDir) { throw 'DIAGNOSTIC_OUTPUT_COLLISION' }
$scratch=Join-Path ([IO.Path]::GetTempPath()) ('aql-h2-ready-' + [guid]::NewGuid().ToString('N'))
$clone=Join-Path $scratch 'repo'
$stage=Join-Path $scratch 'stage'
New-Item -ItemType Directory -Path $clone,$stage -Force | Out-Null
try {
  & $Git -C $clone init -q
  if ($LASTEXITCODE -ne 0) { throw 'READINESS_GIT_INIT_FAILED' }
  & $Git -C $clone remote add origin $repoUrl
  if ($LASTEXITCODE -ne 0) { throw 'READINESS_GIT_REMOTE_FAILED' }
  foreach ($sha in (@($personal,$readiness,$diagnostic)+$pins)) {
    & $Git -C $clone fetch -q --no-tags origin $sha
    if ($LASTEXITCODE -ne 0) { throw 'READINESS_ROLE_PIN_FETCH_FAILED' }
    $found=(& $Git -C $clone rev-parse --verify ($sha+'^{commit}')).Trim()
    if ($LASTEXITCODE -ne 0 -or $found -cne $sha) {
      throw 'READINESS_ROLE_PIN_SHA_MISMATCH'
    }
  }
  $stageScript=@'
import pathlib,subprocess,sys
repo,stage,personal,readiness=(pathlib.Path(sys.argv[1]),
    pathlib.Path(sys.argv[2]),sys.argv[3],sys.argv[4])
def get(commit,rel):
    return subprocess.run(
        ['git','-C',str(repo),'show',commit+':'+rel],
        capture_output=True,check=True).stdout
for rel in ('tools/atlas_h2_owner_local_one_shot_v1.py',
            'tools/atlas_h2_historical_policy_v2.py'):
    p=stage/rel
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_bytes(get(personal,rel))
sys.path.insert(0,str(stage))
from tools.atlas_h2_owner_local_one_shot_v1 import isolated_overlay,PINS
expected={
  'integration':'43a3bf3196649c46aed54872f958c323e4ae4913',
  'core':'99c27ea2c1a4d41aaae361141301a8a9ea3b33c3',
  'scanner':'af3720b6be921444cb83d52f3e975a9c85475ec6',
  'factory':'04b63cc9b406b1f3eae2ac7de5d43ebda26dbfdf',
  'work235':'6acbcc7fc243b132f58170df4c6469bbf7f4eff8',
}
if PINS!=expected: raise SystemExit('READINESS_PINNED_ROLES_DIFFER')
isolated_overlay(repo,stage)
for rel in (
 'tools/atlas_h2_owner_local_one_shot_v1.py',
 'tools/atlas_h2_historical_policy_v2.py',
 'tools/atlas_h2_owner_personal_batch_v1.py',
 'tools/atlas_h2_owner_identity_v2.py',
 'tools/atlas_h2_owner_research_authority_v1.py',
 'tools/atlas_h2_binance_public_lane_v1.py',
 'tools/atlas_h2_owner_evidence_recovery_v2.py',
 'tools/atlas_h2_scanner_import_seam_v2.py',
 'tools/atlas_h2_private_batch_bootstrap_v1.py',
 'research_wp_r0/strategy_definition.py',
 'research_wp_r0/indicator_library.py',
 'research_wp_r0/historical_library.py',
):
    p=stage/rel
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_bytes(get(personal,rel))
p=stage/'tools/atlas_h2_owner_readiness_v2.py'
p.write_bytes(get(readiness,'tools/atlas_h2_owner_readiness_v2.py'))
d=stage/'tools/atlas_h2_owner_diagnose_all_v2.py'
d.write_bytes(get(sys.argv[5],'tools/atlas_h2_owner_diagnose_all_v2.py'))
from tools.atlas_h2_scanner_import_seam_v2 import apply_import_seam
apply_import_seam(stage)
print('READINESS_COMPLETE_PINNED_OVERLAY_STAGED_NO_ORIGINAL_RUN')
'@
  & $Python -I -c $stageScript $clone $stage $personal $readiness $diagnostic
  if ($LASTEXITCODE -ne 0) { throw 'READINESS_PINNED_OVERLAY_STAGE_FAILED' }
  $runner=@'
import sys
sys.path.insert(0,sys.argv[1])
from tools.atlas_h2_owner_diagnose_all_v2 import main
raise SystemExit(main(sys.argv[2:]))
'@
  & $Python -I -c $runner $stage '--evidence-dir' $PrivateEvidenceDir '--signed-output-dir' $out '--owner-key' $key '--repo' $clone '--diagnostics-dir' $diagDir
  $rc=$LASTEXITCODE
  $digestAfter=(Get-FileHash -LiteralPath $existing -Algorithm SHA256).Hash
  if ($previousDigest -cne $digestAfter) {
    throw 'SIGNED_ROOT_PRIOR_READINESS_REPORT_CHANGED'
  }
  Write-Host ('PRIVATE_DIAGNOSTIC_REPORT_BASENAME: h2-preflight-findings.json')
  Write-Host ('PRIVATE_DIAGNOSTIC_FOLDER_BASENAME: ' + [IO.Path]::GetFileName($diagDir))
  Write-Host 'SIGNED_READINESS_REPORT_UNCHANGED'
  Write-Host 'NO_ORIGINAL_H2; NO_ONE_USE_CLAIM; NO_KEY_ENROLLMENT; NO_G0'
  exit $rc
} finally {
  if (Test-Path -LiteralPath $scratch) {
    Remove-Item -LiteralPath $scratch -Recurse -Force -ErrorAction SilentlyContinue
  }
}
