# ATLAS F2 owner-private isolated PowerShell exact-SHA assembly/one-command.
# NOT a merge, not original F2 reconstruction, not F5/Paper/trading.
# Download this file from the exact Integration commit and pass that commit
# as -IntegrationCommit; the same SHA is checked after detached worktree setup.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')]
        [string]$IntegrationCommit,
    [string]$WarehouseRoot = '',
    [string]$VaultRoot = '',
    [string]$RecoveryFile = 'E:\ATLAS\diagnostic-runner\f2-recovery-evidence.json',
    [string]$PolicyFile = '',
    [string]$TrialLedgerFile = '',
    [string]$InventoryReceiptsFile = '',
    [string]$PythonExe = 'python'
)
$ErrorActionPreference='Stop'
function Deny([string]$code) {
    [Console]::WriteLine(('{ "status":"PRIVATE_WAIT","code":"' + $code + '","trading_authority":"NONE"}'))
    exit 2
}
if ([string]::IsNullOrWhiteSpace($WarehouseRoot) -or
    [string]::IsNullOrWhiteSpace($VaultRoot)) {
    Deny 'WAREHOUSE_ROOT_AND_RAWVAULT_ROOT_REQUIRED'
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Deny 'PINNED_GIT_REQUIRED'
}
if (-not (Get-Command $PythonExe -ErrorAction SilentlyContinue)) {
    Deny 'PYTHON_3_11_PLUS_REQUIRED'
}
$repo='https://github.com/scannercrypto0-gif/super-kumo-v8.git'
# Isolated directory is a new UUID under OS TEMP, NEVER inside E: originals.
$root=Join-Path ([System.IO.Path]::GetTempPath()) ('AQL-F2-ISOLATED-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root -ErrorAction Stop | Out-Null
$env:AQL_F2_WORKSPACE=$root
$mirror=Join-Path $root 'mirror'
$operator=Join-Path $root 'operator'
$output=Join-Path $root 'private-output'
New-Item -ItemType Directory -Path $output -ErrorAction Stop | Out-Null
$refs=[ordered]@{
    'integration'=$IntegrationCommit
    'factory_e'='0ec35238de6cf48db07c5c977e1f0d04bc299f58'
    'factory_d'='a695e262da6787f752a13820f02dd00eef8ef1cd'
    'core_f'='998e3bcca8ca6f1150964dfa9d94726fec96b846'
    'core_e'='3af5b66d2b381b853a6b5be32c38b3d3d02e1ea7'
    'core_d'='a86a590a5e2c32c18e03522f52896dbcf50c60ff'
    'scanner_f'='798d409cb3db36b4f519f2e18a1f6089ff8f8010'
    'scanner_e'='a2aa9c195095bcfe852fdc760e385ccb2acf3d5d'
    'scanner_d'='a91e370ae7e5197e9af71f8300eeaff4a7aff022'
    'scanner_c'='1659713c80d1934f3c08af1af422b89cd5706360'
    'scanner_b'='30c37ae56851488b882998c7fa0085ec51dbfc92'
    'discoverer_f'='1cb70f1212283fe34117882d18e0501fc6409fe7'
    'discoverer_e'='149ca90c09b96abb45d3bc2839b657711c9826ac'
    'discoverer_base'='f2006c0e431690ccea8b0532095bf4f2a2dc88ba'
    'work235'='6acbcc7fc243b132f58170df4c6469bbf7f4eff8'
    'raw211'='7d97b09c0c6ee2650a61d523acb8d8c771a99c46'
    'scanner227'='b9c9ff8602e79c534402f44bce83c56ec2fa6bb9'
    'raw_windows_lock'='e368dd491a0d80618bdc6c6e8f731a195d763dda'
}
try {
    # Git fetch always takes place in the NEW TEMP checkout.
    & git clone --quiet --filter=blob:none --no-checkout $repo $mirror *> $null
    if ($LASTEXITCODE -ne 0) { Deny 'GIT_CLONE_OR_AUTH_FAILED' }
    # Windows Git may otherwise convert LF to CRLF on checkout. Every
    # downstream Git-blob/raw-byte pin requires original exact bytes.
    & git -C $mirror config core.autocrlf false
    if ($LASTEXITCODE -ne 0) { Deny 'GIT_LF_CONFIG_FAILED' }
    & git -C $mirror config core.eol lf
    if ($LASTEXITCODE -ne 0) { Deny 'GIT_LF_CONFIG_FAILED' }
    & git -C $mirror config core.safecrlf true
    if ($LASTEXITCODE -ne 0) { Deny 'GIT_LF_CONFIG_FAILED' }
    foreach ($entry in $refs.GetEnumerator()) {
        $key=$entry.Key
        $sha=$entry.Value
        & git -C $mirror cat-file -e "$sha^{commit}" *> $null
        if ($LASTEXITCODE -ne 0) {
            & git -C $mirror fetch --quiet origin $sha *> $null
            if ($LASTEXITCODE -ne 0) { Deny 'PINNED_GIT_COMMIT_UNAVAILABLE' }
        }
        $path=if ($key -eq 'integration') { $operator } else {
            Join-Path $root ('_pinned_'+$key)
        }
        & git -C $mirror worktree add --quiet --detach $path $sha *> $null
        if ($LASTEXITCODE -ne 0) { Deny 'PINNED_WORKTREE_FAILED' }
        $actual=(& git -C $path rev-parse HEAD 2>$null).Trim()
        if ($actual -cne $sha) { Deny 'EXACT_OWNER_SHA_DRIFT' }
    }
    Push-Location $operator
    try {
        & $PythonExe -m tools.atlas_f2_stage_owner_overlay --root $root
        if ($LASTEXITCODE -ne 0) { Deny 'PINNED_OVERLAY_INCOMPATIBLE' }
        $manifest=@{
            schema='aql.integration.owner-local-f2-one-command.v1'
            owner_operator_authorized=$true
            warehouse_root=$WarehouseRoot
            vault_root=$VaultRoot
            recovery_file=$RecoveryFile
            policy_file=$PolicyFile
            trial_ledger_file=$TrialLedgerFile
            inventory_receipts_file=$InventoryReceiptsFile
            isolated_workspace=$output
        }
        $manifestPath=Join-Path $output 'operator-manifest.json'
        $manifest | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $manifestPath -Encoding utf8
        # IMPORTANT Windows PowerShell 5.1 writes BOM for utf8; Python
        # json.loads(bytes) rejects BOM. Normalize manifest to no-BOM UTF8.
        $payload=$manifest | ConvertTo-Json -Depth 12 -Compress
        [System.IO.File]::WriteAllText($manifestPath,$payload,
            (New-Object System.Text.UTF8Encoding($false)))
        & $PythonExe -m tools.atlas_f2_owner_execute --operator-manifest $manifestPath
        $operatorExit=$LASTEXITCODE
        if ($operatorExit -ne 0) { exit 2 }
    } finally {
        Pop-Location
    }
} catch {
    # Never print exception text: native Git and Python can include E: paths.
    Deny 'ISOLATED_OPERATOR_PREREQUISITE_OR_SOURCE_ERROR'
}
