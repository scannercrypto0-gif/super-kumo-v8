# Offline custody and restore kit — #71 / #77

**Software verification only. No custody attestation, production activation or
research evaluation acceptance.** Base249210786ef91f2c1c968dd0c5ec8ef7654b917c.
Reuses merged101 read-only verifier and104 builder without changing Factory code.

## Windows dry-run-first operator runbook

Before executing against real data, owner identifies/authorizes the exact finalized
research bundle, independently administered anchor destination, new disposable
restore path and report location. Stop writers and restart supervisors separately;
this kit does not stop processes, fence writers, or create a coherent live snapshot.
Do not infer permission from a path mentioned in an issue. In particular, the
previous F:desktop backup/old restore and2399file checks have **not** been inspected
by this kit and are not research-specific custody or Git recovery evidence.

Use the verified repository checkout and actual Python3.10+ executable. Assign
quoted literal paths only after the owner selects them:

```powershell
$py = '<verified Python executable>'
$bundle = '<authorized finalized offline research bundle>'
$anchor = '<owner-controlled separately retained manifest digest file>'
$restored = '<new disposable path; existing parent; must not exist>'
$report = '<new report file outside source, target and anchor>'

# Read-only planning. Does not create a manifest, target or report file.
& $py -B tools/offline_custody_kit.py manifest --source $bundle
# Only after explicit authorization AND confirmed quiescence:
& $py -B tools/offline_custody_kit.py manifest --source $bundle --execute --quiescent
```

Skip manifest creation when a valid existing manifest is already part of the
finalized bundle: it is never overwritten. Builder returns SHA256; it does **not**
store a protected anchor. Owner/custodian retains that exact digest through a
separate approved route before restore; do not derive the expected reference from
the restored bundle. The kit never chooses media, writes an anchor or provisions ACLs.

Read-only evidence collection on the authorized anchor (not an ACL-changing command):

```powershell
Get-Acl -LiteralPath $anchor | Format-List Owner,AccessToString,AreAccessRulesProtected
(Get-Item -LiteralPath $anchor).Attributes
Get-FileHash -LiteralPath $anchor -Algorithm SHA256
```

ACL output, the read-only attribute and an external drive alone do not establish
independent protection/WORM/retention. Independent operator must prove denial of
edit/delete/replace under the actual writer identity and retain identity, approval,
timestamps, media/retention and readback/restore evidence. Do not try destructive
permission tests against real anchors without separate explicit scope.

```powershell
# Source/anchor/target validation, all reads. Even --report is NOT written here.
& $py -B tools/offline_custody_kit.py restore --source $bundle --anchor $anchor --target $restored --report $report
# After approval/quiescence and reviewing dry-run output:
& $py -B tools/offline_custody_kit.py restore --source $bundle --anchor $anchor --target $restored --report $report --execute --quiescent
```

Exit0 means the requested local software check succeeded, NOT independent custody
or research acceptance. Every report keeps independent_custody_verified=false,
anchor_protection/retention/custodian/signoff unverified. Execution identity and UTC
are observed local metadata, not authenticated custodian identity or trusted time.
An owner signoff is separate; do not relabel the generated unsigned report as signed.

Target and report are exclusively created. Existing paths reject. On interruption,
partial target is preserved and error status is FAILED_NO_ACCEPTANCE. **No cleanup,
overwrite, backup deletion, truncation, retention or automatic retry/repair.**
Choose a different authorized target after inspecting incident evidence, never
delete/reuse a partial path automatically. Original source and anchor remain inputs.

## Optional observed receipt/state replay — NOT an evaluator

Only if the approved bundle contains a finalized standalone Factory SQLite ledger,
provide a separately retained frozen-plan digest AND checkpoint pair:

```powershell
& $py -B tools/offline_custody_kit.py restore --source $bundle --anchor $anchor --target $restored --ledger 'receipts.sqlite' --plan-digest '<retained 64hex digest>' --checkpoint-sequence <retained sequence> --checkpoint-hash '<retained 64hex chain>'
# Review dry-run/preflight first; add --execute --quiescent --report only after approval.
```

Reader uses SQLite mode=ro&immutable=1 on the quiescent snapshot, rejects live
WAL/SHM/journal sidecars, and reuses the merged AttemptLedger chain/lifecycle reader
and frozen membership verifier without invoking its writing constructor. It checks
source then restored receipts and re-verifies restored file hashes after replay.
Private reader coupling is intentional/pinned and regression-tested; a future
ledger/schema change requires review, not a permissive fallback. Known finalized
snapshot is a precondition of immutable mode, never a live-database consistency fix.

LOCAL_RECEIPTS_REPLAYED proves only observed receipt/state reconstruction and
checkpoint-prefix comparison. PENDING/FAILED/INPUTS are not completed evaluations;
COMPLETE remains disabled by the existing ledger. No bundle script/module/command
is executed. research_evaluation_replay always remains NOT_PERFORMED_NO_EVALUATOR;
real dataset coverage/PIT receipts/availability/splits remain NOT_ATTESTED. This
software does not start Factory77 priority2 or unblock it on synthetic test evidence.

## Limits and acceptance matrix

- Local regular files only; no symlink/reparse, UNC/network paths, special nodes,
  traversal, Windows reserved/ambiguous names or case-fold collisions. Bounds:
  4096files,8192entries,depth16,64MiB/file,128MiB total. These are bounded drill
  limits, not physical disk capacity, time/I/O quotas or production performance.
- Owner-confirmed quiescence required for execute, but is an assertion, not an
  independently attested snapshot. Pre/post stat/file-set/digest checks catch
  observed drift, not hostile same-account races or atomic live multi-file snapshots.
- Copies default file bytes, not ACLs, ownership, alternate streams, extended
  attributes, empty-directory topology or full filesystem/Git repository semantics.
- File fsync requests and process interruption fixtures are not hardware power-loss,
  Windows directory durability, authenticated anchors, off-device custody or retention.
- Reports expose no contents/credentials, only supplied paths, hashes/counts/states,
  local identity/time/tool/Python/Git versions and explicit limitations. Use only
  approved evidence bundles; no legacy secret search or backup-drive inventory.
- File hashes are not Git fsck. The reported broken ATLAS-Issue82-Work refs remain
  a separate unresolved observation. This kit neither repairs them nor reports
  repository recovery PASS. After separate authorization, perform read-only
  `git -C '<isolated restored checkout>' fsck --full` and preserve its errors;
  do not reset/reflog-repair/delete to turn that into a pass.

| Gate | This delivery |
|---|---|
| Local manifest/content/restore software | Deterministic synthetic tests + exact-head CI |
| Restored Factory receipts | Observed synthetic read-only replay; actual source not supplied |
| Real research bundle/PIT coverage | NOT VERIFIED |
| Independently protected anchor/identity/ACL/retention | BLOCKED, owner evidence needed |
| Actual independently restored research evaluation | NOT PERFORMED |
| Auxiliary Git repository recovery | NOT TESTED; prior failure not erased |
| #71/#77 / production acceptance | OPEN/BLOCKED; no merge/activation/holdout |

Next real drill requires owner authorization for the exact source snapshot and
independently protected anchor/destination. Keep #71/#77 open until independently
accepted observed evidence exists. No provider, permanent storage or retention
choice is made by this utility.
