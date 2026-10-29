# Factory consolidated boundary audit — 2026-10-28

Execution authority: owner directly supplied [#77/6464942337](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/77#issuecomment-6464942337).
Base: Draft #143 `a0b463dfae6f652a37b892f80c1215ec8614a704`, stacked on
#141 `fbf70afbcf3ba051a9b1522328893bf9ab7f2a67`, #140→#139→#138.
Main `dbc191df72f4b4d1ebb7d490926dcad4325dac12` is a different, older source surface.
No source PR merged. This is direct scoped execution, not an asserted unified
cross-chat Work handoff or independent Council verdict.

## Inventory method and actual coverage

`tools/factory_boundary_inventory.py` enumerated every tracked non-test Python
file in the pinned #143 tree using `git ls-tree`, loaded each blob, parsed its
AST, and retained all function/class declarations, imports and call locations:
**84 files, 6,199 calls, 19 dynamic attribute sites**. The complete machine-readable
baseline is `evidence/factory-consolidated-20261028/source-inventory.json`, including
SHA256 of each source file and excluded test paths. The targeted suite reproduces
it from the pinned parent tree. This is a complete *file/AST census at that tree*,
not a claim that AST determines all runtime receiver types or outside callers.

Manual disposition below follows imported aliases, instance construction,
callback parameters and concrete implementations. The 19 dynamic sites use
`getattr` for filesystem flags, result metadata or pipeline optional fields;
none implements a Factory scoring plugin loader. No `eval`, `exec`, dynamic
import or runtime plugin registration was found in the inventoried tree.
External callers of exported Python APIs, unprovided branches, external sinks
and unseen chats remain outside this bounded proof. Tests/mocks are separately
excluded, not mistaken for production sinks.

The stack adds/changes 11 Factory modules relative to main: core_proof_bridge,
data_admission_b, factory_b2_counterfactual, factory_full_synthetic_b,
guarded_factory_exam, indicator_calculation_identity, indicator_library,
indicator_library_v2, pre_indicator_boundary, strategy_definition and
synthetic_outcome_receipt. They are all present in the audited #143 tree;
this is not a default-branch code-search inference.

## Actual call paths and claim boundaries

Paths below are relative to `research_wp_r0/` unless stated otherwise. Line
numbers refer to the pinned pre-change #143 census; current comparison guard is
located by `_comparison_input`/`compare_routes` after the additive repair.

| Source boundary | Actual consumers / output | Authority and disposition |
|---|---|---|
| `strategy_definition.py:366` AttemptRecorder, `:394` finish | `attempt_ledger.py:318` constructs recorder with AttemptLedger; `historical_evaluation_bridge.py:145` accepts caller recorder, `:161` finishes FAILED | Port accepts COMPLETE with binding/digest, but no production caller finishes COMPLETE. External sink behavior is not certified. |
| `attempt_ledger.py:238` record_attempt | concrete durable sink; `:318–319` prepare_durable_candidate, FrozenAttemptWriter `:57` | Sealed membership and state transitions; COMPLETE rejected at `:120`. INPUTS remains PENDING work, not evaluation. |
| `frozen_attempt_writer.py:28` record_attempt | workflow `sf_synthetic_workflow.py:182`; batch adapter `:44` | Only PENDING/INPUTS/FAILED/ABANDONED/INVALID; no accepted evaluator. |
| `frozen_research_plan.py:18,56` commit/verify | sealed ledger bind/read, writer, batch admission, reconciliation, synthetic result link, `tools/offline_custody_kit.py:130` | V1 opaque nonempty rule/cost commitments; identity/replay only, **NOT_CERTIFIED_FOR_RANKING**. Preserve bytes. |
| `frozen_plan_reconciliation.py:21,65` | writer diagnostics, full-plan inventory; tests | Missing/pending inventory with NOT_EVALUATED. Not candidate winner selection; omitted states remain in retained ledger, never implied eligible. |
| `batch01_admission_bridge.py:10`, attempt adapter `:11`, quarantine `:10` | synthetic inputs→PENDING; results QUARANTINED_NOT_EVALUATED | No COMPLETE/result promotion. Reuse existing tests. |
| `strategy_dna_v2.py:59,86,125` profiles; `:299` channel; `:358` evaluate_synthetic | scanner ranks supplied synthetic assets `:390–406`; decisions `:425–440`; `factory_exam.py:67`; example CLI `strategy_dna_v2_example.py:47` | Versioned typed references/direction/ties/missing status and positive weighted scores already validated. Synthetic cross-sectional asset ranking, **not ranking candidate research outcomes**; no research-plan selector. |
| `factory_exam.py:118` freeze_protocol; `:145` run_route; `:280` replay_route | one cash-only route under versioned bps costs, timeline ledger, sampled marks | Existing execution and replay are reused. No fill authority or full pathwise DD. |
| `factory_exam.py:289` compare_routes | `factory_exam_example.py:52–55`; `factory_full_synthetic_b.py:60,65`; `factory_b2_counterfactual.py:106`; `synthetic_outcome_receipt.py:15` | Actual public aggregation boundary. Confirmed UNKNOWN-zero-fill and negative-cost direct-input bypass repaired here. Remains descriptive synthetic, not a winner selector. |
| `factory_exam_example.py:30,62` run_fixture/CLI | four preregistered comparisons and R2 NOT_IMPLEMENTED | Matched/sensitivity labels and trial register retained; print JSON only. |
| `factory_full_synthetic_b.py:49,80` | deterministic run+replay→comparison→JSON | Supplied 18-slot universe, synthetic provenance, no market PIT/OOS. |
| `factory_b2_counterfactual.py:96,122,133,135` | nine authored cases and gate permutation sensitivity; CLI JSON | 162 scheduled authored slots; no trained strategy ranking, no inference/promotion. |
| `synthetic_outcome_receipt.py:8` | public supplied-slot wrapper→manifest/protocol/routes/comparison | Synthetic scheduled denominator retained; now shares repaired comparison guard. |
| `synthetic_execution.py:9,32` | shared accounting; `synthetic_opportunities.py:10`; simulator/pilot/EMA/exam | Validates finite nonnegative bps; ambiguous/gap outcomes remain unresolved. No external fill/receipt authority. |
| `synthetic_summary.py:5` | public ledger→counts, resolved-only mean; **no in-tree non-test caller** | Named resolved-only estimand, unresolved denied scored return, profitability_claim=false. Not a strategy ranker; no fabricated caller invented. |
| `sf_breakout_pilot.py:190` run_pilot | synthetic result link `:154`; workflow `:156,188` | Fixed PilotPlan, BASE/SHADOW and BASE/STRESS; open/pending and unresolved boundaries retained. |
| `sf_synthetic_result_link.py:132,216` | recorded evidence→workflow verify/report | Recomputes pilot, requires exact NO_SELECTION_SYNTHETIC_ONLY and COSTS, sealed two-PENDING receipts. No COMPLETE. |
| `sf_synthetic_workflow.py:64,112,165,205,245` | synthetic report→report_json/report_summary | Checks fixed source/status/version/cost/selection NONE/promotion NONE/custody NOT_VERIFIED; verify_workflow additionally reopens/recomputes actual retained evidence. A digest alone is not this verification. |
| `ema_first_backtest.py:74`; `pinned_ema_research.py:14`; `ema_development_replay.py:14` | `scripts/sf_ema_development.py:15–18` archive→pinned development→create-only JSON | Retrospective development, OOS locked, engineering sample/no inference; close-mark DD only. **Not executed by this task**. |
| `research_guards.py:161` | public guarded retrospective replay→paired BASE/STRESS report | Complete opportunity parity; verified timestamp path NOT_IMPLEMENTED. Not a selector. Not executed here. |
| `offline_simulator.py:19`, `offline_evaluation_result.py:20` | single-long result value; input audit | Versioned hypothetical result, UNKNOWN/unexecuted PnL null, custody NOT_VERIFIED, no ledger COMPLETE. |
| `sf_historical_admission.py:64,167,220`; `pre_indicator_boundary.py:10`; `core_proof_bridge.py:14`; `data_admission_b.py:27` | input admission receipts and human report | DEV/source assertions separate; empirical eligibility never inferred from local hashes; Core clock/corrections remain separately gated. |
| `factory_custody_envelope.py:13,35`; export `:13,44` | public portable envelope→create-only file→verification | Digest/checkpoint equality and fsync, not independent off-writer custody. No caller in the production tree promotes this to VERIFIED. |
| `custody_manifest_builder.py:21`; `custody_anchor_verifier.py:20`; `tools/offline_custody_kit.py:112,140,234` | local inventory/restore/receipt replay→JSON | Original source state counts and NOT_EVALUATED retained. Caller-owned anchor is not independently authenticated authority. |

Remaining Factory modules (`content_identity`, `future_bar_evidence`,
`guarded_factory_exam`, `historical_evaluation_bridge`, `historical_library`,
`indicator_calculation_identity`, `indicator_library`, `indicator_library_v2`,
`offline_input_audit`, `retrospective_kline_intake`, `_dep_guard`, `__init__`)
provide inputs, manifests, typed computations or isolation checks. They do not
publish candidate outcome rankings. Their exported definitions/import edges are
retained in the machine census; historical import/file fixture helpers are not
misclassified as a strategy publisher. Core `src/aql` and public smoke/archive
scripts were also parsed; no additional Factory AttemptRecorder sink or research
selector was found there.

## Proven falsifier and repair

Before modification, the existing fixture with first `fill_fraction=None` yielded
eight UNKNOWN slots and universe mean `None`. Rebuilding that same FrozenExam
with UNKNOWN net/gross/per-notional values set to zero made `compare_routes`
publish a universe mean **0**, while retaining UNKNOWN statuses. Independently,
rebuilding both route assumptions with negative fee/slippage was accepted.
This was an actual call boundary, not a demonstrated empirical/production exploit.

The new `_comparison_input` is a structural validator at that exact port:
requires route-v1/synthetic scope and exact fields; reuses the existing protocol
config validator; rejects nonfinite/negative/wrong-unit costs, UNKNOWN scored
returns, nonexecuted conditional returns, duplicate slots, candidate lifecycle
states masquerading as opportunity outcomes, inconsistent unknown/drawdown/halt
claims, and added promotion/custody/conditional-relabel fields. Existing valid
route/protocol/comparison bytes and labels remain unchanged. It does not replay
accounting or authenticate a self-rehashed coherent forgery; `replay_route` plus
retained source commitments remain required for that stronger claim.

Counts are separate contracts: candidate planned/attempted/PENDING/FAILED/INVALID/
ABANDONED/COMPLETE are sealed ledger/reconciliation concerns; scheduled/known/
unknown/executed/no-fill/zero-exposure are opportunity concerns. They are not
substituted for each other. No COMPLETE or eligible-trial count is invented.
A full candidate-outcome ranking/promotion publisher is **NOT_IMPLEMENTED** in
this tree. Therefore no speculative research-plan-2 engine or generic selection
schema was added. At the existing synthetic boundary, foreign/opaque plans and
unknown contract fields are refused; existing V2 scanner semantics are reused.
A future scientific selector must separately implement metric references,
direction, deterministic ties, missing treatment, finite nonnegative cost units,
full trial-family denominator/eligibility and independent acceptance.

## Immutable legacy and validation batch

`frozen_research_plan.py` remains blob `9403d2e141ddf9dab81851ce13ae828033013518`,
SHA256 `ec45c9ad2f18a290bcb238474771e55c1a012416056ae7441a56be2fe4e4f8fe`.
The canonical existing V1 fixture is retained byte-for-byte, plan digest
`b64a151b59318bbb936e03a11385920fe301892e94714bad582fc6f05df26cc4`.
Golden files are marked `-text` for Windows checkout. Tests verify legacy replay,
not that opaque V1 rules acquire scientific meaning.

One new targeted suite `tests/test_sf_boundary_onepass.py` covers the changed
consumer guard and compatibility. Existing test_sf_factory_exam, full synthetic
B2, outcome receipt and computed-vector tests exercise its real downstream
callers. Existing V2 rule/reference/tie tests, sealed ledger state/missing-trial
and workflow false-promotion/custody tests are reused, not reimplemented as a new
engine. Historical #143 `1240d882` CI 40649718661 (708 passed, 3 skips, 51 subtests
in representative log) and integrity 40649718703 remain historical evidence.

No repeated green CI was requested. The single changed-head matrix uses the
existing acceptance workflow, whose broad regression is justified by changing a
public comparison and shared protocol validator consumed across the five listed
report paths. New falsifiers run once per OS/Python in that same suite, not in
a second targeted workflow. Existing configured integrity CI is retained;
results/run IDs are submitted in #77/#134 and PR #143 after execution. Green
regression does not independently accept scientific claims.

## Continuity and closure

The supplied linked order is the latest directly received execution instruction
for this task. Prior register PR #14 and Factory manager attachment/addenda are
not asserted to be an exhaustively reconciled last global Work handoff. No
unified cross-chat Work order is issued. Inaccessible addenda remain UNVERIFIED;
this gap does not invent approval to merge or broaden the scoped task.

Council S and R must separately accept/reject exact changed SHA and evidenced
bounds. No CLOSED_FINAL, main write, merge, OOS, PAPER, LIVE, G0, actual returns,
issuer-time or off-host custody acceptance is asserted by this implementation.

Local targeted command (70 passed, no skips, 5.84 seconds):

```
python -m pytest -q tests/test_sf_boundary_onepass.py tests/test_sf_factory_exam.py tests/test_sf_factory_full_synthetic_b.py tests/test_sf_b2_counterfactual.py tests/test_sf_b2_gate_permutation.py tests/test_sf_synthetic_outcome_receipt.py --junitxml=/tmp/factory-consolidated-targeted.xml
```

The final CI matrix expands coverage only through the existing configured
shared-dependency suite. No historical/OOS data execution is part of this test
batch; synthetic fixtures and legacy commitment replay only.
