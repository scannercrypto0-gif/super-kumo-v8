# Factory H2 — Economic readiness contract / owner cost authorization boundary (2026-11-08)

**Authority:** [owner provisional B #205/6717854599](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-6717854599); [Factory H2 assignment #267/6717855468](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/267#issuecomment-6717855468). **Preparation/preflight ONLY**; original owner E: read/run needs a new explicit permission. No G0, merge, signed F5, holdout, Paper/live or trade authority.

## Frozen verified Factory baseline — do not rebuild or test again

Existing Factory #267 `research_wp_r0/aql_factory_h_generic_signal_adapter_v1.py::run_factory_h_generic_research(packet, isolated_existing_sqlite_v2_path)` consumes real Scanner H verified batch and bounded Core253 query; preserves next-eligible-open causality, no invented intrabar fills, existing `_modeled_trade` Decimal engine, SHA-sealed input/output, immutable first/write + replay-read `factory_h_research_results_v1` ledger, Lab's `evaluate_immutable_ledger`, and a research-review-only Secretary SHA. Old fixed F2 24-attempt/20+4 Unknown lane and signed F5 untouched. Previously accepted synthetic H cross-owner gate Integration #271 `fe29022e4100aa2ec4947cdd3d7e147f34eae990`, CI [#42451351167](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/42451351167) 4/4, independent Audit #256 `ACCEPT_IN_SCOPE` synthetic only. **No new economic/PIT/original-data validation was performed by that gate.**

### Exact cost input contract (no supplied amounts, not even assumed zero)

A distinct SHA-sealed `operator_cost_policy` carries schema `aql.factory.h.generic-cost-policy.v1` and **exact** fields:

| Field | Required rule |
| --- | --- |
| `schema` | Literal version above |
| `costs` | Exact **7** named values below, no omitted, extra, or default values |
| `market`, `direction` | `SPOT`, `LONG` |
| `scenario_class` | `SYNTHETIC_TEST_EXPLICIT` (test-only, `owner_operator_authorized=false`) **or** `OWNER_DECLARED_RESEARCH_SCENARIO` (owner declaration only, `owner_operator_authorized=true`) |
| `owner_operator_authorized` | Exact boolean appropriate to class, but **NOT a trusted approval source** just because it occurs inside a caller-controlled receipt |
| `fill_semantics` | `NEXT_ELIGIBLE_OPEN_UNKNOWN_ON_INTRABAR_TOUCH` |
| `holdout`, `trading_authority` | `SEALED_UNOPENED`, `NONE` |
| `sha256` | SHA computed from canonical policy body, independently cross-bound to Factory input `sha256`/result and persisted Lab/Secretary parent identities |

**All values must be explicitly supplied as Decimal strings in basis points; never fill from guesses or prior diagnostic:**

1. `fee_entry_bps`
2. `fee_exit_bps`
3. `spread_entry_bps`
4. `spread_exit_bps`
5. `slippage_entry_bps`
6. `slippage_exit_bps`
7. `funding_bps_per_bar` — explicit literal **`"0"`** required for existing **Spot** kernel; a funding charge belongs to a separate authorized PERP contract and must not be silently modeled here.

Current `_costs` is already strict: **every** entry must be a string representing finite `Decimal` in `[0,1000]` bps, SPOT funding exactly zero, no missing/extra field. Existing `_modeled_trade` subtracts explicit entry+exit fee/spread/slippage bps from modeled next-open gross return; costs are assumptions, not observed broker fills. A check that numerical inputs are nonzero is NOT a proof that fees/spreads/slippage are realistic, and **a resealed `owner_operator_authorized:true` field does not independently verify the owner**.

### Owner action needed *later* (separate from current provisional B)

Before an actual original-source generic H economic-scenario run, the owner must **separately** authorize:
- Read-only use of the identified existing private RawVault/Warehouse local paths, allowed dataset/symbol/timeframe, bounded UTC start/end/cutoff, experiment ID, and exact approved Scanner plugin/AST SHA; include Windows/local no-export/no-write conditions. Merely publishing a repo policy is **not** data access permission.
- The **six nonfunding cost values** individually (or a separately approved SHA-pinned policy carrying all seven), with Spot funding `"0"`, and a factual provenance/classification for each assumed fee, spread and slippage; the owner must explicitly approve using those assumptions **for this bounded research scenario**. No numbers specified in this document. Approval to run costs ≠ independent proof of historical fee schedules or executable economics.
- Separate intended interpretation: **research scenario under declared assumptions** only; all original-source rights, publisher issuance/PIT, independent economic attestation, ACK signers, sealed holdout and F5 remain unavailable until distinct evidence and authorizations.

### H2 fail-closed readiness states for Integration's ONE preflight

| Missing or invalid condition | Readiness result | Allowed action |
| --- | --- | --- |
| No explicit owner E: private-source permission | `WAIT_SOURCE_PERMISSION` | **STOP before any private file read**, even if a synthetic packet exists |
| Source permission present but no complete separately owner-approved 7-value cost scenario | `WAIT_COST_POLICY` | **No economic run**; return missing *field names only* with no default zero or invented fees |
| Source/manifest/Core245/Core253 query/interval/cutoff or independent provenance not established | `WAIT_PROVENANCE` | Do not claim issuer rights/PIT or start original-data processing |
| Incompatible code/contract SHA, drift, schema mismatch or forbidden ACK/authority/holdout | `BLOCKED_CONTRACT` | Fail closed with sanitized reason, no private data, do not downgrade |
| Every **readiness input**, SHA, owner permission and cost field verifiably present | `READY_FOR_OWNER_AUTHORIZATION` | Readiness review / Audit only; **still no owner-original run until a separate explicit run authorization** |

**Diagnostic fallback:** Existing historical zero-cost outcome is `DIAGNOSTIC_ZERO_COST_NOT_ECONOMICALLY_VALIDATED`. It is a *label for previously authorized diagnostic evidence only*, not a fallback that silently runs original owner data at zero costs. If the prospective H2 cost authorization is absent, Integration returns `WAIT_COST_POLICY` (not synthetic `PASS`, alpha, cost-validated, or a newly executed original-source diagnostic). If the owner later explicitly authorizes a zero-cost diagnostic, it must be clearly reported as DIAGNOSTIC ONLY and may not support net-economics conclusions. If all six costs are zero but policy claims economic realism, STOP/WAIT_COST_POLICY for evidence/clarification; do not silently upgrade zero cost.

### Exact lineage/readiness acceptance (existing code; one later owner-local gate)

At readiness preflight Integration should pin: `aql.scanner.h.causal-signal-batch.v1` + verified strategy/plugin/config/evaluator SHA, complete actual `aql.core.local-history-query.v1` (not the Core H summary), source bytes/manifest/range-query SHA, cutoff and missing/UNKNOWN denominator, separate Factory `factory_code_sha256`, canonical cost policy digest, immutable Factory `experiment_sha256/result_sha256/ledger_sha256/Lab SHA`, then Core Secretary durable WAIT under its own DB. A generic 3rd-manual AST must **not** reuse the frozen F2 24/20+4 cohort, and February/August UNKNOWN must remain untouched in prior F2.

Never copy original private OHLCV, ZIP, RawVault/Warehouse paths, or source contents to GitHub/CI or logs. The eventual owner-local **first/replay** and no-write proofs are planned separately after explicit owner permission. Preflight should disclose only missing field names, SHA metadata, permitted code origins and `WAIT_*` statuses. Keep `trading_authority=NONE`, `historical_pit=NOT_ATTESTED`, holdout `SEALED_UNOPENED`, Source ACK / Strategy Approval / Factory Consumer ACK null and Secretary `WAIT_RESEARCH_REVIEW` only.

## Factory delivery / integration ownership

Factory H2 is a **documentation + verifiable contract handoff only**, not a fresh evaluator or rerun. Canonical existing input/output: [Factory generic H v1 contract](factory-package-h-generic-scanner-v1-20261107.md). Integration #271 owns one H2 preflight manifest, explicit permission/cost/provenance state machine and evidence packet for Audit #256. Core/Scanner give contract confirmations only. **No new Factory production code or repeat of accepted Package H CI required at this time** unless Integration identifies a reproducible mismatch.

**Sign-off (Factory scope): `READY_FOR_H2_READINESS_PREFLIGHT` — NOT `READY_TO_EXECUTE_PRIVATE`, `ECONOMIC_VALIDATED`, `F5`, `G0` or `TRADING`.**
