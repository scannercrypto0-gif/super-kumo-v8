# Factory #238 — Authentic historical research admission, bounded V1

## Ownership and purpose
This Factory-owned additive module builds on Factory Draft #229 (stacked on frozen #222). It is a strict **preflight**, not an authentic historical evaluation engine, source verifier, strategy interpreter, or Work transport. Existing Factory descriptive and modeled-trade evaluators remain unchanged.

API: `research_wp_r0.aql_factory_authentic_research_admission.assess_research_admission(packet)`; input schema `aql.factory.authentic-research-admission.v1`; output `aql.factory.authentic-research-gate.v1`.

### Frozen boundaries
- Core #226/#237 exclusively owns source-original-byte custody, provenance, correction lineage and verified as-of queries. Factory must not trust a caller-supplied SHA or verification flag as evidence of authenticity.
- Discoverer #230/Work #235/#239 exclusively owns independent hypothesis generation, plan/strategy semantics and integrated adapters. Factory verifies the supplied plan/strategy/attempt commitments but **does not** infer actual strategy signals from a candidate definition.
- Factory #229 already validates synthetic Core-style/Discoverer-style compatibility and invokes the existing descriptive evaluator. That fixture is not a scientific evaluation of a newly generated strategy.
- Audit #240 owns the final independent authentic-source integrated gate.
- No PR merge, G0, paper/live trading, private data access or holdout unsealing.

### Contract checks implemented
- Canonical immutable packet SHA256, source bytes SHA shape, source manifest SHA shape, dataset-version commitment, strategy identity/version/digest, plan digest and decision cutoff.
- Full attempt denominator; every attempt has an immutable unique ID, exact strategy/plan/cutoff, state and explicit absence of results or holdout access.
- Fail-closed duplicate lineage (must refer to an earlier claimed attempt), feature availability not after cutoff, and rejection of invented returns, winners or authority.
- Distinguishes TEST_ONLY_CONTRACT_VALIDATED from AUTHENTIC_SOURCE_NOT_CONNECTED; returns INSUFFICIENT_EVIDENCE and NOT_PERFORMED for strategy-rule-trigger evaluation in both cases.
- Deterministic digest and no input mutation; focused adversarial test matrix.

### Explicit blockers, not waived
1. **SOURCE_NOT_AVAILABLE/UNVERIFIED** until Core supplies independently validated original bytes, credible source/capture/correction lineage and PIT as-of availability. This module deliberately cannot certify authenticity.
2. Core's current read-only range metadata does not itself supply complete verified OHLCV price series; Work must join a source-authenticated full price grid before Factory computes scientific outcomes.
3. Candidate definition does not imply a historical signal. Work/Factory need a separately validated versioned rule interpreter and the existing Factory modeled-execution engine joined to actual eligible bars, without inventing a new backtester.
4. Trial-family search budget, candidate-level multiple testing, full market opportunity denominator and correction chains require actual upstream receipts; synthetic fixtures cannot certify them.
5. Development windows only, BASE/SHADOW costs and ambiguous outcomes separately labeled; no OOS, significance, alpha or paper approval inferred.

### Reproduction
```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p 'test_aql_factory_authentic_research_admission.py' -v
```
The isolated module has no third-party runtime dependency. This test alone is **not** the final Core→Discoverer→Factory integrated gate. Work must pin the exact Core/Factory/Discoverer SHAs, validate independent source proof, then run a single consolidated cross-owner test and send the exact evidence to Audit.

### Status
`IMPLEMENTED_ADMISSION_PREFLIGHT` / `AUTHENTIC_SOURCE_NOT_CONNECTED` / `STRATEGY_RULE_TRIGGER_EVALUATION_NOT_PERFORMED` / `SCIENTIFIC_RESULT_INSUFFICIENT_EVIDENCE`. No claim of full Issue #238 completion until source-backed integration and independent review.
