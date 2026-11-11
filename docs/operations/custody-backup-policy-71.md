# ATLAS Quant Lab — Custody & Backup Policy (Issue #71)

Status: **OWNER-APPROVED POLICY / IMPLEMENTATION NOT YET VERIFIED** (2026-10-25).
Project: AQL-CRYPTO-RESEARCH-001.

## Boundaries

- This document authorizes a policy baseline; it does **not** claim Windows scheduled tasks, encrypted backups, automated cloud uploads, WORM, independent custody, or production disaster recovery are operating.
- No automatic deletion, overwriting of cloud anchors, or secret uploads. No production acceptance without separate evidence.
- Scope limited to ATLAS-owned data and directories, never blanket permissions or retention on the entire external drive.

## Retention targets

| Tier | Target | Acceptance prerequisite |
| --- | --- | --- |
| Daily operational backup | F: / ATLAS-only, retain 30 days | Tested scheduled job, success/failure log, capacity limits |
| Weekly backup | Retain 12 weeks | Verified distinct recovery point |
| Monthly backup | Retain 12 months | Verified distinct recovery point |
| Offsite anchor | On each approved data release | Unique immutable-style filename, SHA256 readback, receipt |
| Restore drill | Monthly | Isolated restore, SHA256 verification, audit receipt |

**Deletion remains disabled** until a tested retention engine, owner-controlled recovery path, and reviewed deletion safeguards exist. Do not confuse retention targets with deletion authorization.

## Current evidence (bounded sample only)

- Historical sample: four Binance CSV files, 5,400 bars; earlier hashes and restore/reimport evidence recorded in Issue #71.
- Cloud Drive folder: `ATLAS-Independent-Custody` (ID `14teJ9-6I9etUzh7ai3cArfIzJc1aaL6Z`).
- Cloud `anchor.sha256` (ID `1vlWWf6aHjShSEy6ZC6-fqPFiVfOcPvJy`) fetched/read back as 64 ASCII characters: `5fe4018a3b490cd64fb998c7b5d9afbd5bbf76a1868cc83194cb7dfc7f2d0c0d`.
- Local `custody-manifest.json` hash match: **owner-confirmed** fresh PowerShell result, not independently executed by cloud assistant.
- Protected local directory `F:\\ATLAS\\protected-custody`: ACL write-denial test passed for non-elevated Windows user; does not restrict elevated Administrators or SYSTEM.
- Drive folders created and read back: `anchors`, `receipts`, `restore-drills`; original anchor remains in root.

## Security and custody limitations

- Same owner's Google account is off-device storage, **not** independent custodian or WORM. Account owner/admin can delete or alter files.
- MFA must be verified by owner or authorized security evidence; not assumed enabled.
- Encrypt backups with a recoverable key and independently protected recovery material. Do not place keys in Drive receipts or GitHub.
- Use append-only versioned anchor names in process; never rely on filename conventions alone as immutability guarantees.

## Acceptance checklist

1. Implement and test Windows daily/weekly/monthly backups with least privilege, ATLAS-only scope, bounded resource usage and failure alerts.
2. Produce dated SHA256 manifests and non-overwrite custody receipts; cloud upload + independent readback comparison.
3. Validate encryption/decryption and offline key recovery in an isolated restore drill.
4. Verify monthly full recovery, capacity monitoring, failure handling, and retention safeguards; no automatic purge before signoff.
5. Establish independent custodian or enforceable immutable retention if strict independent custody is required.
6. Keep Issue #71 open until evidence exists. Issue #77 PIT and research evidence remain separately gated.

## Evidence handling

Record execution date, host, tool/version, source scope, destination, SHA256 values, test outcome, and failures in Issue #71 or versioned custody receipts. Do not commit raw market archives, credentials, recovery keys, or sensitive personal data.
