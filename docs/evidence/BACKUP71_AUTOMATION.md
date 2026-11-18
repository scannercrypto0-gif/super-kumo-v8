# Backup71 execution evidence / acceptance boundary

Base main `fc94d833dcb6e87064093ca7ccc4efea3a0732e3` (merged#107). Owner attachment
requested implementation, not another architecture review. Read#71/latest policy
and Draft#109/9491c334c162cd2527b52f1adfb3144a6935f060. #109 unchanged; no merge.

Reused custody kit bounded inventory/manifest verification and existing sealed
archive WAL-aware backup verifier. No changes to core journal/collector/pipeline,
Factory, historical library, protected-custody ACL or existing backups. No live
database file-copy claim. No automatic source discovery, production key or full
machine backup. Operational source/escrow must be named/configured by owner.

## Implemented

Finite encrypted jobs, manual CLI, read-only preflight; separate OS lock and
IgnoreNew scheduler setting; unique exclusive generations/partial preservation;
idempotent verified same-day retry, complete-generation adoption after crash;
fresh AES-GCM DEK/nonce, pinned RSA-OAEP public key, authenticated stored readback;
private-key restore into a new target with original manifest reconciliation;
weekly/monthly point labels and no-delete retention preview; fsynced local audit,
health/overdue/monthly-drill flags; paths-free unique receipt/anchor outbox;
Limited/Interactive Windows task XML+registration with no credentials/elevation.

## Actual Windows observation

[Sanitized raw evidence](backup71-automation-windows.json) records locally observed
unsigned results and source hashes for **pre-publication worktree bytes**. Final
commit CI is separately identified in PR/#71 RESULT; do not relabel this actual
Scheduler observation as an execution of a future commit identity.

Windows11/Python3.14.3/PowerShell7.6.5, isolated venv `backup71-venv` with optional
cryptography50.0.2 and test/runtime packages. Existing G1 interpreter untouched.
F: reported ATLAS_BACKUP, serial38B211B9, OS fixed-drive type3; not a physical
independent-custody attestation. Existing sample custody-manifest hash freshly
read matches5fe4018a3b490cd64fb998c7b5d9afbd5bbf76a1868cc83194cb7dfc7f2d0c0d.
No repeated Binance download/import/restore of that unchanged sample.

Actual uniquely named Scheduler acceptance task
`ATLAS Backup71 Acceptance 1792925276081` registered/started, LastTaskResult0,
Limited/Interactive/IgnoreNew. It created a real encrypted backup in a **new
synthetic-only** F:\ATLAS subdirectory:2files/114829sourceB. Backup ID
`20261025T104801Z-8cde1fbdb9364bf58b9a743b480f05e5`, ciphertext SHA256
`7ca70bdc36aea100f3272984655dbc267a6c91bcb21cd57cd8029bb167f46959`.
Private-key decrypt+byte reconciliation PASS; rerun ALREADY_VERIFIED_TODAY,
ciphertext unchanged; scoped local health OK/custodyfalse. Acceptance task then
**disabled**, retained for review. An earlier synthetic task1792924831191 was
also disabled; later observation additionally exercises final pinned-key config.
No production daily job enabled, credentials stored or final recovery key created.
Fixtures/test keys are synthetic and remain local; do not use for real data.

## Tests / reproducibility

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
python -B -m pytest -p no:cacheprovider tests/test_backup71_automation.py -q -rs --tb=short
```

New29-case acceptance includes encryption/restore bytes, SHA256, forged-receipt
ciphertext authentication, wrong keys/pinning, weak-key denial, no overwrite,
real second-process lock refusal, two real os._exit interruption/retry paths,
source/media mutation, absent fixture media, injected space/permission errors,
health/overdue, point labels/calendar-year retention/no deletion, bounded ZIP
central directory before materialization, WAL-aware snapshot adapter and core
commit while backup worker is blocked. No new skip accepted by CI. Windows and
Ubuntu Python3.11/3.14 matrix retains exact checkout/environment/JUnit artifacts;
actual counts/run URLs are recorded only after observed completion.

Local final grouped run: **29 PASS,0 FAIL,0 SKIP in9.63s**. PowerShell scripts
parsed successfully; final XML writer exclusive creation/preflight observed and
final no-clobber wrapper rerun through the same task returned0. Task disabled
again afterwards. This rerun reverified the existing same-day ciphertext rather
than claiming a second newly encrypted backup. Raw source hashes reflect those
reviewed files; no production activation inferred.

Unchanged inherited archive/G1 suites were not manually repeated. Their prior
evidence is in#107/#71; automatic PR checks may rerun due existing workflow path
filters/optional-dependency addition. Such checks are supplementary, not a
substitute for Windows Scheduler acceptance.

## Operational readiness

|Requirement|Disposition and evidence|
|---|---|
|Normal encrypted backup/SHA256/restore|PASS on synthetic actual Windows source; not production data|
|Task Scheduler executes actual backup|PASS, Limited/Interactive, LastTaskResult0; test task now disabled|
|Daily production schedule|BLOCKED: exact ongoing source generations, independently recovered real key, local time/logoff identity/setup not activated|
|Weekly/monthly points/retention|PASS controlled-date software tests; real12week/12month operation NOT VERIFIED; deletion absent|
|Overlap/interruption/restart|PASS real OS lock/second process and process-exit tests, preserved partials|
|Missing drive / replacement|PASS fixture missing-media/replacement tests; actual physical F: unplug NOT VERIFIED|
|Disk full/insufficient permission|PASS deterministic safe injection; host disk exhaustion/actual restrictive-ACL write NOT VERIFIED|
|Corruption/failed restore detection|PASS on disposable altered copies, typed logs; original backups intact|
|Core isolation|PASS bounded dependency test; host-wide CPU/I/O/paper/Telegram/Research performance NOT VERIFIED|
|Local health/audit/outbox|PASS tested; not independent custody or remote alert delivery|
|Google Drive upload/readback of new receipts|BLOCKED: no connected Drive capability; prepared local outbox + manual runbook; old anchor untouched|
|Telegram notification delivery|NOT VERIFIED; no credentials/service calls|
|Real key recovery/independent custody/MFA/WORM|NOT VERIFIED; owner secure setup/signoff required|

Failed final tests: none when reported PASS; unresolved operating gates are not
silently marked passed. Limits:128MiB finalized source,4096files,64MiB/file;
4096generations/8192local-state entries; partials/logs accumulate without cleanup.
Temporary authenticated decryption uses OS temporary storage; restricted/encrypted
scratch and independently held key recovery need owner operating controls.
Local identity/timestamps, app media markers and unsigned hashes do not prove
trusted time, immutability, independent custody or production disaster recovery.

**Closure recommendation: NOT READY.** Implementation is reviewable, but real
production source/key recovery/schedule and custody/remote evidence remain open.
Do not merge, close#71, enable destructive retention or extend into#77.
