# Scanner P0 fixture readiness

The scheduler runs a frozen finite 15-minute plan. One local poll handles at most the configured catch-up count, with a complete symbol × strategy census for each committed slot. The caller supplies a UTC clock and a read-only Core253 warehouse. The fixture rights pin binds the exact source bytes and manifest version. The native Scanner H evaluator and Factory signal-batch verifier remain responsible for the causal signal batch. Scanner does not provide a data gateway for Factory or Discoverer.

The slot key binds the plan, symbol, strategy pin and scheduled time. A missing or incomplete source window emits UNKNOWN. A late read uses the original cutoff and can produce research evidence only. There is no trustworthy real first-known-at in this fixture, so it stays null. Once committed, an UNKNOWN slot stays UNKNOWN. Native source and evaluator policy continue to govern no-fill semantics.

Each requested Lab indicator resolves through IndicatorRegistryV2, using the same native vector implementation as Factory. Lab receipts bind the request, strategy version, input query, indicator version, shared library hash, cutoff and warmup. Monitor errors produce UNKNOWN monitor evidence. The independent Lab byte allowance and returned backpressure count preserve the decision path.

## Integration contract

The Scanner transaction commits the decision, native batch and outbox together. The producer sends sealed `aql.scanner.p0.handoff.v1` with a canonical digest as effect key. It sends eligible on-time `aql.scanner.p0.decision.v1` to SECRETARY and `aql.scanner.p0.lab-monitor.v1` to LAB. A consumer must validate the route, scope, envelope digest, body digest and authority, then persist the effect and key atomically. Replaying an identical key and body returns the same receipt. Conflicting bytes fail closed. The fixture sends `aql.scanner.p0.fixture-consumer-ack.v1` after commit. Retries reuse the key, wait exponentially and quarantine malformed responses or exhausted attempts.

An outstanding Secretary envelope expires once the dispatch clock exceeds the slot cutoff plus the frozen lag allowance. The decision stays immutable. A downstream receiver must also validate its delivery deadline before using any signal.

The current F3 Secretary proposal accepts the historical source-policy graph, and rejects the new per-slot body with `F3_SOURCE_AND_POLICY_GRAPH_NOT_READY_FOR_PROPOSAL`. Factory Lab's evaluation path takes a Factory ledger. Lab's owner needs to register an independent monitor receiver for the new route. Integration #271 and the respective Secretary and Lab owners need to agree on authenticated receipt binding and demonstrate durable effects in their actual receivers before deployment. The fixture receipt has authority NONE and cannot stand in for that evidence.

## Reproduction

Use Python 3.13 with pytest 9.0.2. Run from the Scanner #277 checkout:

```text
python -B tools/scanner_strategy_f/p0_stage.py p0-ci --fetch
```

Enter `p0-ci` and set `PYTHONPATH` to `src;.` on Windows or `src:.` on Ubuntu:

```text
python -B -m pytest tools/scanner_strategy_f/test_p0_slice.py tools/scanner_strategy_f/test_research_strategy_plugin.py --basetemp fixture-tests -q
python -B -m tools.scanner_strategy_f.p0_evidence ../p0-evidence
```

The dependency overlay is copied from pinned Git objects and leaves the checkout unchanged. Each replay creates a fresh native Core warehouse, Scanner ledger and fixture consumer database. Metrics record CPU and wall time, peak process RSS (peak working set on Windows), and peak traced Python allocations. The canonical digest excludes machine-specific metrics. Storage budgets limit canonical payload bytes independently for the decision and monitor lanes. Physical disk size requires separate operational measurement.

This runtime has zero provider requests. It uses historical fixture rights and has no production egress authority. Real rights, point-in-time custody and shared IP fencing need owner approval and evidence from Core, the #305 pilot and Integration. The current tests establish a bounded offline poll and crash recovery. They leave sustained operation, real PIT/OOS, G0 and execution authority unverified.
