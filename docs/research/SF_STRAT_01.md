# SF-STRAT-01 Strategy Definition JSON V1

Owner authority: Issue #66 comment6381524610. Base main72a183c445fbfc2de20311870e34f861dd85535f.
This is a definition/validation/provenance contract, **not a strategy execution or backtest engine**. No signals/orders/fills/PnL are evaluated.

## Compatibility matrix and dependency decision

| Surface | Accepted main | This contract / integration |
|---|---|---|
| Indicator registry/results | V1 scalar value and immutable IndicatorResult | defaults to existing IndicatorLibrary; registry.get injection with version, params, min_warmup_bars, output_fields (scalar default value), compute |
| Custody/PIT | CustodyAccessor enforces confirmed availability | actual accessor required; complete requested range, future/retrospective/corrupt bars rejected; warmup+lag output count required |
| Provenance | dataset manifest + indicator per-result hashes | immutable EvaluationBinding wraps all metadata, parameters, ordered bar/result commitments, cutoff and definition digest |
| Strategy JSON | no accepted generic contract | strict version1 AST/risk/timing; canonical definition separated from evaluation binding |
| Candidate grid | PR46 synthetic fixed-grid proposal | finite predeclared validated Cartesian family with unique digests; no optimizer or ranking |
| Ledger | FrozenSearchFamily/Attempt/DurableTrialJournal exist only in OPEN/UNMERGED research chain | caller-owned record_attempt(event_dict) port; records INVALID/PENDING/COMPLETE/FAILED/ABANDONED, no new journal, no upstream imports |

PR46 a4c106a02c55ee012eedf4c55c1488d71d850203 is stacked on #43 and earlier unmerged research PRs, not accepted main. Reuses the canonical-byte/frozen-protocol/candidate/commitment pattern; does not silently merge or copy its engine. A concrete adapter to DurableTrialJournal's existing Attempt API requires separate ancestry reconciliation. The port is not that journal implementation and makes no fsync, anti-rollback or independent custody guarantee. The injected sink must persist-or-raise and enforce family membership/event lifecycle; supplied in-memory mocks are test sinks only. Failure to record propagates; no successful receipt is fabricated.

Indicator V2 is independently reviewable [PR68](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/68). Runtime has **no V2 import**. Its typed vector registry is tested explicitly in integration_tests/, pinned to headf3ca2d5dde019a836fe6994b658a444c34b1cfb2; ordinary strategy validation works with main V1 alone. Both PRs target main; no implicit stacked merge order required. If either reviewed head changes, update the pin and rerun cross-PR integration before joint acceptance.

## Schema and bounded semantics

See examples/strategy_definition_v1.json (complete hashed document) and tests/test_sf_strat_01.py.
Required definition keys: schema_version, strategy_id, strategy_version, scope, indicators, entry, exit, timing, risk. Unknown/missing fields rejected.
scope RESEARCH_ONLY, schema_version "1"; identifiers/version labels explicit. Each indicator has unique name, registered indicator_id, version, explicit parameters and per-parameter typed min/max constraints. All defaults must be written explicitly (including EMA smoothing); bool is never an integer/number parameter.
AST only: numeric constant; indicator(name, field, lag>=0); comparisons gt/ge/lt/le/eq; all/any with2..8 boolean args; unary not. Max depth8,128 nodes per expression. No arithmetic/eval/import/code/callables or future/negative lag. Entry/exit must be boolean typed; all field references resolved before acceptance.
Timing fixed: CONFIRMED_CLOSE decisions; NEXT_ELIGIBLE_OPEN entry; same-bar ambiguity REJECT. This declares semantics for a future simulator; this module never interprets a trade.
Risk: ENTRY_NOTIONAL unit; max_exposure in(0,1], max_leverage exactly1, stop_fraction in(0,1), positive bounded target_fraction, entry_ttl_bars1..1000, holding_bars1..10000. These are unlevered research restrictions, not suitability/portfolio risk guarantees.
Candidate axes use name.parameter keys and bounded nonempty explicit lists; every candidate must pass original constraints, canonical duplicate candidates rejected; maximum default256. Family completeness/durable accounting is enforced by the caller's ledger, not a newly invented ledger here.

## Serialization and retained commitments

Canonical UTF-8, sorted keys, compact separators, finite IEEE754 binary64 decimal rendering via Python JSON (supported Python3.10..3.12), integral floats normalize to integers, signed zero to0; integers outside ±(2^53-1) rejected. No RFC8785 compliance claim. Only JSON-shaped data accepted; internal provenance tuple arrays normalize to JSON arrays. Duplicate JSON keys and NaN/Inf constants rejected; input max100KB, generic depth24. Definitions store canonical bytes only; returned dictionaries are copies.
to_json/from_json includes verified SHA256 digest. Hash integrity is verified against stored values; **external authenticity requires independently retained commitments**.
EvaluationBinding.from_dict additionally requires expected_digest from a retained source, not a hash supplied alongside attacker-controlled data. Binding includes definition identity, dataset version/hash, cutoff/range, bar checksums, indicator manifests/results. Definition remains constant across cutoff changes; binding changes. A manifest reconstructed from custody with different creation metadata intentionally yields a different binding.

bind_evaluation recomputes through custody+registry and checks manifest identity, parameters, dataset hash, output order/coverage, finite typed values, warmup and required lag. It is intentionally complete-only: no missing/partial/retrospective opt-out.

## Attempt lifecycle boundary / examples

prepare(raw_definition_json, family_id, candidate_id) records INVALID on rejected definition input and raises; valid input records PENDING and returns a frozen handle.
finish(handle, COMPLETE, binding=verified_binding, result_digest=retained_result_sha256) binds family/candidate/input/strategy/binding/result hashes; FAILED and ABANDONED have explicit events even when no result exists. The sink must validate family membership, uniqueness, terminal transitions and persistence (a forged caller handle is not authenticated by this port). Do not label preparation or binding as a completed profitable trial.

## Validation
Default standalone tests: existing50 indicator +45 guard and strategy tests.
CI installs pytest+pytest-timeout to honor repository timeout config. Existing sf-ind-01 workflow also gains that missing runner plugin (one-line test-only correction; assertions unchanged).
Six CI environments Ubuntu/Windows ×3.10/3.11/3.12 test standalone contract then exact pinned V2 integration via package search-path addition in the disposable CI checkout. No changes to tracked source are needed to combine the independent branches.
Pinned schema/binding fixture commitments test Windows/Linux parity; future/cutoff/gap/retrospective/warmup, incorrect output/manifest, mutation/roundtrip/tamper and invalid attempts covered. Exact final CI counts/SHAs are in the PR/Issue report, not guessed here.

VWAP/session anchors, cross-asset availability, new data contracts, concrete unmerged ledger chain integration, signal evaluation/optimization, Holdout, live/paper/shadow trading and G1 changes remain outside this deliverable. No profitability or production claim. Owner review/merge authorization separate; Issue66 stays open.

## Final acceptance hardening
JSON floating-point overflow and nonzero underflow-to-zero are rejected before canonicalization. Unexpected registry/provider exceptions produce a FAILED attempt event and re-raise; validation rejections remain INVALID, and sink failures always propagate. Binding rejects scalar/vector shape mismatches and per-result warmup mismatches even if a provider supplies self-consistent hashes. These checks validate adapter contracts; they do not sandbox arbitrary injected Python code.
