# AQL-CORE-WORK-OBSERVATION-AUTHORITY-E2E-001

**2026-10-28 Issue151 supersession:** all owner execution commands below are
historical, not a new authorization to repeat capture/SMB/Drive or start Guardian.
Current Guardian CLI is local-preflight-only; continuous and once starts are
HOLD. See [Guardian151 closure/runbook](guardian_closure_151.md). Historical
owner 14-ACK transport was subsequently accepted boundedly (AIARC-079/081/086);
AIARC-088 deferred one negative-access test, never granted operational release.

Disposition: **PARTIAL / owner-host acceptance and independent S/R pending**.
No PR merge, trading, OOS opening or final G0 approval. This report supersedes the
operational description at checkpoint 325cad5; its original evidence is retained.
Exact delivered SHA and CI run/job IDs are pinned in the PR #144 delivery comment.

## Continuity and authority

Starting Draft #144 head 6cb17079b71e7aaa33de756b60ad59686b260aad; main
 dbc191df72f4b4d1ebb7d490926dcad4325dac12. #142 08c140a9, #137 d27ddd8f
and Factory #141 fbf70afb / #143 33c432be are unmerged candidates. Concurrent
#144 update 325cad581dcb4222ec007338294c6001971fc921 was fetched and retained
before this additive revision; no force-push or source PR merge.

G0-GOV-01: last explicitly owner-confirmed cross-chat submitted baseline in
HANDOFF_REGISTER remains AQL-HO-20261021-002 / #14. Latest scope delivery before
execution was #144/6465387750, UTC B approval #144/6465335332, implementation
#134/6465367240. Current direct owner instruction supplies scoped execution
authority. All retrieved #128/#134 comments and inventory are retained in
continuity.json/open-pr-inventory.json; Council reviewed through #6465513488.
Personal Context search did not establish a newer owner-confirmed global handoff.
**COVERAGE GAP** remains for inaccessible chats/addenda; no exhaustive global
handoff claim. Historical D1/D2/D3 and Factory fixes ALREADY DOCUMENTED; current
runtime/UTC/Guardian/Drive work INCLUDED; owner-host and independent proof gaps
UNRESOLVED. No older proposal is silently treated as accepted main.

## Delivered code

- `scripts/binance_independent_observer.py`: public-data observer, automatic
  child-process local outbox snapshots at startup, every 30 seconds and shutdown.
- `src/aql/observer_runtime.py`: read-only SQLite snapshot in a consistent read
  transaction; export failure is visible and retryable. No full-ledger serialization,
  remote upload or NTP network probe in the receive loop. The parent waits at most
  two seconds for the final snapshot, then reports pending if it must terminate it.
- `scripts/sample_utc.py`, `src/aql/utc_sampler.py`: separate Windows1 collector,
  reusing canonical SNTP parser and preserving raw W32Time status. Observer imports
  a session-bound local sample and binds the canonical UTC result to each RECEIVE.
- Existing `src/aql/evidence_guardian.py` and Guardian CLI reused. Restrict upload
  fallback to remote-not-found errors; authorization/connection failures remain
  pending. Same SHA filename, immutable copy option, full download/bundle validation
  before ACK. Local ACK corruption now fails visibly instead of suppressing enqueue.
- Existing `binance_observer.verify_bundle` session/UTC metadata verification and
  Factory bridge reused; no replacement scientific admission gate.
- CI adds separate-process/W32Time cases and Python 3.14 alongside 3.11 on Windows
  and Ubuntu. Test data stay synthetic except explicitly retained public captures.

Isolation is process-level on a shared host/disk, not a resource/SLO or physical
failure-isolation guarantee. Windows2 may be off: Windows1 captures locally.
Cumulative snapshots grow with ledger size; no production retention/scale approval,
no automatic deletion, no arbitrary durability/power-loss claim. A killed exporter
leaves committed ledger recoverable at observer restart; supervision and disk
monitoring remain deployment duties. One Guardian worker is supported.

## Verified evidence, separated by kind

| Kind | Result | Retained evidence |
|---|---|---|
| Starting-head hosted CI | Six workflows SUCCESS on 6cb17079 | baseline-ci.json; authority run 40664387918, observer 40664387927, proof 40664387904, G1 40664387914, storage 40664387928, integrity 40664387919 |
| Injected local reconciliation | 39 passed before three added W32Time cases; final affected runtime suite 8 passed | runtime-targeted.xml; final hosted CI pinned in delivery |
| New genuine Linux capture | 4 REST versions/4 receives, 1 source clock sample, 1 GAP; no WS final event or natural correction proven | runtime-capture-manifest.json, runtime-capture.log, 36b7c8ca…json |
| Actual Drive roundtrip | 22,877 downloaded bytes, full SHA256 match and bundle verification; local ACK recorded only after readback | runtime-drive-receipt.json |
| Factory | Both prior and new actual-capture bundles structurally valid but empirically/PIT ineligible | test_current_operational_capture_drive_backup_still_denied_by_factory |
| Guardian missing/restart | Two actual Linux CLI starts with no installed rclone retain pending; reconnect/readback/tamper/replay use injected backend | test_observer_runtime.py, test_observation_operational_e2e.py |
| Windows1 / Windows2 | **NOT EXECUTED**: no remote channel to owner's machines | Owner runbook below |
| Physical power loss / Windows SMB / real Windows rclone OAuth | **NOT EXECUTED** | Owner deployment responsibility |

Earlier checkpoint capture/Drive proof at 325cad5 and supplementary original/interim
uploads remain retained; they are distinct captures, not counted as new final-source
acceptance. The primary final-runtime object is:
https://drive.google.com/file/d/15-3KbuiR_n88YeSwVtZ2GR5YgIjjqTIC/view

SHA256: `36b7c8ca2d5354aa7d3b4484091593daddf456e7a083f47ba1e4258099b34015`.
Ledger head: `12c459761b1b8cb7a886efd1e7d4bfe85953d6a82134b75a1bfc795e2291f2cd`.
Vault: `1WeOdQ4COL89w4uqX-BnGGM4_xFYZHB9q`.
This upload used the connected Drive service, **not Windows2/rclone**. It proves
backup bytes roundtripped, not independent custody or a provider publication time.

## UTC and scientific limits

No finite UTC accuracy was established. Actual collector DNS lookup failed
(`gaierror`); sample remains UNKNOWN. Missing, expired, restarted/session-mismatched,
wall-step, unsynchronized, invalid, over-threshold diagnostics fail UNKNOWN.
Default TTL 60 seconds, 10ms wall-step tolerance and 100ms diagnostic threshold
are implementation policy parameters, not measured accuracy or final production SLA.
Bounds include absolute offset, conservative RTT/root-delay allowance and maximum
of SNTP and parsed W32Time root dispersion. Unsupported/localized W32Time output
fails UNKNOWN rather than guessing numeric values. Earlier owner-reported ~7.76s
root dispersion prevents millisecond claims despite small stripchart offsets.

Windows and unauthenticated SNTP diagnostics are not an independently verified
UTC authority. Binance E/T/serverTime are source-reported fields, not authenticated
publication evidence. Same-account Drive can be changed/deleted; Windows2 on the
same LAN is additional verification only. Every bundle retains UNKNOWN UTC and
UNATTESTED issuer state, and Factory empirical/PIT admission remains refused.
No pre-monitor historical PIT, revision completeness between polls or scientific
predictive validity is inferred. rclone --immutable is client overwrite protection,
not WORM storage (official docs: https://rclone.org/docs/ and /drive/).

## Exact owner commands (PowerShell)

Use a separate checkout on each host. Replace DELIVERED_SHA with the exact SHA
in the linked PR delivery; the commands below do not activate trading or change
an existing G1 Core configuration. Windows1 hosts Core and this companion observer;
Windows2 runs only the optional Guardian. Existing production Core has no newly
authorized startup/migration in this task.

On both machines:

```powershell
git clone --branch core/observation-authority-gate-20261028 https://github.com/scannercrypto0-gif/super-kumo-v8.git C:\ATLAS-OBS-E2E
Set-Location C:\ATLAS-OBS-E2E
git checkout --detach DELIVERED_SHA
git rev-parse HEAD
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q tests\test_observer_runtime.py tests\test_observation_operational_e2e.py --junitxml=owner-host.xml
```

On Windows1, in one terminal (bounded public capture):

```powershell
New-Item -ItemType Directory -Force C:\ATLAS-EVIDENCE-RUN
.\.venv\Scripts\python.exe scripts\binance_independent_observer.py --directory C:\ATLAS-EVIDENCE-RUN --seconds 180
```

On Windows1, in a second terminal while the observer runs:

```powershell
Set-Location C:\ATLAS-OBS-E2E
.\.venv\Scripts\python.exe scripts\sample_utc.py --directory C:\ATLAS-EVIDENCE-RUN
```

Stop this collector with Ctrl+C after capture. It cannot supply a sample before
runtime-session.json exists. Reuse from an earlier observer session is rejected.

Configure an authenticated, user-restricted SMB share of
`C:\ATLAS-EVIDENCE-RUN\outbox` named `ATLAS-EVIDENCE-OUTBOX` on Windows1;
Windows2 needs read/change permissions for pending/ACK files. No broad Everyone
share, stored password or automatic firewall change is supplied. Actual share
identity/authentication is operator-owned and was not tested here.

On Windows2 install rclone from https://rclone.org/downloads/ and configure
an OAuth Google Drive remote named `atlas` using the vault's account. Run:

```powershell
rclone version
rclone config
rclone lsf atlas: --drive-root-folder-id 1WeOdQ4COL89w4uqX-BnGGM4_xFYZHB9q
Set-Location C:\ATLAS-OBS-E2E
# HISTORICAL command only; superseded by Issue151 launch HOLD.
# Current CLI rejects delivery/continuous starts. Do not execute this old form.
# See docs/core/guardian_closure_151.md for local-only controlled preflight.
# .\.venv\Scripts\python.exe scripts\evidence_guardian.py --outbox \\DESKTOP-6LLNVIF\ATLAS-EVIDENCE-OUTBOX --remote atlas: --once
```

Historical disconnect/restart plan (DO NOT REPEAT under Issue151) used a longer
Windows1 capture and Windows2 Guardian stop/restart. The old continuous invocation
is now rejected; operator commands below are retained only as historical context:

```powershell
Get-Item C:\ATLAS-EVIDENCE-RUN\observer.sqlite3* | Select-Object Name,Length,LastWriteTimeUtc
Get-ChildItem C:\ATLAS-EVIDENCE-RUN\outbox\pending\*.json | Measure-Object
Get-ChildItem C:\ATLAS-EVIDENCE-RUN\outbox\acknowledged\*.json | Measure-Object
w32tm /query /status /verbose | Out-File C:\ATLAS-EVIDENCE-RUN\w32time.txt
Get-Content C:\ATLAS-EVIDENCE-RUN\utc-sample.json
```

Acceptance: ledger/receives progress while Guardian is stopped; pending persists;
restart downloads each pending object and checks its SHA before ACK; repeat
`--once` sends no already-acknowledged bundle. Retain SHA, both Python/rclone
versions, logs/JUnit, pending/ACK samples and raw W32Time. In an isolated copy of
the outbox, corrupt a pending JSON byte and confirm TAMPERED_LOCAL/no upload;
never modify originals. Do not call these steps PASS until logs are supplied.

## Remaining ownership and requested review

- Owner: execute both-device runbooks, verify SMB/rclone OAuth and host restart;
  supply logs. No machine access was silently assumed.
- Core: monitor backlog/storage, handle demonstrated deployment defects; provide
  stronger external timing/correction evidence if scientific acceptance requires it.
- Independent Council #134: **S requested**, challenge process isolation, ACK/custody,
  rollback/tamper/recovery and exact-SHA CI; **R requested**, compare observer
  receipt vs issuer-publication time, clock uncertainty and mutable same-account
  backup, and confirm continued Factory denial. Implementer does not self-accept.
- Owner alone: future merge/activation/G0 decision. None performed here.


## Preserved CI failure and deterministic test repair

First implementation head325cad581dcb4222ec007338294c6001971fc921:
Core proof40666205102 Windows job122741211366 failed59PASS/1FAIL on
`test_sweep_soft_time_budget_preserves_cursor`. Stop phase already used a fake
monotonic clock, but resume phase used real clock and demanded completion within
the default250ms soft slice. Source intentionally returns incomplete at the budget
boundary; Windows fsync is not guaranteed below250ms. This is a test-contract
mismatch, not evidence lost progress or a production sweep defect. Resume now uses
deterministic monotonic time too; original complete/added==2 assertion retained,
plus cleared-progress assertion. No production budget/threshold/skip changed.
New code revision justifies new CI; original red run remains linked, no retry.

Same Windows job's optional benchmark separately reported SQLite database locked
and subsequent temporary-directory WinError32 cleanup failure. Remains
PERFORMANCE/CONTENTION OPEN; no performance/SLO acceptance. It is not the gating
pytest failure and is not concealed by changing benchmark behavior. Owner/Core
performance follow-up should preserve this counterevidence before production.
New-source authority40666205121 passed on both OS; observer Ubuntu job122741212261
446PASS/2SKIP. Some legacy CI uses GitHub virtual mergeafbb0666, not an actual
repository merge; its tree0980dd2e matched the implementation tree exactly.
