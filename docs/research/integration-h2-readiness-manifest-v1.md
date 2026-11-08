# ATLAS H2 / aql.integration.h2.readiness-manifest.v1 — UNEXECUTED

Authority: owner provisional B [#205/6717854599](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-6717854599). This deliverable is **readiness-only**; no owner-private E: byte read/run/export, no change to existing private Warehouse, no unsigned F5, no G0, Paper/live, trading or PR merge. Earlier H [run #42451351167](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/42451351167), 4/4 synthetic CI, independently Audit #256 **ACCEPT_IN_SCOPE** on #6717825617; do not repeat or upgrade that scientific status.

## Versioned exact-head source manifest (refresh before any future authorized operator)

| Role | Draft PR | Pinned head | Consumer role |
|---|---|---|---|
| Integration | #271 | UPDATE_AFTER_H2_FINAL_COMMIT | H2 gate only |
| Core | #275 | `99c27ea2c1a4d41aaae361141301a8a9ea3b33c3` | Core245/253 query + same-root research WAIT |
| Scanner | #277 | `3c82448702c9ae35783716e4e2c3b640010db97c` | AST/signal decisions only |
| Factory+Lab | #267 | `52504ad59d75976ce45fb8f75c1b278c3d1b0975` | next-eligible fills + Decimal bps, immutable ledger, Lab |
| Discoverer | #276 | `1cb70f1212283fe34117882d18e0501fc6409fe7` | optional; manual AST cannot depend on signed F4 |
| Work235 | frozen | `6acbcc7fc243b132f58170df4c6469bbf7f4eff8` | two old frozen TEST_ONLY strategy definitions |

All role PRs are OPEN/DRAFT/UNMERGED at manifest construction; no silent merge. These are git object integrity pins, not independent data provenance or policy authority.

## Existing contracts — no new execution engine

1. Core `aql_core_h_portable_query_v1.adapt_verified_recovery_month`: must consume **same-session original source–verified** `read_recovery_diagnostic` output. Distinguishes Core245 native `core245_native_query_sha256` from Core253 local `core253_local_query_sha256`, source ZIP, manifest, Warehouse, original recovery-file bytes, month, source coverage, range, decision cutoff. Self-sealed fixture is NEVER evidence of genuine source. No point-in-time known-at is invented.
2. Scanner `tools.scanner_strategy_f.research_strategy_plugin.register_strategy_plugin / evaluate_strategy_plugin / verify_factory_signal_batch`: pinned AST id/version/config digest, definition digest, indicator parameters, evaluator code SHA, Core253 range query SHA and closed-bar decision cutoff. Explicit COMPLETE/PARTIAL/UNKNOWN, expected/observed/missing, ENTRY/EXIT/NO_SIGNAL/UNKNOWN; manual third AST does not need optional Discoverer F4. Scanner never declares fills or PnL.
3. Factory `run_factory_h_generic_research`: exact Scanner verified batch + bounded Core253 query + independent `operator_cost_policy` schema `aql.factory.h.generic-cost-policy.v1`; cost fields `fee_entry_bps, fee_exit_bps, spread_entry_bps, spread_exit_bps, slippage_entry_bps, slippage_exit_bps, funding_bps_per_bar` (Decimal strings); SPOT/LONG; strict next eligible open/UNKNOWN ambiguity. `SYNTHETIC_TEST_EXPLICIT` **must not** be promoted to original-source economic policy. `OWNER_DECLARED_RESEARCH_SCENARIO` needs *separate* owner cost authority and remains NOT independent economic attestation, even when populated. No defaults chosen for owner. Original zero-cost F2 is diagnostic only.
4. Existing Factory SQLite v2 `factory_h_research_results_v1` immutable SHA+canonical JSON; Lab `evaluate_immutable_ledger` consumes sealed ledger, returns descriptive risk/uncertainty/sensitivity metrics (not strategy approval, alpha, OOS/PIT or observed fills). Integration `atlas_h_generic_secretary_bridge.deliver_generic_research_wait` binds packet+persisted package+Factory receipt to Core `route_generic_research_result/read_generic_research_result_route`; same existing Secretary SQLite `h_generic_research_routes/events` stores `WAIT_RESEARCH_REVIEW`, idempotent event/readback. All Source ACK, Strategy Approval, Factory Consumer ACK, Research Review ACK must remain **null**, holdout `SEALED_UNOPENED`, F5 denied, Paper `NOT_ACTIVATED`, trading `NONE`.
5. No writes to RawVault, original owner E: Warehouse/source, no uploads/CI of raw bytes. Only a separately approved isolated local results SQLite (outside original source directories) could be written in a future owner-authorized operation.

## H2 authorization gates in mandatory order

Preflight `tools/atlas_h2_readiness_preflight.py` is a *pure* JSON-only input validator. It never opens owner-private files, never reads Warehouse and cannot grant legal authority. Exact head mismatch or invalid 15m bounded range => `BLOCKED_CONTRACT`; no independently scoped owner permission => `WAIT_SOURCE_PERMISSION`; absent, zero or not explicitly owner-approved nonzero SPOT cost scenario => `WAIT_COST_POLICY`; no separately verified source rights, publisher PIT, source/manifest and **distinct** Core245 vs Core253 query identities => `WAIT_PROVENANCE`. Complete **self-reported synthetic** values produce `READY_FOR_OWNER_AUTHORIZATION` only: not original execution permission and not evidence that a self-declared receipt, rights or PIT is true. A later actual operator must re-verify authentic evidence in the owner session and fail closed if any condition differs.

**Required owner inputs in a future separate decision:** original data folder/approved read-only access and bounded month/range/strategy; cost scenario *each* of the seven named Decimal-string components and authorization scope; source rights/custody and PIT limits (if NOT_ATTESTED, never claim a PIT study); isolated approved results directory; explicit no-export policy and execution approval. This H2 package does not solicit those inputs for execution now.

## Future owner-local template — INERT TEXT, NOT EXECUTED, NOT RUN-READY

```powershell
# DESIGN TEMPLATE ONLY. Do not run: H2 has NO permission to read owner-private E:.
# Fill only after separate scoped owner approval AND independent Audit H2 readiness.
# git checkout --detach <EXACT_H2_INTEGRATION_SHA>
# python -m tools.atlas_h2_readiness_preflight --request-json '<PUBLIC_SANITIZED_JSON_ONLY>'
# STOP: this preflight does not launch, connect to, or read E:.
# A separate future owner-authorized read-only operator must be designed,
# approved, source-verified and pinned. It does not exist in this template.
```

## Evidence contract / permitted final H2 status

Provide: exact PR SHAs, preflight source code SHA, bounded request and strategy SHA (no E: paths), absence of private bytes in CI, test outcomes for NO_PERMISSION/COST/PROVENANCE/HEAD/RANGE/ACK, prior H accepted link, and no-private-I/O statement. Report `READY_FOR_OWNER_AUTHORIZATION` as *preparation readiness only*, or `BLOCKED_CONTRACT` and exact predicate when failing; no `RESEARCH_E2E_DIAGNOSTIC_PASS` for H2, signed F5, G0 or Paper.

Separate owner approval and independent source rights/PIT economic validity remain outstanding. No private data or holder access attempted in H2.
