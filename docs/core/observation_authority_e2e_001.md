# AQL-CORE-WORK-OBSERVATION-AUTHORITY-E2E-001

Owner review status: **PARTIAL / operational acceptance pending**. Existing Draft
PR #144 only; no merge, trading, OOS or final G0 change. This standalone observer
runs alongside Core on Windows1. Existing G1 collector/runtime is unchanged.
Windows2 Guardian is an optional separate process, with no Core network call to it.

## Continuity

Project identity verified from repository. Main dbc191df72f4b4d1ebb7d490926dcad4325dac12;
starting #144 6cb17079b71e7aaa33de756b60ad59686b260aad. #142 08c140a9,
#137 d27ddd8f and Factory #141 fbf70afb / #143 33c432be are open/unmerged.
Last explicitly owner-confirmed submitted cross-chat baseline in register remains
AQL-HO-20261021-002/#14. Latest scope code delivery is #144/6465387750;
UTC owner B #144/6465335332 and implementation #134/6465367240 reconciled.
Current direct owner instruction authorizes the present implementation. It is not
proof every older Work chat was accessed. **G0-GOV-01 = COVERAGE GAP** for unseen
chats/addenda. No purported exhaustive unified handoff is issued.

Delta dispositions: previous D1/D2/D3, ACK/clock crash cases ALREADY DOCUMENTED
in #128 through6463127686; latest Council through #134/6465410783 and all
accessible comments inventoried in `evidence/observation-e2e-20261028/continuity.json`.
Current automatic outbox / UTC / Guardian / Drive proof INCLUDED here. Independent
custody, issuer timing, owner-device tests and Council S/R UNRESOLVED. Factory
#143 arithmetic remediation remains Factory-owned, not copied or retested here.

## Implementation and limits

The capture CLI now enqueues a verified ledger snapshot at start, after each REST
batch/closed WS event and at stop, automatically. Upload is never invoked in this
process. Local export failure prints LOCAL_EXPORT_PENDING; committed ledger can
be re-exported at next checkpoint/restart. Observer/outbox disk I/O still costs
local time and space; full cumulative snapshots have no production scale/SLO
approval. Operate bounded captures and monitor disk; no retention deletion added.
Outbox acknowledged receipts are local mutable state, not independent authority.

SNTP diagnostics are measured in the current observer process and stored with
session, monotonic/wall time, source, offset, RTT, root delay/dispersion, raw NTP
request/response and TTL. Default TTL 60s / diagnostic threshold 100ms are
conservative test/operator parameters, not approved production accuracy targets.
The bound sums absolute offset + RTT/2 + nonnegative root-delay/2 + root dispersion.
These values are **unauthenticated diagnostics**, not guaranteed UTC accuracy.
Stale, missing, unsynchronized, reset, wall-step (>10ms relative to monotonic),
nonfinite and over-threshold values become UNKNOWN. Session-reference and result
binding are checked on bundle verification. No sample reload across process start.
The existing provider event E / Binance time sample remains separate.
No W32Time stripchart-only millisecond accuracy claim is made; earlier reported
root dispersion ~7.76s cannot justify it. Actual new capture had UTC DNS failure,
so **no finite UTC accuracy bound established**. Factory timing remains unverified.

Guardian uses operator-configured rclone Google Drive remote, fixed vault ID
`1WeOdQ4COL89w4uqX-BnGGM4_xFYZHB9q`, content-addressed filenames, immutable
copy and full download SHA256/bundle check before ACK. Existing remote bytes are
read first for interrupted-upload recovery. Failed upload/readback/mismatch keeps
local pending evidence. `--immutable` is client behavior, not cloud immutability.
Same-account Drive and same-LAN Windows2 are mutable backup/additional verification,
not independently held append-only custody. Single Guardian worker supported;
concurrent workers, malicious admin rollback and physical power-loss unproven.
Credentials stay in owner's rclone config, never repository/chat. Connector upload
in this task proves actual Drive roundtrip separately from unexecuted rclone setup.

References checked 2026-10-28: RFC5905 packet/offset fields
https://www.rfc-editor.org/rfc/rfc5905.html ; rclone
https://rclone.org/drive/ and https://rclone.org/docs/ .

## Windows1: bounded observation alongside Core

No remote execution channel to owner devices was available. Run these commands
in **PowerShell** on Windows1. Use a separate checkout, leaving an existing Core
instance/config/data untouched. Replace `<DELIVERED_SHA>` with the exact final
commit reported in PR #144; do not use a moving branch without verifying SHA.

```powershell
git clone --branch core/observation-authority-gate-20261028 https://github.com/scannercrypto0-gif/super-kumo-v8.git C:\ATLAS-OBS-E2E
Set-Location C:\ATLAS-OBS-E2E
git checkout --detach <DELIVERED_SHA>
git rev-parse HEAD
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe scripts\binance_independent_observer.py --directory C:\ATLAS-EVIDENCE-RUN --seconds 180 --max-uncertainty-ms 100
Get-ChildItem C:\ATLAS-EVIDENCE-RUN\outbox\pending\*.json | Get-FileHash -Algorithm SHA256
w32tm /query /status /verbose | Out-File C:\ATLAS-EVIDENCE-RUN\w32time-status.txt
```

This starts the evidence observer, not trading or a second G1 runtime. Keep the
existing owner-controlled Core process on Windows1; no command here activates an
unreviewed pipeline. For restart proof repeat the capture command against the same
directory, retain both printed ledger heads and bundles. No retrospective coverage
or correction is inferred from REST snapshots or absence of observed corrections.

## Windows2: optional Guardian only

Install rclone from https://rclone.org/install/ if not present; `rclone config`
creates a Google Drive remote named `atlas` using the same authorized account.
Complete OAuth locally; do not paste credentials. Share ONLY the Windows1 evidence
outbox with this Windows2 account via Windows file sharing using least required
access (read pending; write acknowledged/remove pending). Windows2 must not open
or copy a live SQLite database. The share below is an operator prerequisite,
**not configured automatically**. UNC server is the reported Windows1 hostname.

```powershell
git clone --branch core/observation-authority-gate-20261028 https://github.com/scannercrypto0-gif/super-kumo-v8.git C:\ATLAS-GUARDIAN-E2E
Set-Location C:\ATLAS-GUARDIAN-E2E
git checkout --detach <DELIVERED_SHA>
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
rclone config
rclone lsf atlas: --drive-root-folder-id 1WeOdQ4COL89w4uqX-BnGGM4_xFYZHB9q
.\.venv\Scripts\python.exe scripts\evidence_guardian.py --outbox \\DESKTOP-6LLNVIF\ATLAS-EVIDENCE-OUTBOX --remote atlas: --once
```

For normal observation remove `--once`. For disconnect/restart evidence: stop
Guardian with Ctrl+C, keep Windows1 bounded capture running; retain pending count
and hashes on Windows1; restart Guardian and retain its receipts plus downloaded
file hashes. Expected: Core observer continues while Guardian is off; pending
count drains only on matching full readback, and second `--once` sends nothing.
This is an instruction for **NOT EXECUTED owner-device tests**, not a result.
Do not tamper with the actual vault; adversarial tests use disposable fixtures:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_observation_operational_e2e.py tests/test_evidence_outbox.py tests/test_utc_evidence.py
```

Independently download one SHA-named file on Windows2 to `C:\ATLAS-DOWNLOAD`,
then verify using its SHA retained on Windows1 before upload:

```powershell
rclone copyto atlas:<SHA256>.json C:\ATLAS-DOWNLOAD\<SHA256>.json --drive-root-folder-id 1WeOdQ4COL89w4uqX-BnGGM4_xFYZHB9q
.\.venv\Scripts\python.exe scripts\verify_observer_evidence.py C:\ATLAS-DOWNLOAD\<SHA256>.json --sha256 <SHA256>
```

## Validation results

Starting head six workflows all SUCCESS: 40664387919 (integrity), 40664387927
(observer), 40664387918 (authority), 40664387914 (WP01–04), 40664387928
(storage), 40664387904 (Core proof). Historical evidence, not new-source CI.
No manual rerun requested. Final changed-source CI IDs/results will accompany
this single report in the pinned PR #144 delivery comment.

Local Linux Python3.12.14 (actual runtime version in capture manifest):
- Baseline24 PASS; first collection failed because package was not installed;
  PYTHONPATH corrected. New CLI test initially lacked websocket-client;
  declared dependency install resolved collection. These were setup errors.
- Final targeted34 PASS/0FAIL/0SKIP,0.58s, local-targeted.xml.
- Core proof regression53 PASS/0FAIL/0SKIP,3.31s, local-proof-regression.xml.
- Existing pinned Factory #141 bridge rejects both historical fixture and new
  actual capture empirical/real-PIT claims, even after real Drive backup.
- No tests disabled/xfail, no assertion weakened; unchanged broad G1/storage
  historical proofs reused. Changed shared bundle verification justifies one
  configured observer/Core regression CI batch, without manual green reruns.

## Evidence and remaining ownership

Actual Work Linux capture: 4 Binance REST versions, WS timeout recorded as GAP,
UTC DNS failure recorded UNKNOWN. `capture-manifest.json`, live-capture.log and
SHA-named bundle pin bytes. Actual connected Drive upload/raw download:
file `1RuR86eEZ3NaASymm3oz698N7uJQbOtau`, 23148 bytes,
SHA256 `05e0f25a13b633f50e4f870ac79943414111c8a19fee717c2c4259144a9bad10`;
readback internal ledger/raw/version/envelope verification passed. Receipt in
`drive-readback.json`. This was NOT rclone or Windows2 execution.

Synthetic integration tests separately exercise actual run() callpath with fake
REST/WS, Guardian offline/reopen, bad readback/recovery/upload-before-ACK replay,
local export failure/retry, UTC expiry/session/wall-step and malformed NTP.
Existing real subprocess-exit, replay/reversion, tamper/truncation and pinned
Factory refusal tests are reused. New actual capture is also passed through
existing Factory #141 pinned bridge; no source-timing/real PIT promotion.

Owner: execute two Windows runbooks and supply redacted raw logs/receipts; provision
rclone/OAuth/UNC share. Core maintainer: address any resulting actual failure;
scale/retention/physical durability requires separate evidence, no guarantee here.
Independent custodian/time authority remains external; no code can manufacture it.
Council #134: separate S safety challenge and R scientific comparison requested
against final SHA, tests and provenance; no self-issued acceptance or task closure.
