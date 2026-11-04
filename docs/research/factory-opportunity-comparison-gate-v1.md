# Factory #250 — full opportunity census and BASE/SHADOW plan

This additive **research-only, TEST_ONLY** gate extends Draft Factory #241 without modifying the #246 rule engine or Work #247 original calculation. API:

```python
from research_wp_r0.aql_factory_opportunity_comparison_gate import assess_opportunity_comparison
report = assess_opportunity_comparison(frozen_plan)
```

Input schema: `aql.factory.opportunity-comparison-plan.v1`; output schema: `aql.factory.opportunity-comparison-report.v1`. Input binds original archive/member/CHECKSUM/Core price-query SHA256, the immutable candidate generation SHA, and the *precalculation* Work plan SHA. Both are **development-era freezes, NOT historical preregistration**. Exactly 53 frozen attempts across the observed families, with no result-based retuning; multiple-testing correction status must remain NOT_ESTIMATED. Holdout SEALED_UNOPENED, development-only comparison, >=3 day embargo, no authority to trade.

**Population contract:** `universe_inventory=null` when Core #249 has not delivered an independent complete opportunity universe. The report then returns null universe/arm denominators; never zero. If supplied, the inventory must explicitly state `EXPLICIT_SINGLE_SYMBOL_DEVELOPMENT`, `SUPPLIED_NOT_INDEPENDENTLY_ATTESTED`, a source-manifest hash, and one row per opportunity with unique ID, bar time, reason, status ELIGIBLE/INELIGIBLE/UNSCANNED/REJECTED/UNKNOWN/MISSING, plus two BASE/SHADOW arm states restricted to UNKNOWN/NOT_EVALUATED. Conservation and 2 arms per supplied opportunity are checked. This **does not** establish full-market membership, independent opportunity count or outcome comparability. A candidate's per-bar decision slots and the 106 Work reports are not independent opportunities.

**Cost sensitivity:** supply explicit entry/exit fee, spread, slippage and funding bps as finite decimal strings; the BASE_ASSUMPTION scenario must equal the sum and HIGHER_COST must exceed it. These are assumptions only. No cost-adjusted returns are recomputed from private data; no fictitious execution fill, PnL, confidence interval, efficacy or statistical significance. If future research seeks valid BASE/SHADOW comparison, a genuinely predeclared plan, paired source-eligible opportunity observations, known-at chronology and independent controls must be established **before** a fresh prospective/OOS experiment. This code deliberately does not retrospectively relabel the 53 TEST_ONLY candidates.

**Output hard limits:** `base_shadow_comparison=null`, `independent_market_opportunity_denominator=null`, `historical_pit=NOT_ATTESTED`, `scientific_result=INSUFFICIENT_EVIDENCE`, `trading_authority=NONE`. Source byte integrity and independent Audit #248 arithmetic verification are valid in their narrow scope, not historical as-of or efficacy.

**Owner boundaries:** Core #249 owns independent issuance/availability/correction chronology and market/universe manifests. Work owns consuming this additive report alongside the existing original-data results in one consolidated integration, without re-running old 106-report arithmetic. Audit independently reviews only the delta. No merge/G0/holdout/Paper/Live.
