# SF-DEC-21 B — Reproducible Synthetic Factory Workflow

**Development proof only:** not StrategyDefinition generic evaluation,
research COMPLETE, independently anchored custody, real market/OOS/PAPER,
Core Scanner/trader signals, order/fill, G0 acceptance or trading.

## Existing dependencies reused

`sf_breakout_pilot.PilotPlan(SPEC)` and exact 500 generated 15m bars,
`frozen_pilot_family`, `FrozenAttemptWriter`, `AttemptLedger`,
`run_pilot`, `record_synthetic_result`, `read_synthetic_evidence`.
No existing schemas, fee/cost logic or Core files are modified.

## Operator/test recipe (API, no automatic trusted anchor)

1. Call `pilot_commitments()` to calculate expected pilot-plan, fixture
   and family digests. **Retain those exact commitments independently before**
   any execution, preferably in an owner-controlled custody destination. The
   helper does **not** prove this happened. Feed the three expected digests
   explicitly into `run_workflow(db_path, expected=...)`.
2. Use a new, operator-selected SQLite file path under an existing private
   directory. The workflow freezes the family, appends two BASE/SHADOW PENDING
   attempts, simulates 500 artificial bars, writes only a **synthetic evidence**
   receipt into the existing Factory DB and replays the record.
3. Retain the returned canonical `report_json(report)` bytes and
   `report_digest`, `attempt_checkpoint`, `evidence_checkpoint` outside
   the writer's control. The report labels costs, observed simulated trade
   counts, missing volume, rejected entries, unresolved boundary and
   terminal-open positions; these are not fabricated closed PnL.
4. Reopen with `verify_workflow(db_path, expected=..., expected_report_digest=...,
   expected_attempt_checkpoint=tuple(...), expected_evidence_checkpoint=tuple(...))`.
   This recomputes the frozen artificial pilot and demands exact match to
   externally supplied values. Identical reruns are idempotent.
5. `report_summary(report)` provides readable text. The caller decides how to
   publish/store it; no new global reporting service or trusted external
   custody integration is created.

**Important:** The synthetic Breakout `PilotPlan` is *not* an accepted generic
`StrategyDefinition`/PIT HistoricalLibrary adapter. Reporting code and
its optional same-process hash generation alone cannot authenticate when
an external owner commitment was first made. The Factory attempt states stay
PENDING, not COMPLETE. Core's operational lifecycle and real-time feed remain
entirely separate.
