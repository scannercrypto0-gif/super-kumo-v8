param(
    [Parameter(Mandatory = $true)][string]$Repository,
    [Parameter(Mandatory = $true)][string]$Python,
    [ValidateSet('--offline-preflight')][string]$Mode = '--offline-preflight',
    [string]$WheelDirectory
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Invoke-Checked {
    param([string]$Command, [string[]]$Arguments)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command exited with code $LASTEXITCODE"
    }
}

if ([Environment]::OSVersion.Platform -ne 'Win32NT') {
    throw 'WINDOWS_REQUIRED'
}
$Repository = (Resolve-Path -LiteralPath $Repository).Path
$Python = (Resolve-Path -LiteralPath $Python).Path
$observer = 'd072544427d6b08473c88b2e36d5857cfd8581dc'
$transport = '0a45cb6de6027b6fba54320e07b0faf3317a5382'
$integration = '9e97d4880920b9c0f5a949377100cfe38e690804'
$receiptFiles = @(
    'tools/atlas_single_receipt.py',
    'tools/atlas_single_receipt_runner.py',
    'tools/test_atlas_single_receipt.py',
    'tools/test_atlas_single_receipt_runner.py'
)

$root = Join-Path ([IO.Path]::GetTempPath()) ('atlas-receipt-' + [guid]::NewGuid())
$null = New-Item -ItemType Directory -Path $root
$oldTemp = $env:TEMP
$oldTmp = $env:TMP
$oldPath = $env:PYTHONPATH
try {
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl = Get-Acl -LiteralPath $root
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($rule in @($acl.Access)) {
        $acl.RemoveAccessRuleAll($rule)
    }
    $rule = [Security.AccessControl.FileSystemAccessRule]::new(
        $sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $acl.AddAccessRule($rule)
    Set-Acl -LiteralPath $root -AclObject $acl
    $actualAcl = Get-Acl -LiteralPath $root
    $rules = @($actualAcl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]))
    if (!$actualAcl.AreAccessRulesProtected -or $rules.Count -ne 1 -or
        $rules[0].IdentityReference -ne $sid -or $rules[0].AccessControlType -ne 'Allow') {
        throw 'PRIVATE_CUSTODY_ACL_UNVERIFIED'
    }

    $tree = Join-Path $root 'source'
    $index = 0
    foreach ($item in @(
        @{ Sha = $observer; Paths = @() },
        @{ Sha = $transport; Paths = @('tools/binance_live_feed') },
        @{ Sha = $integration; Paths = $receiptFiles }
    )) {
        $zip = Join-Path $root "source-$index.zip"
        Invoke-Checked git (@('-C', $Repository, 'archive', '--format=zip', "--output=$zip", $item.Sha) + $item.Paths)
        Expand-Archive -LiteralPath $zip -DestinationPath $tree -Force
        $index++
    }
    # When the release files include the tested delta, overlay only those files.
    foreach ($path in $receiptFiles) {
        $name = Split-Path -Leaf $path
        $overlay = Join-Path $PSScriptRoot $name
        if (!(Test-Path -LiteralPath $overlay -PathType Leaf)) {
            throw "MISSING_WINDOWS_PACKAGE_FILE $name"
        }
        Copy-Item -LiteralPath $overlay -Destination (Join-Path $tree "tools/$name")
        Write-Output ("OVERLAY_SHA256 {0} {1}" -f $name, (Get-FileHash -LiteralPath $overlay).Hash)
    }
    if ($WheelDirectory) {
        $WheelDirectory = (Resolve-Path -LiteralPath $WheelDirectory).Path
        $venv = Join-Path $root 'venv'
        Invoke-Checked $Python @('-I', '-B', '-m', 'venv', $venv)
        $Python = Join-Path $venv 'Scripts/python.exe'
        Invoke-Checked $Python @('-I', '-B', '-m', 'pip', '--isolated', '--disable-pip-version-check',
            'install', '--no-index', '--no-deps', '--find-links', $WheelDirectory, 'websocket-client==1.9.2')
    }

    $env:TEMP = $root
    $env:TMP = $root
    $env:PYTHONPATH = "$tree\src;$tree"
    Push-Location -LiteralPath $tree
    try {
        Invoke-Checked $Python @('-I', '-B', '-c', "import sys; from importlib.metadata import version; print(sys.version); assert sys.version_info >= (3, 11); v = version('websocket-client'); print('WEBSOCKET_CLIENT=' + v); assert v == '1.9.2'")
        Write-Output "INTEGRATION=$integration TRANSPORT=$transport OBSERVER=$observer"
        Invoke-Checked $Python @('-B', '-m', 'unittest', 'tools.test_atlas_single_receipt', 'tools.test_atlas_single_receipt_runner', '-v')
        Write-Output 'WINDOWS_OFFLINE_PREFLIGHT_PASS'
        Write-Output 'LOCAL_RESERVATION=FIXTURE_ONLY SHARED_IP_AGGREGATE=UNKNOWN'
        Write-Output 'BLOCKED_CONTROLLED_EGRESS_AUTHORITY_UNAVAILABLE'
    } finally {
        Pop-Location
    }
} finally {
    $env:TEMP = $oldTemp
    $env:TMP = $oldTmp
    $env:PYTHONPATH = $oldPath
    $resolvedRoot = (Resolve-Path -LiteralPath $root).Path
    if ($resolvedRoot -eq $root -and (Split-Path -Leaf $resolvedRoot) -match '^atlas-receipt-[0-9a-f-]{36}$') {
        Remove-Item -LiteralPath $resolvedRoot -Recurse -Force
    }
}
