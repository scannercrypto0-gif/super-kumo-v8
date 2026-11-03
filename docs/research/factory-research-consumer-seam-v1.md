# Factory Research Consumer Seam V1 — F1–F4 TEST_ONLY delivery

Owner: Factory. Stacked Draft PR #229 targets frozen Factory Draft #222 at
\`6b93abf975648d3ce5ee9c28c7b33c72686f4e6b\`. No change to #222, original
private Option C scoring, Core #226, Scanner #227, or Work #228.

## F1: existing owners/APIs

- Core paired schedule: \`aql.p2.core.paired-schedule.v1\`.
- Existing Factory \`research_wp_r0.aql_p2_factory_lab.validate_schedule\` checks
  source, protocol, exact pair/BASE/SHADOW denominator, sealed SHA, embargo,
  holdout, retrospective NON_PIT and NOT_OBSERVED authority.
- Existing Factory \`build_lab\` consumes six (2 arms × 3 horizons) descriptive
  observations per pair, checks COMPLETE/CENSORED/UNKNOWN and same-source
  market windows; it does not model trade fills.
- Existing \`prepare_real_development\`, \`build_modeled_trade_package\`, and
  Option C remain separate and unchanged; no new strategy evaluator built.
- Core Bridge #226 offers draft read-only archive/custody packet contracts only,
  not a validated connected Scanner/Discovery/Factory source.
- Work Harness #228 currently consumes existing Factory report projections,
  does not invoke Factory evaluator; it remains independently Draft/unmerged.

## F2: versioned handoff and mapping

\`build_research_handoff(schedule, envelope)\` reuses the *real existing*
\`validate_schedule\`. Immutable input \`aql.factory.research-consumer-seam.v1\`
requires \`artifact_sha256\` over canonical JSON excluding the digest itself
and strict TEST_ONLY/NO_TRADING authority. It binds:

| Input field | Factory validation/mapping |
|---|---|
| \`source_schedule_sha256\` | equals validated actual Core schedule SHA |
| \`source_package_sha256\` | equals source in Core schedule |
| \`source_manifest_sha256\` | SHA-shaped, bound identically across rows; authenticity beyond this TEST_ONLY fixture NOT_ATTESTED |
| \`cohort_id\`, \`strategy_version\` | nonempty and identical for every paired arm |
| \`pair_id\`, \`opportunity_id\`, \`arm\` | exact Core schedule pair/arm identity, one row per slot |
| \`attempt_id\` | unique within cohort and repeated exactly on deterministic replay |
| \`decision_cutoff_ms\` | equals Core opportunity cutoff |
| \`feature_available_ms\`, \`feature_availability_class\`, \`feature_snapshot_sha256\` | data available no later than cutoff; retrospective NON_PIT only |
| \`source_disposition\`, \`status\` | source disposition must match Core; unverified promotion to NOMINATED rejected |
| descriptive outcome / modeled trade / return | strictly NULL, NOT_OBSERVED: evaluation happens only at separate existing Factory descriptive stage |

The receipt \`aql.factory.research-consumer-receipt.v1\` preserves 7 mutually
exclusive research states: NOMINATED, NO_SIGNAL, REJECTED, UNKNOWN, NULL,
UNSCANNED, UNRESOLVED. Conservation: \`sum(status_counts) == arm_slots ==
2 * scheduled_pairs\`. UNRESOLVED/UNSCANNED are allowed only as labels on
received Core UNKNOWN slots in this TEST_ONLY adapter, **not** evidence of a
complete real-world Scanner universe; external Scanner denominator remains
\`NOT_CONNECTED\`. NULL is not a zero return or a modeled trade.

\`build_research_report(schedule, envelope, observations)\` invokes existing
Factory \`build_lab\` with the real TEST_ONLY schedule and descriptive
4/24/72h windows (no mocked schedule validator). It binds output to both
source receipt SHAs and enforces 3 observation horizons × 2 arm slots/pair.
It does not call fill/fee/ten-bar trade engine or imply PIT/OOS, alpha,
holdout usage or real execution. Ambiguous intrabar results remain UNKNOWN;
no synthetic wins/losses are manufactured.

## F3 adversarial gate

Focused tests reject wrong source/schedule/manifest pin, wrong cutoff,
late/future feature, mixed cohort/strategy, duplicate/conflicting attempt
and slot, incomplete denominator, NULL→zero coercion, fabricated trade
or descriptive outcome, false NOMINATED promotion, false source disposition,
false LIVE_PIT, unauthorized execution, mutated receipt hash, and
ambiguous-descriptive winner injection. Exact duplicate inputs deterministically
produce the same output SHA.

## F4 consolidated read-only TEST_ONLY Core-style fixture

Uses the **existing repository Factory/Core paired-schedule test fixture**
as a frozen synthetic Core-style query result. Extends to four separate
source-identity-bound opportunities: NO_SIGNAL, REJECTED, UNKNOWN, TRIGGERED.
No private data, outside checkout, synthetic strategy success or source
acquisition. One consolidated call performs TEST_ONLY source/pair validation,
research intake, and **actual existing Factory** descriptive evaluation.

- 4 scheduled pairs / 8 paired arm slots;
- states: NO_SIGNAL 2, REJECTED 2, UNKNOWN 1, UNSCANNED 1,
  NOMINATED 1, NULL 1 = 8;
- 24 4/24/72h observations (4 pairs × 2 arms × 3 horizons);
  4 COMPLETE at 4h; 4 CENSORED at 24h; 4 UNKNOWN at 72h,
  with identical BASE/SHADOW market windows;
- canonical receipt repeated identically, schedule/envelope/observations
  not mutated; exact SHA printed in CI log;
- \`modeled_trade_engine=NOT_INVOKED\`,
  \`fills_pnl_alpha=NOT_COMPUTED\`, \`trading_authority=NONE\`.

Reproduction (from Factory #229 checkout):

\`\`\`sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover \
  -s tests -p 'test_aql_factory_research_consumer_seam.py' -v
\`\`\`

Initial exact code HEAD \`2d48df37f1b49be727888960edf3e7fbc65595a1\`:
focused [Actions run 41650249042](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/41650249042),
job \`125966173004\`: **3/3 tests PASS**, including the single F4
consolidated integration test and F3 subcases. F4 receipt SHA256:
\`fcb14d4094ea6d3040400d51c7681798999a1721dbf95bc607b55379ace9458e\`.
Final code/doc HEAD CI must be checked independently after this documentation
commit; do not claim it without an actual run.

## Work-ready requirements and remaining blockers

Future Work needs *separate owner authorization* and pinned, independently
validated upstream source/universe/Scanner/Discoverer attempts with complete
unscanned denominator, compatible research-candidate version/cutoff
representation, and source-manifest evidence. The current adapter is
\`TEST_ONLY_INTERFACE_READY\` but \`AUTHENTIC_SOURCE_NOT_CONNECTED\`,
\`SCANNER_UNIVERSE_NOT_CONNECTED\`,
\`DISCOVERER_NOT_CONNECTED\`, and
\`PRIVATE_E2E_NOT_PERFORMED\`. Core #226 / Work #228 / Scanner #227
are unmerged. No cross-owner edits, merge, G0, PIT/OOS/holdout,
deployment, paper/live trading or exchange credentials.
