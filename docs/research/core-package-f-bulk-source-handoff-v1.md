# ATLAS Package F — Core F0–F2 handoff (PROVISIONAL)

Parent: #274. Source order: Core #269 comment 6655595682. New Core branch is stacked read-only on open/unmerged Core E #269 HEAD `3af5b66d2b381b853a6b5be32c38b3d3d02e1ea7`. Core #226/#211/#245/#253 remain canonical; we do not duplicate vault, warehouse, historical byte parsing or frozen contracts.

## F0 explicit initial target and cost bounds

One configurable initial research cohort: **2024-01 through 2024-12**, 12 Binance Spot BTCUSDT native15m monthly ZIP objects with separate publisher `.CHECKSUM` each. Previously pinned February and August are inventory markers, not newly acquired, and default plan attempts only ten new monthly sources. Each month expects 96 UTC 15m bars per day (2,688 leap-February / 2,784 for a 29-day month; 2,880 for a 30-day month; 2,976 for a 31-day month), exact UTC grid. Total expected year 35,136 bars including retained inventory; target new-month actual bars and raw ZIPs remain UNKNOWN until source is read.

`research_wp_r0/aql_core_f_bulk_source_v1.py::build_manifest(first,last,max_workers)` returns immutable schema `aql.core.f.bulk-source-manifest.v1`, exact expected filenames/source URLs, independently separate publisher checksum URLs, per-month bar counts, explicit UNKNOWN source SHA fields and deterministic SHA-sealed manifest; max 4 workers (default 3). Hard limits: **8,000,000 ZIP bytes and 512 checksum bytes per new month**; default 10 new months bound is 80,000,000 ZIP bytes plus 5,120 checksum bytes (network overhead excluded). Private staging/warehouse can need additional disk; allow e.g. >=3x worst-case archive total plus RAW/SQLite overhead, confirm actual free disk before transfer. Publisher terms/licence and authenticated origin must be verified by the authorized private custodian.

## F1 private acquisition only (conditional)
`acquire_private_batch` requires explicit network permission, source-rights review and independent publisher-origin confirmation; private directory must exist and be permission-restricted. It bounds parallel fetches, fetches checksum separately first, uses existing Core #226 `verify_native_month` for ZIP checksum/member/12-column/UTC/gap/census checks, fsyncs create-only originals and never writes historical OHLCV into public GitHub/CI. Existing unverified files remain `REJECTED_QUARANTINED` pending operator reconciliation (no overwrite). Network errors are returned as rejected reasons without private path leakage. **This is bounded best-effort batch execution, NOT an uninterrupted range-request resume engine:** already staged files need explicit independent reconciliation; no automatic resume of partial downloads or file reuse. A separate resumable checkpoint/partial-range transfer design remains needed if required by the private runner. Caller-supplied publisher-origin confirmation is NOT an independent signature/attestation and no 2024 publication timestamp is claimed.

## F2 batch coverage ledger and explicit scope boundary
`build_coverage_ledger` emits immutable `aql.core.f.bulk-source-coverage-ledger.v1` with `ACCEPTED_PREFLIGHT`, `REJECTED_QUARANTINED`, `MISSING_SOURCE`, `RETAINED_PREVIOUSLY_PINNED`, exact denominator and null absent parent SHAs. `ACCEPTED_PREFLIGHT` means original-format ZIP/CHECKSUM byte/checksum and native bar validation **only**; never silently `RAW_COMMITTED`, actual warehouse/#245/#253 query, strategy approval or PIT. Positive original RAW+query evidence MUST only be produced later in authorized private runner by canonical Core #211/#226/`aql_core_dual_query_identity_map_v1` and Core C/D Secretary, with separate Source ACK, research-policy approval and Factory consumer ACK. Partial/missing months remain excluded from source-dependent historical research.

**Current environment is SOURCE_ACCESS_REQUIRED:** current Project/Library accessible search and prior Core #273 inventory did not expose any new original monthly archive plus separate trusted publisher CHECKSUM bytes; no authorized private runner with verified original bytes was supplied. No network fetch or physical original-source byte admission was performed. F0 manifest and no-source F2 ledger are engineering evidence, NOT historical ingestion, policy approval or actual backtest.

## One runnable private handoff / no public source bytes

Plan only, zero network:

```bash
python -m research_wp_r0.aql_core_f_bulk_source_v1 --first 2024-01 --last 2024-12 --max-workers 3
```

Authorized private runner only, **after custodian independently confirms publisher terms, repository/runner isolation, restricted permissions and source authenticity**:

```bash
python -m research_wp_r0.aql_core_f_bulk_source_v1 --first 2024-01 --last 2024-12 --private-dir /private/aql/historical --max-workers 3 --allow-network --permission-confirmed --terms-reviewed --publisher-origin-confirmed
```

The private path is a placeholder, not a path verified as existing or mounted. The latter command has NOT been run in this session. Quarantined/checkpoint state needs operator review prior to retry. No source checksum/ZIP evidence may be manufactured. No separate per-month Audit; Factory leads one exact pinned final batch F gate after genuine source admission + independent research-only NON_PIT policy approval. G0, holdout, operational Paper/trading and PR merge remain prohibited.

## OWNER ACTION — execute private F1/F2 (2026-11-05, #275/6655810787)

**This is the single actionable access handoff, NOT proof that the private runner was accessed.** On the current connector session only GitHub source and engineering CI are accessible; the publisher's ZIP and independently obtained CHECKSUM, owner's licensed private staging directory, and permitted private executor have **not** been presented or inspected. F1 and actual F2 **EXTERNALLY BLOCKED / READY_TO_RESUME**, and the code MUST NOT report accepted historical RAW, native/local query or Secretary proof.

**Owner's one action:** provide an explicitly approved, private, isolated executor to the Core owner with writable private storage and authorized HTTPS read access to `data.binance.vision`, together with separately authenticated publisher CHECKSUM access and written rights/terms confirmation. The executor must be able to run the pinned repo branch with existing RAW #211 and Core warehouse #226 dependencies and retain the real originals privately. Do not attach original market ZIP/CSV or credentials to GitHub comments/public CI.

**Preconditions to verify on that private executor:**
1. Code pinned to Core F #275 exact reviewed HEAD; Core #226 canonical source module and #211 RawVault installed and accessible; Python 3.11+ recommended, do not silently replace frozen contracts.
2. Source permission/licensing, publisher TLS/domain and independent CHECKSUM issuance provenance documented by the operator. The CLI `--publisher-origin-confirmed` is **operator declaration**, not cryptographic issuer-signature verification. A matching remotely fetched `.CHECKSUM` proves byte consistency with what that endpoint served, **not independently that the publisher issued it in 2024**.
3. Confidential private source directory on isolated disk, free disk and backed-up custody path, strict user-only permissions. For 10 new months the existing code bounds download payload to 80,000,000 archive bytes + 5,120 CHECKSUM bytes (plus HTTP/TLS overhead). Budget **at least 256 MiB temporary staging**, plus separate verified RAW Vault, normalized decompression (up to 16 MiB CSV per month), warehouse SQLite/WAL indexes, backups and monitoring; this is a *minimum planning allocation*, not a measured actual footprint. If insufficient disk or rights, stop before transfer.
4. Existing February/August are **previously pinned only**; do not reacquire or relabel as newly verified. Dataset is BTCUSDT Spot native 15m monthly 2024. Preflight refuses gaps/duplicate 900,000ms bars, unexpected native CSV/member or CHECKSUM drift. Complete-year planned count **35,136** bars (including pre-pinned months); actual 2024 new-month admission count must be obtained from real receipts, not this plan.
5. Protected logging: only sanitized metadata/status/hash/census may leave the executor. Never publish raw ZIP/CSV, credentials, access tokens, original OHLCV or protected paths. No PIT, policy approval or trading inferred.

**Safe local commands** (run on the **authorized private machine**, inside pinned checkout; `/private/aql/historical` is an example, not a verified location):

```bash
set -euo pipefail
umask 077
mkdir -p /private/aql/historical
chmod 700 /private/aql/historical
df -h /private/aql/historical
python -m research_wp_r0.aql_core_f_bulk_source_v1 --first 2024-01 --last 2024-12 --max-workers 3
# Only after operator-approved publisher rights, HTTPS/issuer-source verification,
# independently obtained CHECKSUM authority and sufficient private disk:
python -m research_wp_r0.aql_core_f_bulk_source_v1 \
  --first 2024-01 --last 2024-12 \
  --private-dir /private/aql/historical --max-workers 3 \
  --allow-network --permission-confirmed --terms-reviewed \
  --publisher-origin-confirmed
```

**Behavior and limitations:** Existing implementation is bounded concurrent full-file fetch, not byte-range resumable. Repeated runs do not safely resume existing ZIP fragments; pre-existing paths are quarantined for manual read-only reconciliation and must never be overwritten blindly. `ACCEPTED_PREFLIGHT` = checksum/native ZIP/UTC grid validation only. **The current F1 CLI does not itself perform Core RAW #211 admission, warehouse #226 readback, native #245 or local #253 query execution.** These remain a separately guarded F2 action on the *same private retained original bytes*, using existing `aql_authenticated_historical_admission_v1`, `aql_core_backbone_local_v1`, and `aql_core_dual_query_identity_map_v1`, with required actual source bytes, independently authenticated chain and policies. Do not substitute a new ingest engine or manufacture successful query receipts. If the actual runner cannot execute that canonical path, return `F2_BLOCKED` with exact missing dependency.

**Required single sanitized return packet for Core/Factory** (no source payload):
- Exact owner checkout SHA; private executor identifier that does not expose secrets; access approval evidence reference; publisher issuer/HTTPS/checksum provenance reference and observed capture timestamp (never backdated historical available_at).
- For each of 12 months, exact final `ACCEPTED_PREFLIGHT | REJECTED_QUARANTINED | MISSING_SOURCE | RETAINED_PREVIOUSLY_PINNED`, actual observed bars and expected bars, original ZIP SHA + separate CHECKSUM-file SHA and native member SHA **only when validated**; unknowns strictly `null`; explicit missing/rejected denominator.
- For every *actually* admitted month: separate RAW #211 immutable admission/readback SHA and receipt, #226 warehouse committed/readback receipt, independent #245 `price_query_sha256` and #253 `query_sha256` parent receipts (NOT aliased), coverage, 900,000ms UTC opening/closing and negative gap/duplicate census, clean restart replay/trace. `ACCEPTED_PREFLIGHT` cannot be relabeled RAW admitted.
- Distinguish Source ACK, independent versioned Strategy/Policy Approval, and Factory Consumer ACK; without trusted historical policy approval, preserve Secretary `NOT_ENQUEUED` and Factory historical Lab `NOT_EVALUATED`.
- Retrospective classification `RETROSPECTIVE_NON_PIT`, issuer historical available-at `NOT_ATTESTED`, Paper `NOT_ACTIVATED`, trading `NONE`; Source/PIT/policy external blockers explicitly listed.

**Factory integration contract:** Factory F4/F5 leads only after the real Core batch custody+dual query receipt and separately approved Scanner #277 research-only policy exist. Use exact SHA-pinned F owner branches, store each acceptance/rejection/missing denominator immutably, reject wrong Core#245/#253 SHA/symbol/cutoff/coverage and run one final F audit packet. Already accepted B/D/E/#272/#273 engineering suites are not new historical proof and need no repeated independent review.

**State at handoff:** `F0_COMPLETE`; `F1_SOURCE_ACCESS_REQUIRED` (no authorized private runner or newly authenticated source bytes available to this session); `F2_EXTERNAL_SOURCE_BLOCKED` (no real new-month RAW/warehouse/native/local query evidence); `PIT_NOT_ATTESTED`; `POLICY_NOT_APPROVED`. No code changes made as part of this owner-access handoff, no extra source-blocked PR, no merges/G0/trading.

## F2 NEW: owner-reported Windows 10/10 F1 evidence and private one-command intake (#275/6656669009)

**Evidence boundary.** The owner reported a local Windows F1 result on the private E: drive: 10 NEW monthly objects with `ACCEPTED_PREFLIGHT`, 0 new rejects/missing, Feb/Aug `RETAINED_PREVIOUSLY_PINNED` **inventory only**, without original retained bytes independently re-read. The following two SHA references were relayed through the owner's PM handoff; they have NOT been independently proven against the private bytes in this GitHub-only session:

```text
F1 manifest SHA256: f559c82c2c3827382338ab8f84f4a71a1e6705e08105b9b1bdbfaceb3bcbc8b7
F1 coverage ledger SHA256: 303cf791ff01be9d74f824909814e7a015ae6b265ba61e824f374f21648a2ab7
```

No public repository change pretends to contain private original ZIP/CSV or original CHECKSUM bytes. F1 receipt validity is separate from actual F2 RAW admission.

**Core-owned code delta:**
- `aql_core_f_ntfs_acl_v1.py`: on Windows, inspect actual NTFS DACL ACEs and the effective process token, not POSIX `st_mode`; reject `Everyone`, `Users`, `Authenticated Users`, unknown allow principals, deny/unsupported ACE types and inherited unsafe ACEs. No bypass flag. Only the current SID, SYSTEM and Administrators are permitted principals; the OS must authorize actual generic READ/WRITE. A Windows directory inherited from a permissive parent is **not** private just because Python's `chmod(0o700)` was called. This is a deliberately restrictive owner-private custody profile. Linux POSIX guard remains unchanged.
- `aql_core_f_private_f2_v1.py`: F1 saved output JSON `{"manifest":..., "coverage":...}` must match both out-of-band SHA pins; locally re-read original private ZIP and CHECKSUM for all TEN new months, re-fetch the separate original publisher CHECKSUM through HTTPS in the authorized private runner, re-run existing Core #226 monthly native ZIP/UTC/bar validation, and refuse an incomplete batch **before** any RAW writes. It then uses canonical `RawVault` #211, `admit_local_original` #226, fresh read-only native #245 and indexed local #253 query re-read, and `bind_dual_query_identities`. Unknown historical `available_at` remains `None`, PIT `NOT_ATTESTED`. No scanner/policy/strategy/Factory ACK is automatically issued, and no new parser or vault is introduced.
- If a private source or SHA drifts: quarantine/report, **no new source automatically admitted**. Any failure after some immutable commits requires inspection of committed generations and idempotent replay before rerun, never deletion/overwrite.
- Detached local authorization document must be independently issued/reviewed and its SHA pinned through a separate trusted channel. A caller supplying matching JSON+SHA is only local *document integrity*, **not a cryptographic issuer signature, proof of license, 2024 publisher issuance or PIT**. The operator must also independently verify provenance/rights before exercising `--allow-raw-admission`.

**Windows operator check** (read-only; do not weaken ACLs):
```powershell
icacls "E:\AQL_PRIVATE\historical"
icacls "E:\AQL_PRIVATE\core_warehouse"
icacls "E:\AQL_PRIVATE\raw_vault"
```
Ensure only the executing user's exact SID, LocalSystem and built-in Administrators receive allow ACEs, *including inherited entries*; personally review the NTFS effective access and resolve unsafe inherited grants using approved IT procedure, never `chmod(0o777)` or an env bypass. The root paths above are illustrative and have **not** been inspected in this session. Create private warehouse/vault directories and allocate sufficient private storage before running.

**One owner-run command on the actual authorized private Windows host** after preserving F1's full JSON output as a file, separately re-verifying source rights/HTTPS publisher provenance, producing the detached private custodian authorization JSON, and obtaining its independently published SHA:

```powershell
python -m research_wp_r0.aql_core_f_private_f2_v1 --f1-output "E:\AQL_PRIVATE\f1-owner-output.json" --private-dir "E:\AQL_PRIVATE\historical" --warehouse-root "E:\AQL_PRIVATE\core_warehouse" --vault-root "E:\AQL_PRIVATE\raw_vault" --authorization-json "E:\AQL_PRIVATE\custody-authorization.json" --authorization-sha256 "<AUTHORIZATION_SHA256_FROM_INDEPENDENT_TRUST_CHANNEL>" --expected-manifest-sha256 f559c82c2c3827382338ab8f84f4a71a1e6705e08105b9b1bdbfaceb3bcbc8b7 --expected-ledger-sha256 303cf791ff01be9d74f824909814e7a015ae6b265ba61e824f374f21648a2ab7 --allow-network --recheck-publisher-checksums --allow-raw-admission
```

No shell redirection of raw source to console/GitHub; CLI prints only sanitized receipt metadata. Local F1 JSON must be the **actual** owner-run output, never a reconstructed count from the PM comment. `--authorization-sha256` is deliberately unfilled; this command must remain blocked until separately trusted owner/custodian authority and verified source rights are available. If the publisher is unreachable for independent checksum re-fetch, stop at `F2_SOURCE_OR_ISSUER_CHECK_BLOCKED`, do not relabel as admitted.

Authorization JSON schema (example **shape only**, not an issued approval):
```json
{
  "schema": "aql.core.f.private-custody-authorization.v1",
  "owner_permission": true,
  "rights_evidence_reference": "OUT_OF_BAND_DOCUMENT_REFERENCE",
  "issuer_provenance_reference": "OUT_OF_BAND_ISSUER_SOURCE_REFERENCE",
  "publisher_checksum_issued_via": "SEPARATE_PUBLISHER_HTTPS",
  "authorized_months": ["2024-01", "2024-03", "2024-04", "2024-05", "2024-06", "2024-07", "2024-09", "2024-10", "2024-11", "2024-12"],
  "source_class": "ORIGINAL_PUBLISHER_RETROSPECTIVE_NON_PIT",
  "historical_pit": "NOT_ATTESTED",
  "trading_authority": "NONE"
}
```

Do not copy the example as if it were actual external approval. Private authorities need actual evidence references and a trusted SHA bound to the exact document. The CLI verifies integrity/shape/parents and actual current publisher TLS CHECKSUM agreement; **it does not cryptographically verify an issuer signature or independently authenticate an out-of-band signer**. A 2026 HTTPS checksum fetch cannot attest 2024 historical availability. The legal data-use right is a separate owner/custodian check.

**Expected sanitized F2 return to Factory**: exactly 10 new original months only if every new-month ZIP/CHECKSUM validates and actually commits to the existing RAW Vault/warehouse with dual query receipts, distinct #245 `price_query_sha256` and #253 `query_sha256`, and source SHA/cutoff/bar census. Feb/Aug stay **2 inventory-only**, not `12/12 RAW`. The command returns `secretary_historical_strategy_route=NOT_AUTHORIZED`, `factory_consumer_ack=null`, PIT `NOT_ATTESTED`, trading `NONE`. Core source integrity can be acceptable for retrospective NON_PIT custody while still not proving historical scientific PIT, Scanner policy approval or Factory historical execution.

**This owner session did not run the Windows private command or inspect E: bytes.** F2 historical source RAW/warehouse/query proof remains unverified here. Factory F4/F5 must verify exact Core F HEAD/receipts and independent Scanner F3 approval before activation. One final Audit after genuine source/strategy/Factory evidence, no monthly micro-gates, no merge/G0/holdout/trading.


## F2 owner-local completion and Core F5 security checkpoint — 2026-11-05 (supersedes stale F1/F2 blocked state above)

The owner subsequently supplied an actual local Windows F2 CLI output (see #275/6658725082) from `E:\ATLAS\repo`, **not** private source bytes accessible to this repository or CI. The reported command exited successfully, `F2_EXECUTION_PASS_REVIEW_RECEIPTS`; 10/10 admitted original BTCUSDT 15m months (Jan, Mar–Jul, Sep–Dec 2024), 29,376 bars, each `RAW_AND_DUAL_QUERY_READBACK` with separate #245/#253 query digests and warehouse receipt. Feb/Aug remain inventory-only (2), never silently counted as admitted.

Pinned owner-reported evidence (not independently verified by GitHub):
- F2 report canonical SHA: `daf1208bf824e58040858a817c709f7943c19668dc23ce3fd3b0368e01156f40`
- F1 manifest: `f559c82c2c3827382338ab8f84f4a71a1e6705e08105b9b1bdbfaceb3bcbc8b7`
- **Fresh** F1 ledger (replaces the older stale ledger example above): `557c38ecb58d9c0c22784ee105c6cb0a29bf2d4dc2ba44f5ed4e2a08c1a89862`
- Owner-authorized local file *bytes* SHA: `a954b81e67cf731b19aba73d916dda59c80a55ed93442d6abab086972e18cbef`; distinct F2 *canonical JSON document* SHA: `ced74dade0ee151eff61109bddb912c5203cbb4d091f6ba77545cb262e332439`. Never interchange these two algorithms.

`historical_pit=NOT_ATTESTED`, `trading_authority=NONE`, `strategy_policy_approval=NOT_ATTESTED_BY_CORE`, `factory_consumer_ack=null`, `secretary_historical_strategy_route=NOT_AUTHORIZED`. The 2026 publisher HTTPS checksum is **not** a 2024 issuer-signed historical available-at. Owner attestation is **not** an independent external custodian witness. The real private storage is populated; **do not rerun, overwrite or delete it**.

**Windows security CI:** Actions #42024212839 failed `WINDOWS_ACL_UNSAFE_PRINCIPAL` inside disposable temp fixture. CI runner temp folders may contain unrelated explicit ACEs: `icacls /inheritance:r` + `/grant:r` does not remove those. Production fail-closed ACL validator is unchanged. Follow-up #42036734335 exposed unavailable `Get-Acl` PowerShell module on runner. Current test-only fix at `b0265fd7fae8b9daa10dcf71fea186f43414af2c` uses Windows PowerShell 5.1 .NET `DirectoryInfo.GetAccessControl/SetAccessControl` and replaces the DACL only on disposable test directory; exact-head CI pass **must be checked**, not assumed. The test still asserts a broad inherited ACE is rejected. Separate RawVault Windows locking/`fsync` fixes on `core/rawvault-windows-lock-20261105` commits `cd720cf`/`e368dd4` are **not** in this PR head, and integration must pin the actual dependency.

**Secretary authority boundary:** Core source custody receipt ≠ independent Source ACK issuer approval ≠ versioned Scanner strategy/policy approval ≠ Factory Consumer ACK. Secretary must refuse historical strategy enqueue until authentic separate issuer/policy evidence is available; no self-approved ACK, no synthetic positive attestation. Integrator #271 and PM #274 own cross-module sequencing. This branch is a draft, unmerged; no G0/Paper/live trading authorization.
