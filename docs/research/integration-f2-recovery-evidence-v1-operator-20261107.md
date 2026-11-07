# F2_RECOVERY_EVIDENCE.v1 — provisional B, owner-private recovery source gate

**State:** implemented initial Integration-only source gate; **NOT** a complete authentic diagnostic. The original canonical F2 report is unavailable. Never set the legacy `core_f2_report_sha256` to its known digest as a substitute. The known recovery SHA `0428e7b02b7b57bded9906c49f956b76816c179cd8659d61e1c7f1af1df68220` is a **file-byte SHA256 pin**, checked against the actual private file bytes, not an independently verified legal/issuer signature.

## Required private inputs

1. Actual existing owner-local recovery evidence **file** whose SHA256 matches the pin exactly. No generated substitute.
2. Existing owner-local RawVault #211 root and the **same** existing Warehouse #226 root (not a new database).
3. A **separate untrusted mapping JSON** `aql.integration.f2-recovery-evidence.v1` with exactly:
   - `schema: "aql.integration.f2-recovery-evidence.v1"`
   - `source_class: "OWNER_LOCAL_RECOVERY_NOT_ORIGINAL_F2"`
   - `historical_pit: "NOT_ATTESTED"`, `trading_authority: "NONE"`, `owner_f2_report_sha256: null`
   - `entries`: 10 objects, one per original admitted 2024-01,03,04,05,06,07,09,10,11,12, each with **exact keys** `month`, `state: "RAW_AND_DUAL_QUERY_READBACK"`, `bars`, `source_sha256`, `core_245_native_price_query_sha256`, `core_253_local_query_sha256`, `warehouse_receipt_sha256`, `dual_query_map_sha256`. Use the original independently stored inventory references, **not** invented hashes. Feb/Aug inventory-only: no readback.
4. Byte-identical Core `research_wp_r0/aql_core_f_research_diagnostic_query_v1.py` from [Core #275](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/275) assembled in the local checkout with Integration `tools/atlas_f2_recovery_evidence_v1.py`. Both PRs are unmerged.

The mapping is *not* accepted on its own: Core's read-only primitive reopens committed Warehouse, existing RawVault object, stage, original local #253 and native #245, verifies per-bar checksum/time/cutoff, and compares query SHA and 29,376-bar census. Integration recomputes the actual RawVault object SHA256. Missing recovery bytes, mismatched source, absent stage, bad SHA or incomplete month => `PRIVATE_WAIT`. No original F2 report reconstructed or endorsed.

## One source-gate command (not the full diagnostic)

```powershell
& 'E:\ATLAS\.venv\Scripts\python.exe' -m tools.atlas_f2_recovery_evidence_v1 `
  --recovery-file 'E:\ATLAS\private\historical\recovery\actual-evidence-file.json' `
  --mapping-file 'E:\ATLAS\private\historical\recovery\recovery-month-mapping.json' `
  --warehouse-root 'E:\ATLAS\private\warehouse' `
  --vault-root 'E:\ATLAS\private\raw_vault' `
  --owner-private-authorized
```

Paths are placeholders, not evidence of files. Run **only** after authorized owner confirms actual locations and original mapping. Output to stdout is SHA/count-only and reports `SOURCE_READBACK_PASS_DIAGNOSTIC_NOT_RUN` at most. It is **not** `RESEARCH_E2E_DIAGNOSTIC_PASS`. Avoid posting private paths or OHLCV to GitHub.

## Explicit integration blockers to final diagnostic

- Core #275: publish a stable **public versioned recovery source contract** including independently recomputed committed warehouse receipt identity and provably no source writes (not merely comparing a caller-provided receipt parent).
- Scanner #277: locate actual frozen two Work235 ASTs and exact policy/proposal/request/spec receipts. No made-up signature or strategies. The existing Scanner diagnostic 20+4 logic is available but private frozen inputs are not.
- Factory #267: add **distinct recovery input schema** with `original_f2_report_sha256: null`, not the legacy original-F2 field; ensure causal original focus, SQLite v2 immutable replay and no signed authority.
- Integration #271: once owner contracts are ready, wire the versioned recovery source gate into the complete one-command Scanner→Factory operator and run focused regressions. **Do not bypass the original F2 requirement in the old path.**

**Current acceptance:** `RECOVERY_SOURCE_GATE_ENGINEERING_ONLY` pending focused CI, `PRIVATE_WAIT` actual original private readback and full research diagnostic, `F5_BLOCKED_EXTERNAL_INPUT`. No second warehouse, reingestion, original-F2 impersonation, G0, merge, trading or holdout opening.
