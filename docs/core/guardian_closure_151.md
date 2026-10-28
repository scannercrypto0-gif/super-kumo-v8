# Guardian #151 — bounded engineering hardening and operator handoff

2026-10-28 / AQL-CRYPTO-RESEARCH-001. Draft only; no operational authorization.
Issue [151](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/151).
Final exact SHA, test totals and CI URLs are recorded in the linked Draft PR and
Issue RESULT; this document does not invent a self-referential commit hash.

## Authority, ancestry and continuity

This independent branch starts at **3fc035b7ae70693e952976e2dcb2fe165a7e1826**,
OPEN/DRAFT/unmerged [#144](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/144).
It is stacked on #144 (which inherits #142/#137), not represented as accepted
main. Verified main dbc191df72f4b4d1ebb7d490926dcad4325dac12. Existing local
main at ed188f1 has pre-existing staged deletions; it was not repaired/switched.
New worktree C:\dev\ATLAS\guardian-closure-151, branch core/guardian-closure-151.

Latest actually delivered accessible owner Work is
[#147/6470454981](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/147#issuecomment-6470454981),
preceded by #146/6469407856 and #145/6468964410. Work147's source ZIP is
MISSING_BYTES / NOT_READY_FOR_FACTORY_EXECUTION; fetching it belongs elsewhere.
Read #149 (Core DEV-only envelope), #150 (Factory quality inspector), #148
(Factory exit/scenarios), #134 and #144 since-handoff comments, plus #77's
newer accessible comments. Their code/branches/artifacts are excluded.
Factory #143 was a6aa5fdd at first read and advanced during discovery to
dee0f088d70122d143118df2e0a0549a564f2380, still Draft/unmerged. No stale
exact-SHA acceptance is inherited. Council AIARC-089 /6470619214 accepts only
the earlier AIARC-084 policy fix at a6aa5fdd; unrelated to Guardian.

| Decision/delta | Disposition |
|---|---|
| AIARC-079 /6468079296 owner-observed 14 ACK /0 pending | Already documented; no repeat E2E |
| AIARC-081 bounded ACL remediation | Retained; not independently executed here |
| AIARC-086 /6469180485 current effective alias reconciliation | Retained; no historical/future invocation proof inferred |
| AIARC-088 /6469959478 negative identity deferral | Deferred, never PASS; residual acceptance still required |
| Core ACK /6470020127 and Work147 /6470463662, Council /6470464694 | Included; transport not a DEV source/PIT authority |
| #148/#149/#150 | Other owners, excluded; no integration work here |
| Unseen conversations/addenda | COVERAGE GAP; no claim of access or exhaustive cross-chat audit |

The old numbered register's AQL-HO-20261021-002/#14 is historical. It does not
supersede the newer explicitly referenced delivered Work147 for this order.
No new Work launch, gate closure or independent self-acceptance is asserted.

## Reproduced gaps and minimal changes

At the pinned baseline, a sender returning only `{sha256, remote_id}` caused
pending deletion, without a verified readback receipt. A second reproduction
restored pending alongside a previously committed ACK: deliver called sender
again and replaced the receipt. CLI also entered an unbounded loop unless
`--once` was supplied. These are concrete contract gaps, not evidence that any
of the owner's existing 14 records are corrupt.

1. Validate original Guardian receipt fields (digest, download digest, vault,
   status, exact object name, no issuer/custody assertion). Unversioned receipts
   remain accepted unchanged; new receipts explicitly version=1. Unknown versions
   and arbitrary old test-sender ACKs fail closed, with no migration or rewrite.
2. Reuse archive.local's fixed-inode nonblocking OS writer lock and path/reparse
   checks. Serialize cooperating exporter/delivery commits; never unlink locks
   based on PID or age. Contention yields OUTBOX_LOCK_UNAVAILABLE, retryable.
3. File flush/fsync -> atomic replace -> directory sync where supported -> ACK
   before pending unlink. On restart reuse/validate ACK, resync it and its
   directory, then finish unlink without sender or receipt overwrite. Windows
   fsync needs r+b descriptor; opening it does not alter receipt bytes.
4. Distinguish rclone missing-file exit4 from missing-directory exit3. Only4
   permits immutable upload; directory/fatal/conflict failures require review.
   Existing wrong remote bytes are never overwritten. Exceptions are translated
   to fixed codes, never raw command arguments, stdout/stderr or secret strings.
5. CLI now has **only local preflight**. Both legacy continuous and `--once`
   delivery invocations return HOLD before opening/creating an outbox. The
   reusable sender API remains for offline tests/future reviewed composition;
   it is not an operational enablement route or security sandbox.

No receive-loop, ingest, SQLite exporter, UTC policy, trading, Factory or source
adapter code changed. Export remains the existing read-only SQLite transaction
in its separate child; delivery remains separate. Lock contention can defer a
snapshot; the authoritative ledger remains intact. No throughput/SLO claim.

## Failure-mode / evidence matrix

| Boundary/failure | Behavior / focused evidence | Residual |
|---|---|---|
| offline/reconnect, safe retry | Existing offline tests + transient/timeout falsifiers; pending retained | No actual WAN/network outage drill |
| upload before ACK crash | Existing remote readback replay, no second upload | Remote durability is backend-dependent |
| ACK before unlink crash | New real spawned process exits23 with OS lock held; restart reuses identical ACK | Process exit is not power loss or SMB server crash |
| duplicate/reordered bundle | One ACK by content hash; distinct versions retained | No causal total order or latest-snapshot selector promised |
| two delivery writers | Real spawned contender denied nonblockingly; stable lock recovered after exit | Cooperating writers only; SMB lock enforcement needs operator review |
| malformed/partial/forged receipt | Missing fields, wrong root/digest/status/object/version rejected; old ACK never silently repaired | A correctly forged full receipt needs ACL/external trust controls |
| interrupted/partial upload, digest mismatch | Immutable copy; failed readback pending; subsequent conflict never overwritten | Orphan remote objects preserved for operator inventory |
| temp local orphan | Dot-temp ignored and retained | No automatic scavenger; disk capacity operator-owned |
| local fsync/replace/directory-sync failure | Injected ENOSPC and sync uncertainty preserve pending; retry proves no false ACK | Windows directory fsync unsupported; physical power-loss UNVERIFIED |
| permission / remote directory missing | Actionable local/sender code; no automatic permission changes or upload fallback | Effective ACLs not tested on owner hosts |
| symlink/reparse/path replacement | Reuse check_path; real symlink test when privilege allows; synthetic Windows reparse test | Parent rename TOCTOU/admin/hardlinks not a hardened sandbox |
| config/root/alias/executable/code drift | Local contract hash, path/identity/content pins and alias inspection fail closed | No current live target or future invocation proof |
| log secrecy | Fixed codes; injected secret stderr/message absent from outcomes | OS logs/operator shell/service platform need separate policy |
| UNKNOWN clock / PIT/custody | Existing authority/UTC negatives preserved | Transport never upgrades issuer timing or independent custody |
| retention / disk growth | No evidence auto-deletion/compaction, no destructive retry | Quota/retention policy and capacity not selected; no continuous enablement |

Local command (existing interpreter, no dependency installation):

```powershell
$env:PYTHONPATH='src'
& 'C:\dev\ATLAS\g1-completion\.venv\Scripts\python.exe' -m pytest -q tests/test_guardian_hardening.py tests/test_guardian_launch.py tests/test_evidence_outbox.py tests/test_observer_outbox_integration.py tests/test_observer_runtime.py tests/test_observation_operational_e2e.py tests/test_observation_authority.py tests/test_utc_evidence.py
```

Python3.14.3 on this Windows machine, synthetic/temp files only. Reuse existing
observation-authority-acceptance.yml (Ubuntu/Windows,3.11/3.14); new focused steps
and existing regressions cover this delta, no broad observer/G1/Factory reruns.
Original collection failure (test-helper package import) and Windows lock/fsync
discoveries are disclosed in Issue RESULT rather than hidden by CI reruns.

## Controlled future launch contract — NOT an activation script

Use guardian-launch.template.json as an unissued example. Fill it only in a
protected operator control directory after review; never post credentials/config
contents publicly. Contract hashes and config paths are restricted operational
metadata. Expected contract SHA must be retained separately in the reviewed
operator record, not recalculated from a possibly modified file at start.

Pins: atlas_vault:, root **P=1WeOdQ4COL89w4uqX-BnGGM4_xFYZHB9q**, local alias
atlas:ATLAS-EVIDENCE-VAULT, config byte SHA256, executable absolute paths/hashes,
actual Python version, reviewed source-file hashes, working directory, service
identity, exact allowed outbox and separate protected log path. RCLONE_* overrides
are rejected without printing names/values. The template has HOLD and pending
operator/audit refs; neither local success nor nonempty refs authenticate approval.
The public source pin set is a **bounded seam**, not full Python dependency/OS
supply-chain attestation. The future launcher must bind its entire environment,
explicit rclone --config/absolute executable, and recheck pins before each remote
operation; no such operational launcher is enabled in this PR.

Read-only local template invocation, **not executed on Windows2 here**:

```powershell
& .\scripts\guardian_preflight.ps1 -Repository 'C:\REVIEWED\checkout' `
  -Python 'C:\REVIEWED\python.exe' -PythonSha256 '<externally-reviewed-64hex>' `
  -Contract 'C:\RESTRICTED\guardian-launch.json' `
  -ExpectedContractSha256 '<externally-reviewed-64hex>'
```

The wrapper checks the external Python hash before executing it, uses -B and
sets PYTHONPATH to reviewed src; it restores shell state. Preflight creates no
outbox/log/task/service, invokes no rclone, writes no config and performs no
remote probe. Its only positive status is LOCAL_PREFLIGHT_VERIFIED_NOT_AUTHORIZED;
effective remote identity and Windows ACL remain OPERATOR_EVIDENCE_REQUIRED.
Even successful local checks preserve CONTINUOUS_ENABLEMENT_HOLD. Byte-level
rclone config changes (including token rotation) intentionally invalidate the pin;
review/reissue is required, never print tokens or automatically accept drift.

Root P and child **C=1ZxWfiZo2WFjxazJx_AUhpJAQv8mxA6xh** are different IDs.
AIARC-086 reconciled the effective alias under owner-observed configuration;
this code does not infer that all future configurations resolve identically.
Do not switch roots, move/delete/reupload 14 objects, or repeat their E2E.

## Minimal operator-only acceptance and access-control review

NOT EXECUTED here; require separate operational authorization before any real
start. Do not run an old README delivery command to obtain missing proof.

1. Windows2 operator declares actual future command (atlas_vault: plus root P),
   code SHA, executable/version hash, identity, working directory, allowed share,
   config and log locations; review residual risks and protected logging. Capture
   intended invocation without secret args. No service/task installed by this PR.
2. Windows1 authorized admin collects **read-only** effective share and recursive
   NTFS inventory and group membership evidence, not just absence of Everyone:

   ```powershell
   Get-SmbShareAccess -Name ATLAS-EVIDENCE-OUTBOX
   Get-SmbSession | Select-Object ClientComputerName,ClientUserName
   Get-Acl -LiteralPath 'C:\ATLAS-EVIDENCE-RUN\outbox' | Format-List
   Get-ChildItem -LiteralPath 'C:\ATLAS-EVIDENCE-RUN\outbox' -Recurse -Force |
     ForEach-Object { Get-Acl -LiteralPath $_.FullName }
   Get-LocalGroupMember -Group Administrators
   ```

   Retain securely; evaluate inherited ACEs, deny/allow ordering, traversal,
   owner/privilege powers, other shares/paths and nested/domain groups with admin.
   Get-Acl is an inventory, NOT a computed effective-access guarantee. Windows2
   identity must be correlated with server-side authenticated SMB sessions;
   interactive whoami alone is not the SMB principal. Keep operator/admin roles
   separate, least privilege, review changes and protect config/ACK/log parents.
3. Negative test remains DEFERRED_NO_ELIGIBLE_TEST_IDENTITY (AIARC-088), not PASS.
   Only when a legitimate separate non-admin identity exists and is authorized:
   record whoami /all and server principal, then run the bounded **read-only**
   test below in that identity's existing session. No account creation, runas
   password collection, SMB disconnect or impersonation workaround:

   ```powershell
   try {
     Get-Item -LiteralPath '\\DESKTOP-6LLNVIF\ATLAS-EVIDENCE-OUTBOX\acknowledged' -ErrorAction Stop | Out-Null
     'NEGATIVE_READ_TEST_FAILED_ACCESS_SUCCEEDED'
   } catch [System.UnauthorizedAccessException] {
     'NEGATIVE_READ_DENIED_ONLY_NOT_WRITE_OR_ALL_PATH_PROOF'
   } catch {
     'INCONCLUSIVE_NETWORK_PATH_OR_OTHER_ERROR'
   }
   ```

   Do not infer write denial from read denial, missing path or Test-Path False.
   A real write-negative probe would need a separately sanctioned disposable
   location and cleanup plan; not supplied as an executable operation here.
4. Reuse existing 14 ACK/identity evidence. Only if exact config differs, obtain
   a separately approved narrowly read-only effective-target observation and
   Council review. No remote write or historical 14-object rerun required here.
5. Independent Council S/R reviews new SHA/tests, effective ACL/config evidence,
   owner residual acceptance and intended-launch record. Separate owner operation
   authorization is still required; this PR must not self-grant it.

## Recovery, rollback, retention

- On timeout/offline: leave pending and all remote objects untouched. A later
  approved sender can cat first, verify content and complete ACK. Do not delete
  a partial conflicting remote object or force-copy over it automatically.
- On corrupt ACK/pending: preserve originals, stop that item, retain diagnostics
  and seek a reviewed repair plan. Never regenerate a convenient receipt.
- After upload-before-ACK: exact readback permits receipt creation. After
  ACK-before-unlink: validate/reuse the same ACK. Lock file left by a dead process
  is harmless; OS release, not age/PID deletion, determines availability.
- ENOSPC/permissions: operator fixes capacity/access only under separate approval.
  No automatic purge. Pending and acknowledged histories are retained; hashes
  alone cannot prove against full history rewrite. Source ledger is separate.
- Rollback means stop any future authorized sender, preserve all queue/receipt
  bytes, return to reviewed code in an isolated checkout. v1 receipt fields are
  additive; no data schema migration or existing-byte rewrite. Do not restore
  the old unguarded CLI loop or silently reopen continuous operation.
- Windows/SMB fsync/rename/byte-lock semantics and server/media failures are
  remaining platform risks. Local process-crash tests do not certify physical
  media, remote transaction atomicity or immutable third-party retention.

## Closure states and independent review

| State | Current disposition |
|---|---|
| CODE_FIXED_VERIFIED | Only exact new SHA + focused green evidence in PR/RESULT; independent verdict pending |
| BOUNDED_OWNER_TRANSPORT_ACCEPTED | Existing AIARC-079, not rerun or upgraded |
| DEFERRED_NEGATIVE_ACCESS | AIARC-088 limited deferral only |
| FUTURE_LAUNCH_NOT_PROVEN | Operator declaration/invocation proof absent |
| CONTINUOUS_ENABLEMENT_HOLD | Remains in code, runbook and all preflight results |
| PIT/UTC/CUSTODY_UNVERIFIED | Unchanged; no issuer/vintage/independent-clock/custody proof |

Council: independently falsify ACK validation, real-process replay/locking,
content conflict handling, secrecy and HOLD on the exact new SHA (S). Separately
judge R: these engineering tests supply no historical PIT/alpha validation.
No FINAL_CLOSED until operator evidence, owner residual-risk acceptance,
effective ACL/config review, Council review and separate operational permission.

Technical references checked for this implementation (primary docs only):
[rclone exit codes](https://rclone.org/docs/#list-of-exit-codes) distinguish3/4;
[configuration](https://rclone.org/docs/#config-string) documents credential
config and token updates; [environment overrides](https://rclone.org/docs/#environment-variables)
are why preflight rejects RCLONE_* variables. These references are not evidence
of an actual owner-host or cloud operation.
