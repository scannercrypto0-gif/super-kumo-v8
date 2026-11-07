# ATLAS F2 recovery — actual owner-private one-command overlay and provenance (2026-11-07)

State: **implemented on Draft Integration #271; local E: execution NOT witnessed**. Exact Core #275, Scanner #277, Factory #267 commits remain OPEN/DRAFT/UNMERGED. An engineering CI success does not prove an owner-original positive run or F5.

## One Windows PowerShell invocation

Use an **exact, completed Integration PR #271 HEAD SHA**, not `main`. Run in the existing owner PowerShell with Git, Python 3.11+, and network/GitHub access; this creates **new isolated Git worktrees under the operating-system TEMP directory**, not under E: or the old diagnostic runner. Replace warehouse/vault placeholders with their existing real directories only:

```powershell
$h='<EXACT_INTEGRATION_PR_271_HEAD_SHA>'; $p=Join-Path $env:TEMP 'aql-f2-owner-run-pinned.ps1'; Invoke-WebRequest -UseBasicParsing -Uri "https://raw.githubusercontent.com/scannercrypto0-gif/super-kumo-v8/$h/tools/atlas_f2_owner_run.ps1" -OutFile $p; & $p -IntegrationCommit $h -WarehouseRoot '<EXISTING_WAREHOUSE_ROOT>' -VaultRoot '<EXISTING_RAWVAULT_ROOT>' -RecoveryFile 'E:\ATLAS\diagnostic-runner\f2-recovery-evidence.json'
```

The extra optional parameters are `-PolicyFile`, `-TrialLedgerFile`, and `-InventoryReceiptsFile` — only for **already-authentic** diagnostic configuration and receipts. If these are unavailable, **omit them**. The operator will derive the genuine 10-month mapping from read-only Core original-byte/RawVault/SQLite sources and print **one sanitized missing-field JSON**, not a fake Factory PASS. Do **not** manually construct 10 mapping rows. The new private mapping lives in the isolated workspace, whose path is available through `$env:AQL_F2_WORKSPACE` within the same PowerShell process.

The script validates Git HEAD identities for Integration, Core, Scanner, Factory and historical dependencies, stages exact source modules into the newly created detached operator worktree, checks pinned byte-identity/frozen Work235 fixture, and invokes the Python owner operator. It does not `git pull main`, merge any PR, alter any protected source, replay into a source directory, or open a holdout.

## Genuine owner report pins

- Raw JSON file-byte SHA256: `52b47d7d93f5966fffe41ae16cb21486fb14a0753a2821dccc35f4f09e4903d2`
- Separate producer-internal `recovery_sha256`: `0428e7b02b7b57bded9906c49f956b76816c179cd8659d61e1c7f1af1df68220`
- `schema=aql.owner-local.f2-recovery-evidence.v1`; integer `verified_months=10` and `verified_bars=29376`; each actual `entries[]` row has `month,dataset_id,state,bars,source_sha256,manifest_sha256,core245_native_query_sha256,core253_local_query_sha256`.
- The producer's internal canonical SHA algorithm was **not** independently available and must never be claimed recomputed.

`tools/atlas_f2_owner_provenance_v1.py` derives the two report-absent parents `warehouse_receipt_sha256` and `dual_query_map_sha256` from original **immutable** warehouse SQLite generation+admission, sealed stage, actual RawVault bytes/manifest/index, the Core #245 native and #253 local query domains, and the real canonical dual-map binder. This derivation forks ONLY the two unavailable-parent comparison lines from pinned Core #275, preserves original-source checks and no-write tree fingerprints, then invokes the **unchanged Core** verifier again with the derived 10-row mapping. Any mismatch => fail closed.

## Actual Factory diagnostic packet boundary

`tools/atlas_f2_owner_factory_packet_v1.py` requires:
- The two byte-pinned frozen Work235 strategies (already included in pinned checkout; no user reupload), genuine Core receipts, and Scanner 20 evaluated/4 retained unknown.
- An explicit operator-approved **policy JSON** `aql.integration.owner-local-factory-diagnostic-policy.v1` with exactly the fields: `schema,costs,research_window,direction,focus_month,focus_strategy_id`. `costs` has **string** bps values `fee_entry_bps,fee_exit_bps,spread_entry_bps,spread_exit_bps,slippage_entry_bps,slippage_exit_bps,funding_bps_per_bar`; for a SPOT LONG diagnostic, funding must be `"0"`. `research_window` has integer `train_end_exclusive_ms,embargo_ms,holdout_start_ms,holdout_end_exclusive_ms`; existing Factory requires embargo >= 259200000ms. These must come from an intentional **diagnostic policy**, not inferred from source candles.
- A genuine **53-trial source ledger JSON** `aql.integration.owner-local-factory-53-trial-ledger.v1` with exactly `schema,trials,selected_attempt_id,plan_digest`, where each of the 53 actual ledger rows has `attempt_id,candidate_digest,plan_digest,state,duplicate_of`; its selected trial must be actually `PROPOSED` and correspond to the focus month's frozen Work235 definition. The older Factory projection explicitly **requires 53** trial rows. The collector cannot infer genuine prior trial history from the 10-month source report; it never pads the ledger with fabricated historical events.
- Genuine **inventory-only SHA receipts** `aql.integration.owner-local-inventory-receipts.v1` with exact root keys `schema,2024-02,2024-08` (two existing 64-char SHA identities, NOT fake source files). Feb/Aug remain UNKNOWN.

No original data or fill chronology is created. The projection uses **existing AQL indicators, closed-bar rules, next-open modeled trade, explicit fee/spread/slippage assumptions**, and marks intrabar stop/target touch UNKNOWN, never an observed execution. The Factory side rejects absent/invalid fields without constructing a false ledger/score.

When all inputs exist, the old Integration's distinct recovery operator validates the generated Factory packet, creates a **fresh isolated SQLite v2** diagnostics store, runs it twice, and checks `STORED_IMMUTABLE` -> `REPLAY_IDENTICAL`, stable lab/experiment/result digests and different status-bound outer receipt SHA. The verified 10-month source census is 29,376 original bars, 2 TEST_ONLY strategies × 10 = 20 diagnostics plus Feb/Aug 4 UNKNOWN.

## Output and stopping semantics

- Success (ONLY after an owner-private real run): `{"status":"RESEARCH_E2E_DIAGNOSTIC_PASS", ... "f5":"BLOCKED_EXTERNAL_INPUT","trading_authority":"NONE"}` with sanitized digests, and no OHLCV in console.
- No original input/ledger/policy/inventory: **one** `{"status":"PRIVATE_WAIT","missing_fields":[...],"f5":"BLOCKED_EXTERNAL_INPUT","trading_authority":"NONE"}`. A successfully collected ten-row mapping may already have been saved in the isolated workspace; that is NOT E2E PASS.
- Integrity mismatch: `PRIVATE_WAIT` and sanitized error code, NEVER a fake fallback.
- Genuine original F2 SHA remains missing; this path is recovery-only, local and non-PIT. No signed Source/Strategy/Consumer ACK, approval of G0, F5, merge, Paper, trade or holdout authorization. Public CI covers engineering and negative fixtures only.
