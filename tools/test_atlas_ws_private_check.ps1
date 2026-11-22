# Native subprocess wire regression; no task, clock/network or owner state APIs.
$ErrorActionPreference='Stop'
$source=Join-Path $PSScriptRoot 'atlas_ws_resilience_windows.ps1'
$ast=[System.Management.Automation.Language.Parser]::ParseFile($source,[ref]$null,[ref]$null)
foreach($name in @('Hash-Text','Set-PrivateUtf8','Invoke-PrivateCheck')) {
    $node=$ast.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name},$true)
    if(!$node){throw 'MISSING_PRIVATE_HELPER'}
    . ([scriptblock]::Create($node.Extent.Text))
}
$repo=Join-Path ([IO.Path]::GetTempPath()) ('atlas-private-wire-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $repo|Out-Null
$helper=Join-Path $repo 'helper.py'
$ExpectedCommit='a'*40;$AuthorizationFile=$null
$python=(Get-Command python -ErrorAction Stop).Source
# Generated non-ASCII content reproduces Windows PowerShell ASCII-pipe loss.
$privateValue=([char]0x0623).ToString()+([char]0x03A9).ToString()+([char]0x4e2d).ToString()
$snapshot=@{python=$python;xml=$privateValue;expected=(Hash-Text $privateValue)}
$scriptCode=@'
import hashlib,json,sys,time
x=json.loads(sys.stdin.buffer.readline().decode('utf-8'))
mode=sys.argv[1]
if mode=='sleep':time.sleep(5)
if mode=='malformed':
 print('PRIVATE_HOST_PATH_OR_SECRET');print('PRIVATE_STDERR_SECRET',file=sys.stderr);sys.exit(7)
if mode=='invalid_reason':
 print(json.dumps(dict(status='WS_OPERATOR_BLOCKED',reason='PRIVATE_SECRET: C:/host')));sys.exit(2)
if mode=='diagnose':
 if hashlib.sha256(x['xml'].encode('utf-8')).hexdigest()!=x['expected']:
  print(json.dumps(dict(status='WS_OPERATOR_BLOCKED',reason='TASK_XML_CONTENT_PIN_MISMATCH')));sys.exit(2)
 print(json.dumps(dict(schema='atlas.ws.operator-diagnostic.v1',identity_sha256='a'*64,transport='UTF8_EXACT')));sys.exit(0)
print(json.dumps(dict(status='WS_OPERATOR_BLOCKED',reason='RUNTIME_PIN_MISMATCH',private='PRIVATE_SECRET')))
sys.exit(2)
'@
[IO.File]::WriteAllText($helper,$scriptCode,[Text.UTF8Encoding]::new($false))
function Assert([bool]$ok,[string]$code){if(!$ok){throw $code}}
function Refused([string]$mode,[string]$reason,[int]$timeout=30000){
    $caught=$false
    try {$null=Invoke-PrivateCheck $mode $snapshot $timeout} catch {
        $caught=$true
        Assert ($_.Exception.Message -ceq $reason) 'WRONG_PRIVATE_FAILURE_REASON'
        $public=ConvertTo-Json -InputObject $script:privateFailure -Compress
        Assert (!$public.Contains('PRIVATE_SECRET') -and !$public.Contains('PRIVATE_HOST_PATH') -and !$public.Contains('PRIVATE_STDERR_SECRET')) 'PRIVATE_OUTPUT_LEAK'
    }
    Assert $caught 'EXPECTED_PRIVATE_FAILURE_NOT_RAISED'
}
try {
    try {$ok=Invoke-PrivateCheck 'diagnose' $snapshot} catch {
        Write-Output ('SYNTHETIC_WIRE_FAILURE_METADATA '+(ConvertTo-Json -InputObject $script:privateFailure -Compress))
        throw
    }
    Assert ($ok.transport -ceq 'UTF8_EXACT') 'UNICODE_PIPE_CHANGED_IDENTITY'
    Refused 'authorize' 'RUNTIME_PIN_MISMATCH'
    Assert ($script:privateFailure.child_exit_code -eq 2 -and $script:privateFailure.reason -ceq 'RUNTIME_PIN_MISMATCH') 'CHILD_FAILURE_CONTEXT_LOST'
    Refused 'malformed' 'PRIVATE_HELPER_UNSTRUCTURED_FAILURE'
    Refused 'invalid_reason' 'PRIVATE_HELPER_UNSTRUCTURED_FAILURE'
    Refused 'sleep' 'PRIVATE_HELPER_TIMEOUT' 1000
    Write-Output 'WS_PRIVATE_CHECK_UTF8_REASON_AND_TIMEOUT_PASS'
} finally {Remove-Item -LiteralPath $repo -Recurse -Force}
exit 0
