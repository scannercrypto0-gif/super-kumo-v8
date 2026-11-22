# Deterministic local filesystem only. Extract production helpers; no sockets/tasks.
$ErrorActionPreference='Stop'
$source=Join-Path $PSScriptRoot 'atlas_live_research_service_windows.ps1'
$ast=[System.Management.Automation.Language.Parser]::ParseFile($source,[ref]$null,[ref]$null)
foreach($name in @('Test-ResetRecovery','Test-ContinuousFault','Test-ContinuousRecovery','Archive-OperatorClaim','Test-OperatorResume','Claim-OperatorResume','Save-ServiceHold')) {
    $node=$ast.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name},$true)
    if (!$node) {throw "MISSING_HELPER_$name"}
    . ([scriptblock]::Create($node.Extent.Text))
}
$base=Join-Path ([IO.Path]::GetTempPath()) ('atlas-ws-supervisor-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $base | Out-Null
function Assert([bool]$OK,[string]$Code) {if (!$OK) {throw $Code}}
function Pin([string]$path) {(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
function New-Case([string]$Name) {
    $script:root=Join-Path $base $Name
    New-Item -ItemType Directory -Path $root | Out-Null
    $script:hold=Join-Path $root 'hold.json'
    @{reason='PILOT_STOP_TimeoutError';slot_ms=1795259700000L} | ConvertTo-Json | Set-Content $hold
    $claimed=Join-Path $root 'reset-recovery.claimed';'original-claim' | Set-Content $claimed
    $script:ticket=Join-Path $root 'operator-resume.authorized.json'
    $script:now=1795336739000L
    $script:cfgPin='a'*64
    $script:permit=@{schema='atlas.ws.operator-resume.v1';authorization_sha256=('b'*64);config_sha256=$cfgPin;
        hold_sha256=(Pin $hold);claimed_sha256=(Pin $claimed);pending_sha256=$null;
        issued_ms=($now-1000L);expires_ms=($now+600000L);max_segments=1;max_connections=2;orders=0;trading_authority='NONE'}
}
function Save-Ticket {$permit | ConvertTo-Json | Set-Content -LiteralPath $ticket}
function Refused([scriptblock]$Action,[string]$Expected) {
    $caught=$false
    try {& $Action | Out-Null} catch {$caught=$true;Assert ($_.Exception.Message -cmatch $Expected) 'WRONG_REFUSAL'}
    Assert $caught 'UNSAFE_ACCEPTANCE'
}
try {
    # Actual Nov21 sequence is a one-budget safety stop after recovery starts.
    New-Case 'owner-sequence'
    $health=Join-Path $root 'health.jsonl'
    @(@{status='CONNECTING';attempt=1},
      @{status='TRANSPORT_INTERRUPTED';error='ConnectionResetError';receive_phase='FRAME_BOUNDARY';deadline_origin='CONNECTION_RESET'},
      @{status='CONNECTING';attempt=2},
      @{status='TRANSPORT_INTERRUPTED';error='TimeoutError';receive_phase='FRAME_BOUNDARY';deadline_origin='UNDERLYING_RECEIVE_TIMEOUT'},
      @{status='STOPPED_ERROR';error='TimeoutError'}) | ForEach-Object {$_ | ConvertTo-Json -Compress} | Set-Content $health
    Assert (Test-ResetRecovery $health 'PILOT_STOP_TimeoutError') 'MIXED_SEQUENCE_NOT_CLASSIFIED'
    Save-Ticket
    $before=Pin $hold
    $result=Claim-OperatorResume $ticket $root $cfgPin $now
    Assert ((Test-Path (Join-Path $root 'operator-recovery.active.json')) -and !(Test-Path $ticket)) 'CLAIM_NOT_DURABLE'
    Assert (!(Test-Path $hold) -and !(Test-Path (Join-Path $root 'reset-recovery.claimed'))) 'ORIGINALS_NOT_ARCHIVED'
    $archived=Join-Path $root ('recovery-evidence/'+$permit.authorization_sha256+'/hold.json')
    Assert ((Pin $archived) -ceq $before) 'ORIGINAL_HOLD_CHANGED'
    Save-ServiceHold 'LIVE_SERVICE_OPERATOR_RECOVERY_COMPLETE_REVIEW_REQUIRED' 1795336200000L
    Assert ((Get-Content $hold -Raw | ConvertFrom-Json).reason -ceq 'LIVE_SERVICE_OPERATOR_RECOVERY_COMPLETE_REVIEW_REQUIRED') 'ONE_SHOT_RELEASED_CONTINUOUSLY'
    Refused {Claim-OperatorResume $ticket $root $cfgPin $now} 'TICKET_BOUND'
    # Expired, changed evidence, unsafe HOLD, broadened quotas never consume state.
    foreach($case in @('expired','tamper','wrong-config','unsafe-hold','budget','boolean-budget')) {
        New-Case $case
        switch ($case) {
            'expired' {$permit.expires_ms=$now-1L}
            'tamper' {$permit.hold_sha256='c'*64}
            'wrong-config' {$permit.config_sha256='c'*64}
            'unsafe-hold' {@{reason='PILOT_STOP_CANDLE_REVISION'} | ConvertTo-Json | Set-Content $hold;$permit.hold_sha256=Pin $hold}
            'budget' {$permit.max_connections=3}
            'boolean-budget' {$permit.max_segments=$true}
        }
        Save-Ticket;$before=Pin $hold
        Refused {Claim-OperatorResume $ticket $root $cfgPin $now} 'LIVE_SERVICE_OPERATOR_'
        Assert ((Pin $hold) -ceq $before) 'REJECTED_REQUEST_CHANGED_HOLD'
        Assert (!(Test-Path (Join-Path $root 'operator-recovery.active.json'))) 'INVALID_REQUEST_CLAIMED'
    }
    # Crash after claim: retained claim blocks a second scheduled process before any network API.
    New-Case 'crashed-claim'
    $config=Join-Path $root 'config.json';'{}' | Set-Content $config
    Remove-Item $hold
    '{}' | Set-Content (Join-Path $root 'operator-recovery.active.json')
    $output=& (Get-Process -Id $PID).Path -NoProfile -File $source -Config $config -ConfigSha256 (Pin $config) 2>&1
    Assert ($LASTEXITCODE -eq 1) 'CRASHED_CLAIM_EXIT'
    Assert ((Get-Content $hold -Raw | ConvertFrom-Json).reason -ceq 'LIVE_SERVICE_OPERATOR_RECOVERY_ALREADY_CLAIMED') 'CRASHED_CLAIM_STARTED_COLLECTOR'
    New-Case 'crashed-normal-execution'
    $config=Join-Path $root 'config.json';'{}' | Set-Content $config
    Remove-Item $hold
    '{}' | Set-Content (Join-Path $root 'segment-execution.active.json')
    $output=& (Get-Process -Id $PID).Path -NoProfile -File $source -Config $config -ConfigSha256 (Pin $config) 2>&1
    Assert ($LASTEXITCODE -eq 1) 'ORPHAN_EXECUTION_EXIT'
    Assert ((Get-Content $hold -Raw | ConvertFrom-Json).reason -ceq 'LIVE_SERVICE_INCOMPLETE_SEGMENT_REVIEW_REQUIRED') 'CRASHED_NORMAL_COLLECTOR_RESTARTED'
    Assert (Test-Path (Join-Path $root 'segment-execution.active.json')) 'ORPHAN_CLAIM_REMOVED'
    # Existing HOLD cannot be overwritten by a new rejected request/error receipt.
    $before=Pin $hold;Save-ServiceHold 'LIVE_SERVICE_OPERATOR_TICKET_SCOPE' 0
    Assert ((Pin $hold) -ceq $before) 'HOLD_EVIDENCE_OVERWRITTEN'
    New-Case 'continuous-transient'
    $health=Join-Path $root 'health.jsonl'
    $transient=@{status='TRANSPORT_INTERRUPTED';error='TimeoutError';retry_eligible=$true;is_transport_fault=$true;
        fault_stage='FRAME_READ';receive_phase='FRAME_BOUNDARY';fault_class='FRAME_BOUNDARY_TRANSIENT'}
    $events=@(@{status='CONNECTING';attempt=1},$transient,@{status='CONNECTING';attempt=2},$transient,@{status='STOPPED_ERROR';error='TimeoutError'})
    $events | ForEach-Object {$_|ConvertTo-Json -Compress} | Set-Content $health
    Assert (Test-ContinuousRecovery $health 'PILOT_STOP_TimeoutError') 'CONTINUOUS_TRANSIENT_REJECTED'
    $events[3]=$transient.Clone();$events[3].receive_phase='FRAME_PAYLOAD'
    $events | ForEach-Object {$_|ConvertTo-Json -Compress} | Set-Content $health
    Assert (!(Test-ContinuousRecovery $health 'PILOT_STOP_TimeoutError')) 'CONTINUOUS_PARTIAL_ALLOWED'
    $events[3]=$transient.Clone();$events[3].retry_eligible='true'
    $events | ForEach-Object {$_|ConvertTo-Json -Compress} | Set-Content $health
    Assert (!(Test-ContinuousRecovery $health 'PILOT_STOP_TimeoutError')) 'CONTINUOUS_BOOLEAN_SCOPE'
    $events=@(@{status='FAULT_CLASSIFIED';fault_stage='CLOCK_GUARD'},@{status='STOPPED_ERROR';error='FINALIZED_SOURCE_GAP'})
    $events | ForEach-Object {$_|ConvertTo-Json -Compress} | Set-Content $health
    Assert (Test-ContinuousRecovery $health 'PILOT_STOP_FINALIZED_SOURCE_GAP') 'CONTINUOUS_EXPLICIT_GAP_REJECTED'
    Assert (!(Test-ContinuousRecovery $health 'PILOT_STOP_CLOCK_STEP')) 'CONTINUOUS_CLOCK_GUARD_BYPASSED'
    $script:operatorActive=Join-Path $root 'operator-recovery.active.json'
    'original' | Set-Content $operatorActive
    Archive-OperatorClaim
    Assert (!(Test-Path $operatorActive)) 'CONTINUOUS_CLAIM_NOT_ARCHIVED'
    Assert (@(Get-ChildItem $root -Filter 'operator-recovery.completed-*.json').Count -eq 1) 'CONTINUOUS_CLAIM_LOST'
    Write-Output 'WS_SUPERVISOR_OFFLINE_PASS'
} finally {Remove-Item -LiteralPath $base -Recurse -Force}

# Expected failing child-process checks leave LASTEXITCODE=1; this suite passed.
exit 0
