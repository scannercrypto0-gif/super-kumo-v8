# ATLAS Quant Lab — Evidence Register
**Version:** 1.2-CLOSEOUT | **Evidence snapshot:** 2026-10-24
**Main source baseline:** `bcca2238e019b750f564d4b5568e33f2a7aaf5cf` | **Documentation:** PR #74, pre-merge closeout snapshot; ready/merge state is authoritative in GitHub metadata.
Reviewed documentation baseline: `e4ce1c8a5d7911f52fb67e52f7e58c2e0ee5b476`; final document HEAD is in PR metadata/correction matrix, not the main-source SHA.
Evidence IDs and scope: [09_EVIDENCE_REGISTER.md](09_EVIDENCE_REGISTER.md). No production authorization or owner decision is created by this map.

## Scope and labels

- **VERIFIED MAIN:** file/API semantics directly inspected at the main baseline; presence alone is not acceptance.
- **VERIFIED PR ONLY:** exact unmerged branch source/tree inspected; never treated as main.
- **VERIFIED CI:** Actions metadata plus relevant job logs/checkout/counts inspected; test scope remains synthetic/software unless stated otherwise.
- **REPORTED:** an issue/comment records an observation; this docs task did not rerun the external environment observation.
- **DESIGNED / NOT IMPLEMENTED:** respectively documented contract versus no runtime found in the explicitly inspected main/PR scope.
- **NOT TESTED / UNKNOWN:** named evidence missing or not established; never interpreted as zero failures or approval.

**Evidence Quality overall: PARTIAL.** Source/merge/CI facts are verified. Live
Binance observations remain reported evidence, not independently rerun here;
real empirical/OOS/forward performance, external custody/offsite protection and
production authorization are absent. Historical governance-signature provenance
is not re-established by an issue's closed state. These limitations do not
prevent accurate documentation acceptance.

All links below use immutable source refs or specific issue/comment/run IDs.
Existing E identifiers are retained; new evidence uses E-80 onward so historical
Rounds1/2 citations are not silently repurposed.

## Canonical architecture and state

| ID | Evidence | Classification / interpretation |
|---|---|---|
| E-01 | [01_CONTRACT.md](https://github.com/scannercrypto0-gif/super-kumo-v8/blob/4e4c3537036bdf2b106c1a63ec65b2a9855972a7/01_CONTRACT.md) | VERIFIED MAIN: modular monolith, owner/trader authority, PIT/core-run isolation; many clauses remain provisional specifications |
| E-02 | [02_ROADMAP.md](https://github.com/scannercrypto0-gif/super-kumo-v8/blob/4e4c3537036bdf2b106c1a63ec65b2a9855972a7/02_ROADMAP.md) | VERIFIED MAIN: G2 observation, G3 Momentum, G4 Lab, G5 events, G6 multi-trader; no relabeling by this map |
| E-03 | [03_DECISIONS.md](https://github.com/scannercrypto0-gif/super-kumo-v8/blob/4e4c3537036bdf2b106c1a63ec65b2a9855972a7/03_DECISIONS.md) | VERIFIED MAIN: original004 preserved and provisional G1-ARCH contracts; later conditional Option B in E-54 is separate |
| E-04 | [04_STATE.md](https://github.com/scannercrypto0-gif/super-kumo-v8/blob/4e4c3537036bdf2b106c1a63ec65b2a9855972a7/04_STATE.md), [05_WORK_LOG.md](https://github.com/scannercrypto0-gif/super-kumo-v8/blob/4e4c3537036bdf2b106c1a63ec65b2a9855972a7/05_WORK_LOG.md) | VERIFIED MAIN historical records: several entries predate later live/CI/merge results; not a fresh status API |
| E-05 | [08_RISKS.md](https://github.com/scannercrypto0-gif/super-kumo-v8/blob/4e4c3537036bdf2b106c1a63ec65b2a9855972a7/08_RISKS.md) | VERIFIED MAIN: preserve original R01–R10 meanings/severities; map05 no longer renames them |
| E-06 | [10_TEST_POLICY.md](https://github.com/scannercrypto0-gif/super-kumo-v8/blob/4e4c3537036bdf2b106c1a63ec65b2a9855972a7/10_TEST_POLICY.md) | VERIFIED MAIN: scoped evidence, forward≠realized PnL, complete populations and owner gates |

## Inspected main source (presence, not production acceptance)

| ID | File / exact source | Verified facts |
|---|---|---|
| E-10 | [historical_library.py](https://github.com/scannercrypto0-gif/super-kumo-v8/blob/4e4c3537036bdf2b106c1a63ec65b2a9855972a7/research_wp_r0/historical_library.py) | Versioned immutable bars/manifests, CustodyAccessor, complete range, availability classes; source/receipt assertions are not independent custody |
| E-11 | [indicator_library.py](https://github.com/scannercrypto0-gif/super-kumo-v8/blob/4e4c3537036bdf2b106c1a63ec65b2a9855972a7/research_wp_r0/indicator_library.py) | SMA/EMA/RSI/ATR; computation_hash hashes ordered result provenance hashes, not Python object identity |
| E-12 | [indicator_library_v2.py](https://github.com/scannercrypto0-gif/super-kumo-v8/blob/4e4c3537036bdf2b106c1a63ec65b2a9855972a7/research_wp_r0/indicator_library_v2.py) | MACD_v2,BBANDS_v2,ADX_v2,STOCH_v2,ROC_v2,OBV_v2; typed VectorResult/VectorManifest |
| E-13 | [strategy_definition.py](https://github.com/scannercrypto0-gif/super-kumo-v8/blob/4e4c3537036bdf2b106c1a63ec65b2a9855972a7/research_wp_r0/strategy_definition.py) | StrategyDefinition, bind_evaluation→EvaluationBinding, candidate_grid, AttemptRecorder; no bind_indicators/BoundStrategy |
| E-14 | [pipeline.py](https://github.com/scannercrypto0-gif/super-kumo-v8/blob/4e4c3537036bdf2b106c1a63ec65b2a9855972a7/src/aql/pipeline.py) | Shared journal, consumer, bounded recovery and background=True calls; no autonomous production certification |
| E-15 | [lanes.py](https://github.com/scannercrypto0-gif/super-kumo-v8/blob/4e4c3537036bdf2b106c1a63ec65b2a9855972a7/src/aql/lanes.py) | BackgroundLane, JournalConsumer, cooperative WritePriority |
| E-16 | [operational_store.py](https://github.com/scannercrypto0-gif/super-kumo-v8/blob/4e4c3537036bdf2b106c1a63ec65b2a9855972a7/src/aql/storage/operational_store.py) | upsert/count/get_stored_keys/get_range; cloud status NOT_TESTED; no write_bar/get_latest_bar API |
| E-17 | [durable_journal.py](https://github.com/scannercrypto0-gif/super-kumo-v8/blob/4e4c3537036bdf2b106c1a63ec65b2a9855972a7/src/aql/journal/durable_journal.py) | WAL/FULL, bool commit, replay, mark_persisted; actual priority callers |
| E-18 | [health/snapshot.py](https://github.com/scannercrypto0-gif/super-kumo-v8/blob/4e4c3537036bdf2b106c1a63ec65b2a9855972a7/src/aql/health/snapshot.py) | HealthSnapshot/take_snapshot software exists; unified dashboard does not |
| E-19 | [binance_collector.py](https://github.com/scannercrypto0-gif/super-kumo-v8/blob/4e4c3537036bdf2b106c1a63ec65b2a9855972a7/src/aql/collector/binance_collector.py) | Real callbacks, finality/ahead-of-host guard, journal commit and reconnect |
| E-20 | [gap_recovery.py](https://github.com/scannercrypto0-gif/super-kumo-v8/blob/4e4c3537036bdf2b106c1a63ec65b2a9855972a7/src/aql/recovery/gap_recovery.py) | recover_gap(existing_keys)→bars/report; code request cost2/max1000/session1200, not fresh provider entitlements |
| E-21 | [_dep_guard.py](https://github.com/scannercrypto0-gif/super-kumo-v8/blob/4e4c3537036bdf2b106c1a63ec65b2a9855972a7/research_wp_r0/_dep_guard.py) | Explicit static AST policy, not automatic import-time/runtime sandbox |

## Tests and historical evidence IDs

| ID | Scope | Count / disposition |
|---|---|---|
| E-30 | tests/test_sf_data_01.py |141 cases in unchanged main source; exercised within E-86's combined PR78 tree, not506 historical tests |
| E-31 | tests/test_sf_ind_01.py |50 cases in E-82 |
| E-32 | tests/test_sf_ind_02.py |58 cases in E-82 |
| E-33 | tests/test_sf_strat_01.py |57 cases in E-82 |
| E-34 | G1 WP01/02/03/04/fix01/completion files |157 collected per main-equivalent G1 suite; actual OS-dependent skips in E-85 |
| E-35 | [Historical G1 run40085463732](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/40085463732) | Metadata SUCCESS/head453a14d850f64a586f3ec371f826d962ded25b2e; G1 scope only, not evidence for all research tests; newer E-85 used |
| E-36 | Older506pass/2skip local statement | REPORTED/historical aggregate, environment/scope not independently reproduced here; not adopted as current package or G1 count |
| E-37 | [Historical G1 postmerge40071051636](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/40071051636) | Earlier #62 baseline evidence linked by #64; not a fresh rerun in this docs task |
| E-40 | Main .github/workflows | Workflow files exist; presence alone is not a passed run |
| E-41 | [SF66 run40085840893](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/40085840893) | COMPLETED/SUCCESS, replacing old in_progress entry; details E-82 |

## Issue and merge states checked through GitHub API

| ID | Item | Snapshot state / meaning |
|---|---|---|
| E-50 | [#1](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/1) | CLOSED; main state documents report G0 APPROVED, but visible old review comments remain conditional. This task does not independently re-establish the historical owner-signature trail or infer approval for new ADRs/production |
| E-51 | Research PR chain | #18–#31/#33–#39/#41/#43/#46 OPEN/unmerged. #32/#40/#42/#45 are merged G1, not merged research. #48 closed without merge |
| E-52 | [#64 bounded report6381329727](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/64#issuecomment-6381329727) | OPEN; REPORTED bounded ACCEPTED WITH FOLLOW-UPS supersedes earlier clock-blocked report |
| E-53 | [#65](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/65) | OPEN; named Supabase Cloud sandbox/credential route absent, cloud NOT TESTED |
| E-54 | [#67 owner decision6382338071](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/67#issuecomment-6382338071) | OPEN issue; Option B conditionally DECIDED, Phase1 authorized, final ADR/operating budgets not approved |
| E-55 | [#71 RESULT6383654040](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/71#issuecomment-6383654040) | OPEN; merged PR73 technical READY FOR OWNER MERGE APPROVAL, merged as inactive code; not activated |
| E-56 | [#72](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/72) | OPEN; owner-approved FUTURE concept under C, unprioritized; initial request then future conditional/deadline-triggered reassessment design |
| E-60 | [PR62](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/62) | MERGED baf762e874995b2cede3b02fa0846b0cb5389de1; G1 isolation/sandbox preparation, not IndicatorV2 merge |
| E-61 | [PR63](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/63) | MERGED72a183c445fbfc2de20311870e34f861dd85535f; SF-IND guard/CI fix, not pipeline integration |
| E-62 | [PR68](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/68) | MERGED ea9cf19a3b77019c8c0673756fad54068a50532b; IndicatorV2 |
| E-63 | [PR69](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/69) | MERGED4e4c3537036bdf2b106c1a63ec65b2a9855972a7; StrategyJSON |
| E-64 | [PR60](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/60) | MERGED3bb0d9425703547123f2da332505ba2eb61db540; IndicatorV1 |
| E-65 | [PR57](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/57) | MERGEDcf4339e83d8ce2fe30cc727b6c470f1fb0bf63bb; isolated historical library |
| E-70 | R09 | CRITICAL/UNRESOLVED; no issuer-side remediation evidence established |
| E-71 | Bounded Binance | Same reported observation as E-52; not independently reproduced, no provider outage/stress or production claim |
| E-72 | Holdout custody | Code exists in unmerged chain; no accepted-main independent empirical custody workflow |
| E-73 | Supabase | Code/adapters/local PostgreSQL tests exist; cloud acceptance NOT TESTED |
| E-74 | WritePriority | Old unused-claim corrected; caller evidence E-88, no code fix authorized |

## Updated exact-source/CI evidence

| ID | Evidence | Exact scope and limitations |
|---|---|---|
| E-80 | [PR46 source](https://github.com/scannercrypto0-gif/super-kumo-v8/tree/a4c106a02c55ee012eedf4c55c1488d71d850203/research_wp_r0) | VERIFIED PR ONLY: integrity/statistics/evaluation/opportunity_clusters/temporal_contract/trial_holdout/durable_journal/owner_checkpoints/external_custody/strategy_factory/measured_pipeline. Actual code inspected; tests R0/R1/R2/R3/R5/R6/R7/R9/R10/R11/R12/R13/R14/R15/R16/R18/R19/R40/R42 present |
| E-81 | [Draft78](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/78) | OPEN/Draft/unmerged; initial validated head1887fa3880c39faa306a21152518d6a1dcaac509, tree40c7996af4f2654e06bace3df3cca3d730e1bf89; authorized continuation head6e905a2a469ec616922fbc6095dc34dcaeb5cb60, tree9b609d2323ba0ad5566f0545c6e42243dda7d146 (CI pending at this docs snapshot); accepted-main-compatible input contracts, no imported engine/durable ledger; #77 OPEN/BLOCKED full milestone |
| E-82 | [SF66 native combined-main CI40085840893](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/40085840893) | VERIFIED CI:6×216=1296 passing executions,0skip/fail.50V1+45guard+58V2+57strategy+6integration. Workflow harness head a36715a3942caef87e5db5157e47e51a86ce9bfe; actual checked-out source4e4c3537036bdf2b106c1a63ec65b2a9855972a7, not harness source. Linux/Windows job logs inspected; #66 closed |
| E-83 | [Legacy research CI39786828419](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/39786828419) | VERIFIED CI: Ubuntu/Windows Python3.14.8, unittest discover test_research_wp_r*.py; Ran204tests/OK each. Metadata head a4c106a; actual synthetic merge ed65174045d1db69fbd27c04ebe837ab05e782ac has identical tree c2b33fb2c455309b792e0de34fae5ffe792c03ee to PR head. Not main integration or empirical validation |
| E-84 | [merged PR73 CI40089205693](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/40089205693), [final report](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/73#issuecomment-6383587680) | VERIFIED CI/PR: headcb7829e3e3c13c6b6433b6625f2df35d1991a65d, treef20adbc9e0c8487ed350475a16b79ed1eebf8a1c;6×60=360pass,0skip/fail; technically reviewed optional inactive code, merged in main at bcca2238e019b750f564d4b5568e33f2a7aaf5cf.4096-row local synthetic drill, no off-device/power-loss certification |
| E-85 | [G1 virtual integration CI40089205666](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/40089205666) | VERIFIED CI: actual synthetic merge707f7489e094817f35537eee4907a22ca07f045e, parents main4e4c353+PR73cb7829e; treed1f1df246e092ba118f26348e8f73de25771162a equals independent local merge-tree. Ubuntu155pass/2skip, Windows147pass/10skip; disposable PostgreSQL1pass/26deselected, NOT Supabase |
| E-86 | [Draft78 CI40087361925](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/40087361925) | VERIFIED CI: actual head1887fa3880c39faa306a21152518d6a1dcaac509;6×393=2358pass,0skip/fail (141historical+216core+36new). Local Windows391pass/2existing symlink-privilege failures explicitly reported; not silently skipped |
| E-87 | [#65 RESULT6381563663](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/65#issuecomment-6381563663) | REPORTED offline/local PostgreSQL evidence; Supabase Cloud TLS/RLS/roles/outage NOT TESTED; authorization needed |
| E-88 | [Journal callers](https://github.com/scannercrypto0-gif/super-kumo-v8/blob/4e4c3537036bdf2b106c1a63ec65b2a9855972a7/src/aql/journal/durable_journal.py#L88), [priority test](https://github.com/scannercrypto0-gif/super-kumo-v8/blob/4e4c3537036bdf2b106c1a63ec65b2a9855972a7/tests/test_g1_completion.py#L60) | VERIFIED MAIN: constructor + commit/mark_persisted + pipeline background=True disprove zero-caller #75 premise; no host-wide scheduling guarantee |
| E-89 | [Manifest identity source](https://github.com/scannercrypto0-gif/super-kumo-v8/blob/4e4c3537036bdf2b106c1a63ec65b2a9855972a7/research_wp_r0/historical_library.py#L301), [#77 RESULT](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/77#issuecomment-6383320738) | VERIFIED code/current contract + E-86 tests: independent imports differ by creation/instance identity; retained-manifest replay can match across processes; no Python object-id dependency; additive identity now authorized by E-92 |
| E-90 | This documentation package | Ten-file static cross-consistency audit and final PR metadata/correction matrix. No runtime test reruns or independent external performance/custody certification are claimed |

| E-91 | [PR73 merge](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/73), [owner closeout](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/74#issuecomment-6384037397) | VERIFIED API: merged bcca2238e019b750f564d4b5568e33f2a7aaf5cf; inactive code only; #71/#67 remain OPEN pending operating/ADR acceptance |
| E-92 | [OD01B owner approval](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/76#issuecomment-6383377178), [research continuation](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/77#issuecomment-6383377744) | Explicit additive identity implementation authorization on existing Draft78; no research merge/holdout/runtime authority |
| E-93 | [Future event memory](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/80) | FUTURE/UNPRIORITIZED/NON-BLOCKING; future immutable event versions/PIT linkage/all outcomes/missed-opportunity methods, no implementation authority now |

## Continuity and evidence precedence

Owner closeout comment6384037397 is the latest docs execution authority; research continuation6383377744 is independently scoped. The earlier attachment remains context. Latest relevant
agent storage delivery: #71 RESULT6383654040/HANDOFF6383661132; research input
delivery #77 RESULT6383320738/HANDOFF6383324299. These are not represented as
separate unavailable owner-submitted Work messages. GitHub source/API/CI facts
are distinguished from quoted reports and historical state prose. No inaccessible
conversation was reviewed. This snapshot precedes the final ready/merge transition. Owner closeout authorizes descriptive PR74 merge after consistency and CI; runtime decisions remain separate.

## Closeout continuity — owner directives, 2026-10-24

PR #73 is MERGED into main at `bcca2238e019b750f564d4b5568e33f2a7aaf5cf` (source head `cb7829e3e3c13c6b6433b6625f2df35d1991a65d`). Code integration does not activate production, provision independent off-device backup, ratify the final ADR, resolve R09, or close #71/#67. E-91.

OD-01 Option B is owner-approved in #76 comment6383377178; #77 comment6383377744 authorizes additive research implementation on Draft78, not merge. OD-02/03/05 remain proposals. This specific approval supersedes older pending-OD01 wording. E-92.

Issue #80 is FUTURE / UNPRIORITIZED / NON-BLOCKING: event registry/versioned as-known-at-decision references, complete opportunity population and missed-opportunity analysis belong to future reconciliation. No code/PR/subissue or trading influence is authorized by #80. Existing PIT rules cover only part of that future capability. E-93.
