# Package H — Generic Scanner signals → Factory next-open model → immutable Lab (v1)

**Owner/PM authority:** [#205/6707864112](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-6707864112), [Factory #267/6707867351](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/267#issuecomment-6707867351). Research-only provisional B. Do not issue G0, signed F5, StrategyApproval, Source ACK, Factory Consumer ACK, holdout/Paper/trading, an owner-private E: reread, or a merge.

**Important distinction:** Existing immutable original Recovery F2 `aql.factory.f.f2-recovery-research-input.v2` and `run_factory_h_research(...)` continue to enforce **two frozen Work235 identities, 24 attempts = 20 evaluated + four Feb/Aug UNKNOWN, 10 source-backed months/29,376 original bars**. Those validations remain unmodified. Generic Package H is **not** a reinterpretation of F2, and does not assert a 24-row cohort, original F2 SHA, or invented February/August bars.

## API — existing Factory kernels, not a second signal engine

```python
from research_wp_r0.aql_factory_e_research_results_store_v1 import migrate_store_v2
from research_wp_r0.aql_factory_h_generic_signal_adapter_v1 import run_factory_h_generic_research

# Integration supplies one actual Scanner H batch and a matching full,
# SHA-sealed Core #253 bounded source query already checked by Scanner.
# Store path is a NEW isolated disposable research SQLite; never original RAW.
migrate_store_v2(isolated_research_sqlite)
first=run_factory_h_generic_research(sealed_packet,isolated_research_sqlite)
replay=run_factory_h_generic_research(sealed_packet,isolated_research_sqlite)
assert first["store_status"]=="STORED_IMMUTABLE"
assert replay["store_status"]=="REPLAY_IDENTICAL"
```

Input: **`aql.factory.h.generic-signal-input.v1`** with exact required keys:

`schema,sha256,experiment_id,scanner_signal_batch,strategy_plugin,scanner_signal_policy,core_query,operator_cost_policy,factory_code_sha256,source_query_sha256,source_bytes_sha256,manifest_integrity_sha256,strategy_definition_sha256,strategy_plugin_sha256,config_sha256,scanner_policy_sha256,scanner_evaluator_code_sha256,decision_cutoff_ms,holdout,historical_pit,trading_authority,source_ack_sha256,strategy_approval_sha256,factory_consumer_ack_sha256`.

`experiment_id` starts `RESEARCH-H-GENERIC-`; `sha256` is the canonical digest over all other fields, with no extra keys. All source, query, config, strategy, plugin, code and policy hashes are **distinct** and must match the original verified ancestors. `core_query` MUST be the full sealed `aql.core.local-history-query.v1` #253 ranged receipt, **not** the bounded `aql.core.h.portable-research-query.v1` summary; its range `query_sha256` is not silently the whole-month #245/#253 warehouse parent SHA. The actual source bytes/manifest/query identity, dataset ID, range, cutoff, bar numbers and availability must match Scanner H batch. `historical_known_at_ms=null`, `historical_pit=NOT_ATTESTED`, `holdout=SEALED_UNOPENED`, all three independent ACKs null, `trading_authority=NONE`. The test-only manual strategy requires no signed Discoverer F4.

Factory calls **the actual Scanner H `verify_factory_signal_batch(batch)`** and Scanner's canonical Core query and policy validators under a pinned overlay. `StrategyDefinition` is reconstructed to match the registered plugin digest, version, config, evaluator code and Work235 frozen identity (or manual parameter/risk/timing digest). Factory **does not rerun `_vectors`/`_expression` or recompute/override Scanner's signal decisions.** It uses the verified `ENTRY_SIGNAL/EXIT_SIGNAL/NO_SIGNAL/UNKNOWN` stream; next-eligible open is a signal-time pointer, **not a market fill**. Existing `_modeled_trade` Decimal cost/price formula and current StrategyDefinition risk fractions/holding cap generate research-only modeled outcomes. All stop/target intrabar touches, unobserved exits and no available next-open become UNKNOWN, never optimistic fills or zero-return losses. A source PARTIAL/UNKNOWN batch is fully quarantined and makes **zero** modeled fills. Expected/observed/missing counts and NO_SIGNAL/UNKNOWN are explicit.

### Explicit cost policy

`operator_cost_policy` is a distinct canonical SHA-sealed `aql.factory.h.generic-cost-policy.v1` with exact keys `schema,sha256,costs,market,direction,scenario_class,owner_operator_authorized,fill_semantics,holdout,trading_authority`. `costs` has **all seven** original Factory `COST_KEYS`, each an explicit bounded Decimal **string**: entry/exit fee, spread, slippage and `funding_bps_per_bar=0` (Spot). Market SPOT, direction LONG, `fill_semantics=NEXT_ELIGIBLE_OPEN_UNKNOWN_ON_INTRABAR_TOUCH`, holdout SEALED, authority NONE. No implicit default costs.

`scenario_class=SYNTHETIC_TEST_EXPLICIT` requires `owner_operator_authorized=false` and is suitable for isolated synthetic engineering only. `OWNER_DECLARED_RESEARCH_SCENARIO` requires an explicit `owner_operator_authorized=true` **declaration**, but this flag alone is never trusted as independent economic attestation. When all costs are zero, resulting `economic_class=DIAGNOSTIC_ZERO_COST_NOT_ECONOMICALLY_VALIDATED`; otherwise `EXPLICIT_DECLARED_COST_SCENARIO_NOT_INDEPENDENTLY_ATTESTED`. No profitability, risk-adjusted return, practical execution or alpha claim from either class.

### Output — immutable compatible H table + existing scientific Lab

`run_factory_h_generic_research` returns SHA-sealed `aql.factory.h.generic-research-result.v1` with `experiment_id,input_sha256,package_sha256,factory_report_sha256,trade_ledger_sha256,scientific_lab_sha256,secretary_receipt_sha256,experiment_sha256,result_sha256,scanner_batch_sha256,cost_policy_sha256,economic_class,store_status,f5,trading_authority,paper,holdout,receipt_sha256`. The parent `aql.factory.h.generic-immutable-package.v1` stored in existing `factory_h_research_results_v1` SQLite layout-v2 table contains:

- `factory_report` (`aql.factory.h.generic-execution-report.v1`) with source/query/strategy/config/code/cost/cutoff and `experiment_sha256,result_sha256,ledger_sha256,lab_sha256`.
- `trade_event_ledger` (`aql.factory.h.generic-trade-event-ledger.v1`) with exact original Scanner signal event hashes, per-bar execution state, modeled and explicit UNKNOWN outcomes, expected/observed/missing/signal counts and next-open timing. No false 24-row denominator.
- `scientific_lab`, produced by **the same existing** `evaluate_immutable_ledger` research-only Lab function, with generic cohort validation, gross/net modeled returns and cost sensitivity, insufficient-sample/UNKNOWN nullability. The old F2 cohort and its uncertainty fields remain unchanged.
- `secretary_research_receipt` (`aql.factory.h.generic-secretary-review-receipt.v1`), SHA-sealed research review pointer with source/query/strategy/plugin/config/policy/code/cutoff/experiment/result/ledger/Lab SHAs, all ACKs null and no trading authority. **This is not an ACK and cannot impersonate Core H's F2-specific report.**

The same isolated v2 `_store_package` implementation performs first immutable store and exact replay/conflict checks. `package_sha256,experiment_sha256,result_sha256,trade_ledger_sha256,scientific_lab_sha256,secretary_receipt_sha256` are **stable** across first/replay. Outer `receipt_sha256` changes because it includes `store_status`; rehash each outer receipt separately. Windows SQLite connections close explicitly, and native file unlink/tamper tests must pass.

## Integration #271 and Core #275 mapping

Existing **F2** `tools/atlas_h_research_secretary_bridge.py` stays intact: it expects genuine Factory F2 v2 report. **Generic H** has a separate `factory_report` and Secretary research **review** pointer; Integration must adapt that explicit envelope to Core's durable `WAIT_RESEARCH_REVIEW` without pretending it is an F2 Factory report, issuing Source ACK/Strategy Approval/Factory ACK or promoting Paper/F5. Core's non-ACK Secretary remains the authority; Factory only supplies sealed results. Integration performs the **one** SHA-verified pinned overlay Linux/Windows/adversarial gate for both frozen Work235 definitions and genuinely distinct manual AST; then Audit #256 reviews one complete packet. No owner E: rerun.

Cross-owner compatibility test staging pins Scanner #277 `3c82448702c9ae35783716e4e2c3b640010db97c`, Core #275 `59510d302e7bb97a63e3d9603b9fb9f81f8f378a`, Scanner B native policy draft #257 `30c37ae56851488b882998c7fa0085ec51dbfc92`, and the actual frozen Work235 `6acbcc7fc243b132f58170df4c6469bbf7f4eff8` original fixture blob `c27eb5aa70a6d671791ba1e55e9b078a272b611f`. On a disposable runner **only absent files** are staged; tracked Factory files are never overwritten and PRs are never merged. Re-pin the actual heads in Integration before its combined gate.

Focused new-delta command (requires exact staged external code):
```bash
PYTHONPATH=. python -m unittest discover -s tests -p 'test_aql_factory_h_generic_signal_adapter_v1.py' -v
```

Tests: two Work235 TEST_ONLY definitions + a genuinely distinct manual AST; synthetic complete/partial quarantine; causality/no future bars; source/policy/plugin SHA cross-owner match; frozen identity; missing/negative fees; altered event/cutoff, duplicate, forged ACK, immutable replay and native Windows tamper/delete; unchanged original F2 H lane. Engineering PASS never means owner-original E: economic/PIT/F5 approval.
