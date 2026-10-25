# Backup71 automation — bounded implementation and Windows runbook

Issue#113 hardening: restore now **requires** `--receipt-sha256` obtained from a
previously retained trusted channel. It is SHA256 of the exact receipt.json file
bytes, **not** its internal self-hash or the ciphertext anchor. Current source/
anchor paths are no longer historical-restore dependencies; pinned per-generation
metadata supplies the old source commitment. See
[owner acceptance checklist](backup71-owner-acceptance-113.md).
Registration recipes later in this historical runbook are capabilities, not
authorization to activate schedules under#113. That mission prepares/tests code
and owner-run steps only; real activation requires the separate operating gate.

Before publish, a local receipt intent pin is fsynced outside the external drive;
monitoring checks it (or parent111's previously retained outbox receipt), canonical
receipt bytes and **every** retained ciphertext. Missing evidence/corruption/audit
budget exhaustion stops coverage/health claims. This local cache is not independent
custody. The whole retained audit is bounded to2GB/60s plus4096generations, so a
larger retained set fails closed and requires a separately reviewed audit plan;
no silent unbounded work or deletion. Retention preview also audits first.

Custody bundles containing raw SQLite headers or WAL/SHM/journal sidecars are
rejected; use only the existing verified WAL-aware `archive_backup` adapter for
SQLite. Recovery log paths overlapping the supplied backup are rejected before
creating audit files. No new encryption format, private key or dependency.

Authority: owner's Codex attachment dated2026-10-25; issue#71. Implements the
approved policy recorded in#71/comment6396451139. Draft#109 is read-only context,
not a dependency imported into main. No change to its policy document or main.

## Scope / prerequisites

This is an opt-in **finalized generation backup job**, not a new collector or
whole-machine backup. Supported sources: bounded quiescent custody bundles
verified by the merged custody kit, or sealed WAL-aware archive backups verified
by `aql.archive.backup.verify_backup`. A live SQLite/journal/hot file must **first**
use the existing `create_backup` API/finite archive CLI. Never copy live SQLite
files or infer that desktop Git copies are research datasets. No automatic
discovery, production source selection or pipeline activation is installed.

Limit128MiB total source,64MiB/file,4096files; bounded source traversal, unique
generations and cooperative operation deadlines. Separate process, BelowNormal
Windows priority, one fixed interprocess lock and Scheduler IgnoreNew admission.
No network/fetch, shared callback/queue, Factory, Telegram credentials or paper
runtime touched. This avoids a synchronous core dependency; **not a hard CPU/I/O
isolation guarantee**. Task five-minute limit can terminate blocked work; partials
are preserved and never treated as complete. Capacity beyond this bounded scope
needs a measured follow-up, not raised limits silently.

Optional dependency `cryptography==50.0.2` in `[backup]`; existing environments do
not import it unless this new functionality is invoked. Use an isolated approved
venv, `pip install -e ".[dev,backup]"` for tests; no background installation.
Implementation expects the reviewed source checkout including the existing
`tools/offline_custody_kit.py`; standalone wheel-only deployment is not supported.

## Key custody (human prerequisite, no production keys auto-generated)

RSA public recovery key3072..8192 bits; SHA256 of DER SubjectPublicKeyInfo pinned
in the approved config. Daily writer uses only this public key. Each backup gets
a fresh random256-bit DEK and96-bit nonce, streaming AES-GCM with authenticated
versioned header; DEK wrapped with RSA-OAEP/SHA256 and versioned label. Real stored
ciphertext is decrypted/authenticated with the RAM-only DEK and plaintext ZIP hash
compared before success. Private-key recovery is a **separate drill**.

No custom cipher; standard primitives via PyCA. Envelope/container version1 still
requires independent security review; encryption is not a signature, WORM or
independent custody. Anybody with the public key can encrypt different data;
independently retain the expected ciphertext SHA256/receipt/config commitments.
Refs: [PyCA authenticated modes](https://cryptography.io/en/stable/hazmat/primitives/symmetric-encryption/),
[RSA OAEP](https://cryptography.io/en/stable/hazmat/primitives/asymmetric/rsa/).

Owner first chooses custodian/escrow, independently protected offline recovery
copy, recovery operator and test procedure. On that approved workstation, an
already installed OpenSSL can create an **encrypted** private key using its
interactive password prompt (never put a password in argv or chat):

```text
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -aes-256-cbc -out <approved-private.pem>
openssl pkey -in <approved-private.pem> -pubout -out <writer-public.pem>
```

These are instructions, not commands already executed for production. Confirm the
public fingerprint through the custodian's approved channel before filling config.
Keep encrypted private material and passphrase recovery separately from backups,
GitHub, Drive and scheduled writer. Owner must verify recovery on a separate
approved device before activation; lost private key means unrecoverable backups.
Python process environment `ATLAS_BACKUP_RECOVERY_PASSPHRASE` is supported for a
supervised restore only; supply through an approved secure route, never command
history/logs. Environment protection is not HSM protection; do not put this value
in task XML. The synthetic acceptance helper's public test password/key are only
for disposable fake data, **never a key provisioning tool**.

Decryption does not expose plaintext until GCM finalization. It uses a temporary
file which is automatically closed/deleted; source/backup copies are not deleted.
Use an owner-restricted, preferably disk-encrypted TMP/TEMP scratch area; physical
erasure, privileged process access and recovery from storage remnants are not
guaranteed. Restored plaintext is deliberately retained at the new approved path.

## Config / manual operation

Create a local access-controlled JSON outside source/destination, containing
**exactly** these keys (all placeholders require owner selection):

```json
{
  "source": "C:\\approved\\finalized-generation",
  "source_kind": "custody_bundle",
  "source_version": "approved-release-v1",
  "anchor": "C:\\approved-anchor\\anchor.sha256",
  "public_key": "C:\\approved-public-key\\public.pem",
  "public_key_sha256": "<64 lowercase hex DER public-key fingerprint>",
  "external_root": "F:\\ATLAS\\approved-new-automation-root",
  "volume_marker": "<previously provisioned unique marker>",
  "destination": "F:\\ATLAS\\approved-new-automation-root\\runs",
  "local_state": "C:\\approved-local-logs\\backup71",
  "reserve_bytes": 10000000000,
  "quiescent": true
}
```

`archive_backup` source kind expects its previously retained inventory digest as
anchor. The old custody sample digest is **not** a digest for arbitrary archives.
Owner must approve and provision a new root and its `.atlas-backup71-volume` ASCII
marker, verify volume label/serial and ACL; no marker is automatically added to
the existing F: root or protected-custody. App marker+device/inode checks detect
absence/replacement during this run, not physical independence or a hostile
privileged clone. Do not change whole-drive ACLs or grant access to protected
custody to make a test pass. Existing root must exist; missing drive never causes
fallback creation on another disk.

```powershell
$env:PYTHONPATH = Join-Path <reviewed-checkout> 'src'
python -B -m aql.archive.automation backup --config <approved-config.json>
python -B -m aql.archive.automation backup --config <approved-config.json> --execute
python -B -m aql.archive.automation health --config <approved-config.json>
python -B -m aql.archive.automation retention --config <approved-config.json>
python -B -m aql.archive.automation restore --config <recovery-config.json> --backup <generation> --target <new-disposable-target> --private-key <separately-held-private.pem> --receipt-sha256 <independently-retained-receipt-file-sha256> --execute
```

Default backup is **read-only preflight**, not success. Only `--execute` creates
new encrypted generations. Retain versioned configs/anchors for audit, but restore
uses the independently pinned receipt's old source identity and the recovery
config's pinned key/local audit path; it does not require old absolute source or
anchor paths. Configs contain paths/public fingerprints, no passwords. Sources must be frozen; changing
a release means a new source version/anchor/config, not silent discovery of data.
Repeated same-day same-config/commitment jobs reverify ciphertext without replacing
it. Crash retry ignores partials and may adopt a complete verified generation;
missing outbox files are recreated exclusively, conflicting ones stop the job.
Started attempts without result stay visible as interrupted/review-required.

Local durable records: backup ID, UTC start/end, local source/destination,
file/byte counts, SHA256s, duration, status, typed reason, restore status. Failure
detail is a type/code rather than arbitrary exception text. CLI nonzero on errors
or degraded health; Scheduler logs locally, no Telegram send. Check last result,
overdue>26h, missing/mismatched media, reserve, ciphertext drift, interrupted work
and monthly successful private-key restore>31days. Log corruption is degraded,
never HEALTHY. Health is local scoped evidence, not custody acceptance.

## Recovery points / retention — no delete implementation

One unique daily point per config/source commitment. The first successful daily
point in an ISO week and calendar month is also labelled weekly/monthly; these
are distinct dated recovery points across periods, not independent media copies.
Keep30days of daily,12weeks of weekly,12calendar months of monthly. Preview only
lists aged candidates after all applicable horizons; it **cannot delete**.
No pruning/rotation cleanup API, scheduler action or delete flag exists. Partials
and logs accumulate;4096-generation /8192-local-entry bounds fail closed. Budget
capacity and separately authorize maintenance before these limits.

## Windows Scheduler — prepare vs register vs actual acceptance

```powershell
.\scripts\register-backup71-task.ps1 -Python <verified-python.exe> -Repository <reviewed-checkout> -Config <approved-config.json> -LogDirectory <local-logs> -XmlOutput <new-task.xml> -Mode Backup -At '02:00'
# After reviewing that new XML/config/keys and current user scope:
.\scripts\register-backup71-task.ps1 -Python <verified-python.exe> -Repository <reviewed-checkout> -Config <approved-config.json> -LogDirectory <local-logs> -XmlOutput <another-new-task.xml> -Mode Backup -At '02:00' -Register
```

Default mode is Preflight, not backup. Explicit Backup+Register enables a daily
job for the approved config. Daily trigger uses **host local time**, while logs
and tier grouping use UTC; operator records timezone/DST policy. Task is Limited,
Interactive user token, IgnoreNew, StartWhenAvailable, five-minute maximum; no
password stored, elevation, execution-policy bypass or firewall/security changes.
Interactive means **user must be logged on**. No claim of24/7/logoff coverage;
noninteractive service identity/secure key recovery is a separate operating setup.
Existing task names/XML are never replaced. Registration access denied is BLOCKED,
not grounds to request whole-drive access or silently elevate. Monthly private-key
restore is supervised; daily health exposes missing/overdue drill, not fake success.

Synthetic Scheduler acceptance uses `scripts/backup71_acceptance.py prepare` on
two brand-new paths; this creates only test source/keys/config/marker. Register a
uniquely named acceptance task, Start-ScheduledTask, observe completion/code0 and
actual backup log, then `verify` for decrypt/restore parity. Disable the acceptance
task afterwards. These are new implementation acceptance tests, not repeated
Binance sampling or proof of production scheduling.

## Drive and alerts

Each successful backup emits unique dated/ID-named paths-free receipt,
`.receipt.sha256` (exact receipt-file bytes) and ciphertext `.anchor.sha256` in
local state's `outbox`. Receipt has source version,
plaintext source commitment, ciphertext/payload hashes, verification status and
receipt ID/hash; **no private key, passphrase or full personal path**. Upload only
those three small files to the approved custody subfolders; never upload the large
data or overwrite existing anchors, especially old root `anchor.sha256`.

No Drive capability is connected in this Codex environment. Operator uploads the
unique files, records Drive file IDs, downloads/readbacks actual bytes and compares
SHA256 with local outbox; preserve dated receipt. Folder ID
`14teJ9-6I9etUzh7ai3cArfIzJc1aaL6Z`; earlier root anchor remains untouched. Local
outbox creation is **not upload success**, same Google owner is not independent
custody/WORM, and MFA/retention/custodian are not attested by this software.
No suitable non-secret Telegram integration was exercised; notification delivery
is **NOT VERIFIED**. Scheduler exit/health/local logs are implemented, not remote
alert acceptance. No production schedule, private-key provisioning or real source
selection is claimed by CI or synthetic Windows acceptance.
