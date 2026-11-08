# Core F — RESEARCH_E2E_DIAGNOSTIC read-only original-source seam

**Project:** AQL-CRYPTO-RESEARCH-001 | **Date:** 2026-11-07  
**Owner:** Core #275 | **Receiver:** Integration #271  
**Architecture:** [ADR-F-DIAG-01 on Integration #271](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/271). This diagnostic contract is an independent research-only lane, **not** a waiver or amendment to authentic F5 signed authority.

## Intended use: owner-private read-only query, never F2 admission

Use `research_wp_r0.aql_core_f_research_diagnostic_query_v1.read_original_diagnostic(warehouse_root, vault_root, original_f2_report, *, month)` from the **assembled exact-head** owner-local Python environment. The operator must separately authorize access to the already populated immutable original source and existing Core warehouse. The complete original owner-reported **sanitized F2 JSON** is provided from the private operator's retained local report file; do not reconstruct it or scrape a GitHub comment into a surrogate receipt.

The function verifies the fixed original F2 report digest `daf1208bf824e58040858a817c709f7943c19668dc23ce3fd3b0368e01156f40`, its F1 manifest `f559c82c2c3827382338ab8f84f4a71a1e6705e08105b9b1bdbfaceb3bcbc8b7`, fresh F1 ledger `557c38ecb58d9c0c22784ee105c6cb0a29bf2d4dc2ba44f5ed4e2a08c1a89862`, original canonical custody authorization `ced74dade0ee151eff61109bddb912c5203cbb4d091f6ba77545cb262e332439`, 10 admitted months / 29,376 bars / 2 inventory-only, and the `NOT_AUTHORIZED` Secretary/F5 state. File authorization bytes digest `a954b81e67cf731b19aba73d916dda59c80a55ed93442d6abab086972e18cbef` is a **different encoding** from canonical JSON digest and is not substituted.

Valid requested month: **2024-01, 03, 04, 05, 06, 07, 09, 10, 11, 12**. **2024-02 and 2024-08 are always rejected** at this Core seam and must remain `UNKNOWN_RETAINED_NOT_READBACK` in the 24-attempt downstream census.

For each admitted month it uses the **one existing** path `RAW #211 → warehouse #226 → independent native #245 / local #253`:
- Require pre-existing locked-down warehouse, `warehouse.sqlite`, committed `stage/<packet_sha>/receipt.json`, RawVault `objects/`, `.staging/`, `index.json`, `manifest.jsonl`. Check the directory ACL/permissions and deny symlinks on primary roots, SQLite, vault index/manifest and the requested RAW object. Missing files **stop**, never create substitute data.
- Query the canonical SQLite generation with `mode=ro`, require source ZIP digest equals original F2 month entry; query `query_local` on existing staged original source (which independently rechecks stage/source/derived-bar checksums).
- Rehydrate the **already committed** stage packet into an in-memory `HistoricalLibrary` (only after checking its receipt marker is already present). Use existing `query_price_custody` with the exact original manifest/source SHA. **No `admit_original_bytes`, `admit_local_original`, `execute_local_f2` or second warehouse.** No network or publisher download.
- Call the already instantiated RawVault `read(source_zip_sha256)` (SHA-verifying) and require an existing manifest entry. No `admit`, repair, index rewrite or purge.
- Require each month to have a **complete 900,000-ms UTC native candle grid**, all bar-close timestamps before the cutoff, original/local bar checksums and lower-bound times equal, same manifest/source/cutoff/census and the original **separate** #245 price-query and #253 local-query digests. Original F2 run used full-month `decision_cutoff_ms = month_end_ms + 1000`. This retrospective query cutoff does **not** prove a bar was known in 2024.

## Receiver API shape and log hygiene

```python
from research_wp_r0.aql_core_f_research_diagnostic_query_v1 import (
    ADMITTED_MONTHS, read_original_diagnostic
)

# PRIVATE OPERATOR supplies already validated: warehouse_root, vault_root
# and full original_f2_report from the owner's previously retained file.
for month in ADMITTED_MONTHS:
    result = read_original_diagnostic(
        warehouse_root, vault_root, original_f2_report, month=month)
    sanitized_receipt = result["receipt"]   # metadata + SHA; NO OHLCV
    native_price_bars = result["native_bars"]  # private memory, NO GitHub logs
    local_price_bars = result["local_bars"]    # private memory, NO GitHub logs
    # Integration/Scanner/Factory own the isolated evaluator and causal Lab.
```

The *versioned sanitized receipt* `aql.core.f.research-e2e-diagnostic-readback.v1` includes month, dataset/version, original source ZIP digest, canonical manifest, F2-parent warehouse receipt SHA, independent native245/local253 and prior Core dual map parent SHAs, month boundaries/cutoff, verified bar count, SHA-256 receipt digest, `owner_f2_report_pin_verified=True` and the original pinned F2 SHA **only after the public entrypoint verifies the full owner report**. The internal fixture primitive `_one_read_only` returns `owner_f2_report_pin_verified=False`, never evidence of original owner-private F2 success.

**Important limitation:** the F2 **warehouse receipt SHA and dual-map SHA** are retained/checked as pinned **parent IDs from the authenticated owner-report digest**, not regenerated from a new admission (which would violate read-only). Independent row/manifest/source/grid agreement and both query digests are **actually recomputed** from the preexisting source; neither a parent SHA nor a test fixture equals an independent source-rights signer. The simplified diagnostic local trust does not satisfy real historical PIT or authentic F5 approvals.

**Never put `native_bars`, `local_bars`, original ZIP/CHECKSUM, full source paths, private signing material or protected source files into an Actions log, GitHub comment or uploaded artifact.** Only sanitized SHAs, counts and negative/availability statuses may be public.

Integration owns one owner-authorized operator **command** to combine all 10 month reports, the two frozen strategies × 12 months = 24 immutable attempts (20 eligible + Feb/Aug 4 UNKNOWN), evaluator code/definition/config and per-bar fully closed cutoff, Factory causal fees/spread/slippage/ambiguous intrabar policy, immutable result store/replay and the final `aql.research-e2e.diagnostic.v1` receipt. The Core helper does not select a strategy, create a consumer ACK, execute a Lab or grant Paper/orders/trading authority.

## Independent diagnostic/F5 boundaries

The full signed F5 verifier `aql_core_f5_secretary_authority_v1.py` remains unchanged by this diagnostic; Source ACK (`aql.core.f.historical-source-ack.v1`) and StrategyApproval (`aql.core.f.historical-strategy-approval.v1`) still require out-of-band valid Ed25519 issuer and source/policy/evaluator/strategy witness. There is **no diagnostic authority promotion**. `source_ack_sha256=null`, `strategy_approval_sha256=null`, `factory_consumer_ack_sha256=null`, `secretary_state=NOT_ENQUEUED`, `historical_pit=NOT_ATTESTED`, `trading_authority=NONE`.

Fail-closed cases: missing unverified original F2 report; Feb/Aug inventory-only; wrong ZIP, native245 or local253 digest; wrong month/cutoff/census; missing committed stage/warehouse; raw object path symlink; missing original vault; wrong source provenance or implicit PIT claim. No automatic alternative dataset or downloader.

## Engineering test and real-run status

- `tests/test_aql_core_f_research_diagnostic_query_v1.py`: fixture-only 15m original ZIP→existing Vault/warehouse→native/local independent recomputed queries; dual-query hashes and cutoff; deterministic repeated read; no changes to warehouse/vault file digests; tamper and month rejection; POSIX disposable fixture positives and Windows fail-closed missing-original negative. Separate Core Windows NTFS safety and lock/crash gates remain in place.
- `.github/workflows/aql-core-f-bulk-manifest.yml` runs the focused suite on Linux Python 3.11/3.12/3.13 and Windows Python 3.12.
- These tests **do not use the owner's E: original price bytes**. Only owner-authorized private execution with actual source readback and downstream Scanner+Factory E2E can earn `RESEARCH_E2E_DIAGNOSTIC_PASS`; otherwise report `ENGINEERING_PASS_PRIVATE_NOT_RUN`. Authentic F5 remains separately `BLOCKED_EXTERNAL_INPUT`.

**Scope:** provisional B under PM #275/6703069713; no PR merge, G0, trading, source download, F2 reingest, second warehouse, legal rights attestation or forged signed approvals.
