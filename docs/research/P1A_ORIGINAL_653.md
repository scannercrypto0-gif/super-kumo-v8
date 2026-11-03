# P1-A original January cohort — Work adapter

Authority: owner Work request and #77/6597751231, blueprint #77/6597621790.
This is a new isolated Draft stacked on Factory #209, not main implementation
or a merge/cherry-pick of other unmerged candidates. No Claude file is changed.

## Pinned inventory / dependency

| Reference inspected | Head | Base | State |
|---|---|---|---|
| main | dbc191df72f4b4d1ebb7d490926dcad4325dac12 | — | separate accepted baseline |
| Factory #209 | 47558bea22af5480aa84148fd22bf2890bbe22ae | bfd3d80b99602c464872e3676082833fc304f43b | draft/unmerged |
| P0 #204 | 2bfd691d7883606ec4fa691ab70a6a0d7e24709c | dbc191df72f4b4d1ebb7d490926dcad4325dac12 | draft/unmerged |
| Core #216 | 6eabff56dcc79b0abd0a4b3889bc33ca98ce68f9 | 59fb9a71714a719a58b00d4de05654c409fb8a67 | draft/unmerged |
| Synthetic #46 | a4c106a02c55ee012eedf4c55c1488d71d850203 | 0a3d900d5d85a6d987f1e26eac8f99660f05b2e5 | open/unmerged; not used |

Factory pin is a descendant of main (0 main-only /172 Factory-only commits at
intake). New Work diff is only its new module/test/doc/workflow. Target #209's
branch as the Draft base so its already accepted 80-test gate is not repeated.
The stack is an explicit dependency, not main acceptance.

Reuse: C1 admit_source/load_source verify original nested daily ZIP checksums;
C2 load_journal/_verify_factory_receipt and immutable identity/prefix helpers;
W1 RetrospectiveSnapshot/market_outcome; Factory project and typed F3 descriptive
projection; original readonly_link's anchor guard. No producer, strategy,
fill-model, ledger builder, ACK-transition, exchange client or network call.

The generic readonly_link verifier requires original pointer/version fields
absent in this actual P0 schema. The older ZIP adapter expects 660 members,
whereas the recovered audited Work package has 16. Neither is fed invented
fields or relabeled input. Their anchor guard plus actual C2 receipt verifier
are reused against exact private original bytes. Temporary copies are private,
deleted after validation; owner originals are never modified.

## Local CLI and contract

Python 3.11+ standard library; no extra dependency, original P0 replay or source
download. Package is the existing private original audit intake with SHA256
`c72b6271b966ab6f522543a04831053556cfbdf3bd9b7b7fd8b4bc433f2ae503`.
Do not place it or any report/index payload in Git/CI/public issues.

```sh
python -m unittest -v tests.test_aql_p1a_original_653
python -m research_wp_r0.aql_p1a_original_653 \
  --package /private/ATLAS_P0_ORIGINAL_AUDIT_PRIVATE_20261103.zip \
  --output /private/new-p1a-result \
  --code-sha FULL_WORK_COMMIT_SHA \
  --generated-at-utc ACTUAL_UTC_TIMESTAMP_ENDING_Z
```

Both SHA and generation time are explicit provenance parameters, not source
availability/PIT assertions. Reuse exactly the same parameters for deterministic
byte reproduction in another NEW output directory. Existing output is rejected.
Report result.json, compact summary.md, three private JSONL indices and SHA256
manifest are written. Indices are derivatives of original source, not claimed
recovered original files. No uploaded owner helper script is run.

Artifact `schema_version=aql-p1-original-opportunity-outcomes.v1` has source_proof,
code_sha, generated_at_utc, policy_version, rows, summary, threats. Rows use
(trial_id,opportunity_id,producer_event_id,envelope_sha256,horizon_hours),
retain original receipt F3 disposition and saved financial event IDs separately.
No original F1/direction/regime or F3-reason exists in these receipts: null plus
explicit missing status; never infer a LONG from a BUY/debit, eligibility from
TRIGGERED, or reason from later outcomes. BASE_DESCRIPTIVE only; SHADOW is
NOT_EVALUABLE_NO_PREDECLARED_PAIRED_CANDIDATE.

Future windows are strictly [decision_cutoff_ms,cutoff+4/24/72h), native 15m
16/96/288 bars. Missing grid/duplicate/unfinalized/invalid OHLC -> UNKNOWN.
Source-end truncation -> CENSORED; partial extrema/returns are null, not zeros.
Full valid windows -> COMPLETE. W1's signed market_outcome honestly returns
DIRECTION_NOT_ESTABLISHED on full windows. A thin unsigned projection uses the
same window rules to expose observed high/low and price-relative market returns.
Reference is OPEN_AT_CUTOFF_NON_EXECUTABLE (modeled decision is 2s later).
market_low_return can be negative; these are direction-agnostic price returns,
not signed trade MFE/MAE, executable prices, fills, fee-adjusted PnL or alpha.
Directional metrics remain null for all original rows.

Work only emits canonical JSON and compact coverage counts. Reusable validation,
schema, distribution aggregation and renderer remain Claude's separate namespace;
no optional Claude component is needed to produce the first private real report.
Contract coordination: #77/6597806875. Independent review follows implementation.

## Actual original source-backed coverage

Read original package locally with the new adapter (not a P0 replay):
653 opportunities =616 NO_SIGNAL +27 REJECTED +10 TRIGGERED;1959 horizon slots.

| Horizon | COMPLETE | CENSORED at archive end | UNKNOWN |
|---|---:|---:|---:|
| 4h | 637 | 16 | 0 |
| 24h | 557 | 96 | 0 |
| 72h | 365 | 288 | 0 |

These are outcome-window coverage counts, not 1959 independent observations or
new trades. 20 saved modeled financial events remain references for 10 original
TRIGGERED cases; no financial effect is inferred for 643 other decisions.
Original journal final653 APPLIED/0 ACKED; isolated copy653 ACKED only.

Seven days, overlapping horizons, retrospective publication/correction clocks,
absent original F1/context/regime and heavy end censoring limit interpretation.
No alpha, statistical strategy choice, holdout opening, BASE/SHADOW uplift,
authenticated PIT, G0, deployment, Paper/Live, or merge is authorized.
CI uses TEST_ONLY fixtures exclusively and is not original-data-run evidence.
Final code SHA, private report byte hashes, exact command and CI URLs belong in
the delivery comment after publication; no private payload is committed here.
