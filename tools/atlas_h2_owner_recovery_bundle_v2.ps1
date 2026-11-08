# Owner-local ONE bundle: optionally enroll a NEW identity then recover
# genuinely original evidence; DOES NOT run original H2 or import secrets to Git.
# Windows PowerShell 5.1 and Python 3.11+; 3.14 local remains unverified.
[CmdletBinding()]
param(
  [switch]$EnrollNewIdentity,
  [switch]$UseExistingV2Identity,
  [switch]$ConfirmOwnerSigning,
  [string]$Git = 'git',
  [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
if ($EnrollNewIdentity.IsPresent -eq $UseExistingV2Identity.IsPresent) {
  throw 'CHOOSE_EXACTLY_ONE_ENROLL_OR_EXISTING_FORWARD_V2_IDENTITY'
}
if (-not $ConfirmOwnerSigning.IsPresent) {
  throw 'EXPLICIT_OWNER_CONTEMPORANEOUS_COST_AND_SCOPE_SIGN_REQUIRED'
}
$repo = 'E:\ATLAS\diagnostic-runner'
$sourceZip = 'E:\ATLAS\private\historical\BTCUSDT-15m-2024-03.zip'
$originalPrivate = 'E:\ATLAS\private'
if (-not (Test-Path -LiteralPath $repo -PathType Container) -or
    -not (Test-Path -LiteralPath $sourceZip -PathType Leaf)) {
  throw 'OWNER_EXPECTED_LOCAL_REPO_OR_ORIGINAL_ZIP_MISSING'
}
# Verify that the owner has actually synchronized this exact signed source.
$expectedCode='36b72664b07f2c896df689ef3dcf81521a4abc22'
& $Git -C $repo cat-file -e ($expectedCode + '^{commit}') 2>$null
if ($LASTEXITCODE -ne 0) { throw 'OWNER_LOCAL_GIT_EXACT_CODE_NOT_FETCHED' }
$localHead=(& $Git -C $repo rev-parse HEAD)
if ($LASTEXITCODE -ne 0) { throw 'OWNER_LOCAL_REPO_HEAD_NOT_VERIFIED' }
Write-Host ('OWNER_LOCAL_HEAD_VERIFIED: '+$localHead.Trim())
$profile=[Environment]::GetFolderPath('LocalApplicationData')
if (-not $profile) { throw 'OWNER_PROFILE_UNAVAILABLE' }
$base=Join-Path $profile 'ATLAS\H2-Local-Batch'
$idDir=Join-Path $base 'owner-identity-v2'
$enroller=Join-Path $repo 'tools\atlas_h2_owner_local_prepare_v2.ps1'
if (-not (Test-Path -LiteralPath $enroller -PathType Leaf)) {
  throw 'OWNER_IDENTITY_ENROLLER_NOT_SYNCED'
}
if ($EnrollNewIdentity) {
  & $enroller -EnrollNewIdentity
  if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne $null) {
    throw 'OWNER_IDENTITY_ENROLLMENT_NOT_VERIFIED'
  }
}
$key=Join-Path $idDir 'owner-signing.key'
if (-not (Test-Path -LiteralPath $key -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path $idDir 'owner-identity.json') -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path $idDir 'owner-revocations.json') -PathType Leaf)) {
  throw 'OWNER_FORWARD_KEY_OR_REVOCATION_REGISTRY_NOT_AVAILABLE'
}
$runId=[Guid]::NewGuid().ToString('N')
$out=Join-Path $base ('owner-r2-' + $runId)
$evidence=Join-Path $base ('evidence-r2-' + $runId)
New-Item -Path $out, $evidence -ItemType Directory -Force | Out-Null
$summary=Join-Path $out 'owner-r2-preparation-summary.json'
$scratch=Join-Path ([IO.Path]::GetTempPath()) ('aql-h2-r2-code-' + $runId)
$clone=Join-Path $scratch 'git'
$overlay=Join-Path $scratch 'overlay'
New-Item -Path $clone,$overlay -ItemType Directory -Force | Out-Null
try {
  & $Git -C $clone init -q
  if ($LASTEXITCODE -ne 0) { throw 'ISOLATED_GIT_INIT_FAILED' }
  & $Git -C $clone remote add origin 'https://github.com/scannercrypto0-gif/super-kumo-v8.git'
  if ($LASTEXITCODE -ne 0) { throw 'ISOLATED_GIT_REMOTE_FAILED' }
  $pins=@(
    $expectedCode,
    '43a3bf3196649c46aed54872f958c323e4ae4913',
    '99c27ea2c1a4d41aaae361141301a8a9ea3b33c3',
    'af3720b6be921444cb83d52f3e975a9c85475ec6',
    '04b63cc9b406b1f3eae2ac7de5d43ebda26dbfdf',
    '6acbcc7fc243b132f58170df4c6469bbf7f4eff8'
  )
  foreach ($pin in $pins) {
    & $Git -C $clone fetch -q --no-tags origin $pin
    if ($LASTEXITCODE -ne 0) { throw 'ISOLATED_ROLE_PIN_NOT_AVAILABLE' }
    $verified=(& $Git -C $clone rev-parse --verify ($pin+'^{commit}')).Trim()
    if ($LASTEXITCODE -ne 0 -or $verified -cne $pin) {
      throw 'ISOLATED_ROLE_PIN_MISMATCH'
    }
  }
  $prepare=@'
import json,pathlib,subprocess,sys
repo,stage,head=pathlib.Path(sys.argv[1]),pathlib.Path(sys.argv[2]),sys.argv[3]
pins={'integration':'43a3bf3196649c46aed54872f958c323e4ae4913',
      'core':'99c27ea2c1a4d41aaae361141301a8a9ea3b33c3',
      'scanner':'af3720b6be921444cb83d52f3e975a9c85475ec6',
      'factory':'04b63cc9b406b1f3eae2ac7de5d43ebda26dbfdf',
      'work235':'6acbcc7fc243b132f58170df4c6469bbf7f4eff8'}
base=['research_wp_r0','tools','src']
import io,tarfile
for role in ('integration','work235','scanner','factory','core'):
    res=subprocess.run(['git','-C',str(repo),'archive','--format=tar',pins[role]],
                       stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
    with tarfile.open(fileobj=io.BytesIO(res.stdout),mode='r:') as tf:
        for member in tf:
            p=pathlib.PurePosixPath(member.name)
            if not member.isfile() or not p.parts or p.parts[0] not in base:
                continue
            if '..' in p.parts or p.is_absolute(): raise SystemExit('UNSAFE_CODE_ARCHIVE')
            if not member.name.endswith('.py') and not (
                role=='work235' and member.name=='tools/strategy_service_offline/fixtures/strategies.json'):
                continue
            dest=stage.joinpath(*p.parts)
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(tf.extractfile(member).read())
for path in (
    'tools/atlas_h2_owner_identity_v2.py',
    'tools/atlas_h2_owner_evidence_recovery_v2.py',
    'tools/atlas_h2_owner_research_authority_v1.py',
    'tools/atlas_h2_owner_personal_batch_v1.py',
    'tools/atlas_h2_binance_public_lane_v1.py',
    'tools/atlas_h2_owner_local_one_shot_v1.py',
    'tools/atlas_h2_historical_policy_v2.py',
    'tools/atlas_h2_private_batch_bootstrap_v1.py',
):
    res=subprocess.run(['git','-C',str(repo),'show',head+':'+path],
                       stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
    dest=stage/path
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_bytes(res.stdout)
'@
  & $Python -I -c $prepare $clone $overlay $expectedCode
  if ($LASTEXITCODE -ne 0) { throw 'ISOLATED_PINNED_SOURCE_STAGE_FAILED' }
  $executor=@'
import json,pathlib,sys
stage,src,private,out,evidence,identity=map(pathlib.Path,sys.argv[1:7])
sys.path.insert(0,str(stage))
from tools.atlas_h2_owner_evidence_recovery_v2 import (
    prepare_owner_private_evidence, RecoveryBlocked)
try:
    result=prepare_owner_private_evidence(
        source_zip=src,private_root=private,output_root=out,
        evidence_dir=evidence,identity_dir=identity,
        confirm_sign=True)
except Exception as exc:
    code=str(exc) if isinstance(exc,RecoveryBlocked) else (
        'OWNER_PREPARATION_PROOF_OR_RUNTIME_BLOCKED_'+type(exc).__name__)
    result={'status':'BLOCKED','reason':code,
            'original_h2_executed':False,
            'private_evidence_created':False}
summary=out/'owner-r2-preparation-summary.json'
with summary.open('x',encoding='utf-8') as f:
    json.dump(result,f,sort_keys=True,indent=2)
print(json.dumps({'status':result['status'],
                  'reason':result.get('reason'),
                  'summary_file':summary.name},sort_keys=True))
raise SystemExit(0 if result['status']=='FOUR_AUTHENTIC_OWNER_LOCAL_ARTIFACTS_PREPARED_NOT_RUN' else 2)
'@
  & $Python -I -c $executor $overlay $sourceZip $originalPrivate $out $evidence $idDir
  $rc=$LASTEXITCODE
  Write-Host ('OWNER_PRIVATE_REPORT: ' + $summary)
  Write-Host ('OWNER_PRIVATE_EVIDENCE_DIRECTORY: ' + $evidence)
  Write-Host 'NO_ORIGINAL_H2_EXECUTED; NO_G0; NO_TRADING'
  exit $rc
} finally {
  if (Test-Path -LiteralPath $scratch) {
    Remove-Item -LiteralPath $scratch -Recurse -Force -ErrorAction SilentlyContinue
  }
}
