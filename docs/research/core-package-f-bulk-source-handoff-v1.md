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
