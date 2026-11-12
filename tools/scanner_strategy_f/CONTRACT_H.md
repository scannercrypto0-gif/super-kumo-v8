# Package H — Scanner strategy plug-in → Factory causal signal contract (draft v1)

Owner master: [#205/6707637665](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-6707637665). Scanner task [#277/6707643128](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/277#issuecomment-6707643128). **Provisional B**, existing OPEN/DRAFT Scanner #277; Integration #271 is the canonical cross-owner schema lead. This is the Scanner-owned input/output adapter for Integration to reconcile, **not** a second historical evaluator, data store, execution model, or independent policy authority.

## Reused existing code

- `research_wp_r0.strategy_definition.StrategyDefinition` validates declarative AST and immutable definition digest.
- `research_wp_r0.indicator_library_v2.IndicatorRegistryV2`, existing Factory `_vectors/_expression` through `scanner_strategy_f.research_e2e_diagnostic._eval_strategy`: no new technical indicator or competing strategy evaluator.
- Core #253 `query_local(...,sqlite_immutable=True,require_complete=False)` reopens the **same portable, local-first Warehouse**, then compares the complete exact local-query receipt. No re-ingest or new table.
- `tools.strategy_service_offline.common.Frozen` and Core `digest` create deterministic, content-addressed receipts.
- Frozen Work235 two TEST_ONLY ASTs remain pinned to original source spec/config/definition hashes; *not* issuer provenance or owner policy approval.

## Python interface

```python
from tools.scanner_strategy_f import research_strategy_plugin as scanner_h

# Already-loaded frozen Work235 fixture: no changed Work235 files.
plugin = scanner_h.register_strategy_plugin(
    work235_spec["payload"]["definition"],
    config_digest=work235_spec["payload"]["config_digest"],
    source_spec_receipt=work235_spec,
)

# For an entirely new compatible/manual test-only declarative strategy:
# definition.to_dict() is StrategyDefinition's native immutable AST envelope.
manual = scanner_h.register_strategy_plugin(
    definition.to_dict(),
    config_digest=scanner_h.manual_config_digest(definition.to_dict()),
    origin="MANUAL",
)

# Optional Discoverer candidate identity is a reference input only:
# origin="DISCOVERER_CANDIDATE", candidate_sha256="<pinned 64-hex>"
# No signed F4 or independent strategy approval is required for MANUAL.

policy = scanner_h.research_signal_policy(source_class="TEST_ONLY")
batch = scanner_h.evaluate_strategy_plugin(
    plugin, actual_core253_local_query_receipt,
    warehouse_root=warehouse_root, policy=policy,
)
verified = scanner_h.verify_factory_signal_batch(batch)
factory_consumer_input = verified.receipt()
```

For **original source diagnostic**, Integration supplies the already-verifiable Core #253 local query and `source_class="OWNER_LOCAL_RECOVERY_DIAGNOSTIC"`; this class says *research diagnostic only*, not authenticated historical PIT, publisher issuance, or F5 rights. The owner previously approved the original-data diagnostic and already delivered its PASS; **do not rerun it just to prove this new interface**.

## Stable versioned envelopes

**Plugin**: `aql.scanner.h.strategy-plugin.v1` sealed `{payload,sha256}` with strategy ID/version, full native StrategyDefinition receipt and digest, config digest and pinned config identity class, indicator parameters, evaluator code SHA, optional frozen Work235 spec SHA, optional candidate SHA and origin. Research-only trust flags always DENY Source/Strategy/Factory ACK, PIT and trading. Manual config SHA is recomputed from the native AST's indicator parameters, risk and timing; Work235 source/config/definition SHA are pinned against the frozen known original.

**Policy**: `aql.scanner.h.research-signal-policy.v1`, unsigned, `RETROSPECTIVE_NON_PIT`, `holdout=SEALED`, `economic_attestation=NOT_ATTESTED`, no ACK/approval/trading. Authenticated owner-approved economic cost/fill policy belongs **separately** to Factory H and cannot be inferred from this research signal policy.

**Batch**: `aql.scanner.h.causal-signal-batch.v1`, sealed, binds plugin/definition/config/evaluator/source-query/source-byte/manifest/policy SHAs, dataset ID, start/end/cutoff, exact expected/observed/missing counts, per-state `signal_counts` (ENTRY_SIGNAL / EXIT_SIGNAL / NO_SIGNAL / UNKNOWN), events, source completeness/quarantine, explicit `economic_attestation=NOT_ATTESTED`, no profit/fill/selection/operational authority.

**Event**: `aql.scanner.h.closed-bar-signal-event.v1`, each with sequence and strict grid, bar open/close, `research_asof_ms=bar_close_ms+1` (a *hypothetical* closed-bar boundary, **NOT** actual historical availability), `historical_known_at_ms=null`, `historical_pit=NOT_ATTESTED`, state, source observation flag, plugin/query/evaluator SHA, decision cutoff, `next_eligible_open_ms` for action signals, `next_open_is_fill=false`, `cost_or_pnl_computed=false`, exact canonical event SHA. No position, trade, fill, slippage or PnL field.

## Causality and unknowns

- Actual source rows must form a complete, strictly monotonic 900000 ms UTC grid, have canonical 64-hex bar SHA, valid finite OHLCV, exact query hash, `bar_close_ms < cutoff`, `end_exclusive_ms <= cutoff`, and `historical_known_at_ms is None` (no fake PIT).
- Always **re-read** Core #253 with `sqlite_immutable=True`, compare exact full receipt. The Scanner batch is not independent issuer authentication.
- If coverage is PARTIAL or UNKNOWN, the whole bounded requested range is quarantined to `UNKNOWN`. Do **not** calculate indicator states over a gap or misclassify missing candles as NO_SIGNAL. Denominator conserves `expected = observed + missing`; state counts sum to expected.
- A complete range emits exactly one deterministic event per bar; indicator warmup gives UNKNOWN; explicit NO_SIGNAL remains visible; every event SHA, exact fields, identity and grid are independently checked by `verify_factory_signal_batch`. A later bar may not change an earlier bar's signal (causal regression).
- Event output is research-only; a next-eligible open is **not a fill**. Factory owns fees, spread, slippage, ambiguity, trade ledger, immutable result replay and Lab; Core owns Warehouse and Secretary; Integration owns one canonical experiment/results interface and exact-head cross-owner gate.

## Security / acceptance

Synthetic engineering tests use both unchanged Work235 placeholder ASTs **and one distinct new manual test-only declarative strategy**; cover real Factory indicator kernel, prefix causality, content/hash and parameter drift, incomplete query/UNKNOWN, forged approval, future bars, duplicate event/tamper, immutable Core replay mismatch, candidate present/absent. Tests do not use owner E: original rows, raw recovery SHA, original F2 reconstruction or holdout.

**Handoff expected by Integration:** exact Scanner SHA, 3-Python CI results, these four schemas and field mapping to the chosen canonical `research-experiment → immutable Factory result → Lab → Secretary` parent contract. If Integration has chosen different canonical names, add an adapter in Integration rather than create a competing engine or silently rename payload fields. PR remains draft/unmerged; no G0, F5, approved strategy, paper or trading.
