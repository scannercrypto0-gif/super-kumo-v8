# #113 owner-run Windows acceptance — not executed / no activation implied

Track A follow-up6397725932: missing known published generations, not just missing
files inside them, now stop local coverage/health claims. This relies on retained
local successful-result evidence and does not replace independent receipt custody.

Use only after review of child hardening PR and parent#111; neither is merged by
this checklist. No whole-drive ACL change, backup deletion, production key
generation, schedule activation or account connection has been performed here.
Existing protected-custody, desktop backups and old Drive anchor remain untouched.
Every path below is an **owner-approved placeholder**, not inferred permission to
use a real source. Record PASS/FAIL/NOT VERIFIED with exact output; don't substitute
synthetic CI for hardware/account evidence. #71 stays OPEN.

## 1. Name operating scope and evidence paths

Owner records source generation/version/finality/quiescence, backup/recovery host,
media serial/label, dedicated destination+marker, least-privilege identities,
timezone/DST/logoff coverage, capacity horizon and independent custodian. Decide
offline key escrow and two-person recovery procedure **before** creating real keys.
Source limit128MiB total/64MiB per file/4096files; retained audit2GB/60s,4096generations;
local-state8192entries. Exceeding a budget fails closed, never auto-deletes.

In a normal Windows session (not elevated by default), select a new evidence
directory and save only non-secret output. Do not use a transcript while entering
private-key passwords or export environment variables.

```powershell
$Repo = '<reviewed checkout>'
$Python = '<verified existing interpreter with optional backup dependency>'
$Config = '<approved local config.json>'
$Evidence = '<new dedicated evidence directory>'
$Root = '<approved F:\ATLAS dedicated automation root>'
New-Item -ItemType Directory -Path $Evidence -ErrorAction Stop
$env:PYTHONPATH = Join-Path $Repo 'src'
git -C $Repo rev-parse HEAD | Out-File (Join-Path $Evidence 'source-sha.txt') -NoClobber
& $Python --version | Out-File (Join-Path $Evidence 'python.txt') -NoClobber
Get-TimeZone | Format-List | Out-File (Join-Path $Evidence 'timezone.txt') -NoClobber
Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='F:'" | Select-Object DeviceID,DriveType,VolumeName,VolumeSerialNumber,FreeSpace,Size | ConvertTo-Json | Out-File (Join-Path $Evidence 'media.json') -NoClobber
Get-Acl -LiteralPath $Root | Format-List Owner,AccessToString | Out-File (Join-Path $Evidence 'root-acl.txt') -NoClobber
Get-Content -LiteralPath (Join-Path $Root '.atlas-backup71-volume') | Out-File (Join-Path $Evidence 'marker.txt') -NoClobber
```

Missing/wrong media, denied access or unmatched owner-approved identity: STOP
that physical step and retain failure. No fallback drive/ACL bypass/formatting.
DriveType/marker/letter alone do not prove separate physical or immutable custody.

## 2. Establish a genuinely finalized source

CSV/evidence bundle: freeze a new approved version and retain its precomputed
custody manifest digest outside the bundle. Mutation during backup must reject.
Never replace an old source/anchor to make validation pass.

G1 SQLite/journal: use existing finite archive writer+SQLite backup API against
approved scope; **never copy a live .sqlite or WAL/SHM sidecar as a custody bundle**.
Example only after source/root/budget approval:

```powershell
& $Python -B -m aql.archive --journal '<approved journal.sqlite>' --root '<approved archive root>' --market spot --build '<unchanged archive build>' --policy '<unchanged policy>' --batches 4 --backup-to '<new sealed snapshot parent>' | Out-File (Join-Path $Evidence 'wal-snapshot.json') -NoClobber
if ($LASTEXITCODE -ne 0) { throw 'Snapshot failed; no source generation accepted' }
```

Record sealed path, inventory digest, journal/archive counts, watermark, backlog,
snapshot observation/missingness. Set source_kind=archive_backup with its retained
inventory digest, not the old CSV anchor. Backup API is coherent for individual
SQLite databases, not a global journal/hot transaction or actual PIT attestation.
This adapter verifies G1 journal/catalog/optional hot schemas; arbitrary research
or receipt SQLite databases require a separately reviewed adapter, not Factory
changes or a naked-file exception in this task.
Freeze that source generation and bind source_version/config; a newer snapshot is
a new generation/config, not an overwrite of historical evidence.

## 3. Real key recovery / explicit manual job

Owner independently pins DER public-key fingerprint, protects private-key escrow
and password recovery separately, and supplies only public material to writer.
No keys/passwords in GitHub, Drive, task XML or CLI arguments. Use the established
approved key setup; the synthetic helper is never real-key provisioning.

```powershell
& $Python -B -m aql.archive.automation backup --config $Config | Out-File (Join-Path $Evidence 'preflight.json') -NoClobber
if ($LASTEXITCODE -ne 0) { throw 'Preflight failed' }
# Execute only on the specifically approved source/destination/key scope:
& $Python -B -m aql.archive.automation backup --config $Config --execute | Out-File (Join-Path $Evidence 'manual-backup.json') -NoClobber
if ($LASTEXITCODE -ne 0) { throw 'Backup failed; no acceptance' }
& $Python -B -m aql.archive.automation health --config $Config | Out-File (Join-Path $Evidence 'health.json') -NoClobber
& $Python -B -m aql.archive.automation retention --config $Config | Out-File (Join-Path $Evidence 'retention-preview.json') -NoClobber
```

Health before a real private-key drill should explicitly show that drill missing.
Record job ID, counts, source/cipher/payload/receipt-file hashes and local intent
pin/outbox paths; local cache is not independent custody. No cleanup of partials.

## 4. External receipt pin and alternate-host restore

From local outbox collect unique `<id>.receipt.json`, `<id>.receipt.sha256` and
`<id>.anchor.sha256`. First pin is SHA256 of exact receipt-file bytes; internal
receipt_sha256 is a different self-check. Verify locally:

```powershell
$Receipt = '<local outbox\id.receipt.json>'
$PinFile = '<local outbox\id.receipt.sha256>'
if ((Get-FileHash -LiteralPath $Receipt -Algorithm SHA256).Hash.ToLower() -ne (Get-Content -LiteralPath $PinFile -Raw).Trim()) { throw 'Receipt outbox mismatch' }
```

Off-device transfer requires **separate owner account/config approval**. Human
operator may upload ONLY these small unique files to the approved custody folders
then independently download/read back exact bytes, record file IDs/UTC/operator
and compare hashes. Never overwrite old anchors or send bulk data/keys. Same-owner
Google Drive is mutable offsite storage, not WORM/independent authority; document
custodian separation, MFA and retention evidence. No cloud command/account login
or Telegram send is included or authorized by this checklist.

On a separately approved recovery host retain the trusted downloaded receipt+pin
outside the backup. Obtain pin **before** trusting the local backup metadata;
never calculate a new expected pin from the possibly compromised backup itself.
Use a recovery config with pinned public-key identity and new local audit path;
old source/anchor/F: paths may be unavailable. Do not place audit files inside the
backup. Private-key recovery must be independently observed by the custodian.

```powershell
$TrustedReceipt = '<authenticated independent download\id.receipt.json>'
$Pin = (Get-Content -LiteralPath '<authenticated independent download\id.receipt.sha256>' -Raw).Trim()
if ((Get-FileHash -LiteralPath $TrustedReceipt -Algorithm SHA256).Hash.ToLower() -ne $Pin) { throw 'Trusted receipt readback mismatch' }
# Supply encrypted-PEM password via approved secure per-process route, never argv.
& $Python -B -m aql.archive.automation restore --config '<new recovery config.json>' --backup '<offline backup copy>' --target '<new disposable restored-A>' --private-key '<separately recovered encrypted private.pem>' --receipt-sha256 $Pin --execute | Out-File (Join-Path $Evidence 'restore-A.json') -NoClobber
if ($LASTEXITCODE -ne 0) { throw 'Restore failed; preserve evidence/partials' }
```

Repeat supervised acceptance for A after creating B/new anchor, reconcile exact
A manifest/files/rows with independently retained A evidence; then reject a
tampered **disposable copy** using original pin. Do not corrupt originals. Real
host-loss recovery requires source machine/media unavailable plus separate key
and receipt retrieval; a same-host alternate-path unit test is not that proof.
Lost local monitoring cache is not auto-rebuilt from untrusted F: metadata; use
independent restore, then separately approved cache re-establishment.

## 5. Scheduler, failures and alerts — prepare/inspect only here

Existing task uses Interactive/Limited: logged-off execution is **not supported**
by that principal. Owner must choose a properly scoped noninteractive identity
and secure credential mechanism separately if required; do not store passwords
in XML or elevate the job. Record host-local trigger time/DST vs UTC job grouping.

```powershell
.\scripts\register-backup71-task.ps1 -Python $Python -Repository $Repo -Config $Config -LogDirectory '<approved local logs>' -XmlOutput (Join-Path $Evidence 'review-task.xml') -Mode Backup -At '<approved local HH:mm>'
# No -Register, Enable-ScheduledTask or Start-ScheduledTask in this issue's work.
Get-ScheduledTask -TaskName '<approved existing task name>' | Select-Object TaskName,State,Principal,Settings | ConvertTo-Json -Depth 5 | Out-File (Join-Path $Evidence 'task-state.json') -NoClobber
Get-ScheduledTaskInfo -TaskName '<approved existing task name>' | Select-Object LastRunTime,LastTaskResult,NextRunTime | ConvertTo-Json | Out-File (Join-Path $Evidence 'task-result.json') -NoClobber
```

Actual registration/activation, logged-off run, physical unplug, real ACL denial,
disk exhaustion and full host-loss drill remain owner-run, separately scoped
actions. Use only approved disposable test media/data; record baseline/recovery
conditions and no-original-data-loss evidence. Software CI covers controlled
versions, not physical certification. Require nonzero/typed failures, retained
partials and DEGRADED health; no unauthorized permission workaround or pruning.

Telegram is separate opt-in work with named channel/config/secure credentials,
redacted payload and delivery receipt; no send/credential access here. MFA/WORM/
retention and independent authority require owner/security evidence, not code0.
Monthly drill/capacity/overdue checks remain explicit. Final disposition stays
NOT READY for operational closure while any required external gate is unverified.
