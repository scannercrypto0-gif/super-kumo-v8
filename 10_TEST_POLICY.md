# Test and evidence policy
Unit: indicator math, clocks, cutoff, outcomes, state transitions, fill calculations.
Property: same input same output; no future references; idempotent writes; missing data never silently passes.
Integration: Binance fixtures, Supabase test database, retries, local spool and restarts.
Replay: frozen datasets, checksums, exact versions.
Failure: 429, timeout, delisting, missing candles, same-bar TP/SL, offline writes, duplicate jobs.
Load: measured symbol coverage, API weights, CPU/RAM, Supabase rows/egress, backlog.
Research: distinguish forward max return from realized paper PnL; report full denominators; compare against random and simple momentum baselines; purged time splits for overlapping 72h labels; all experiments registered; parent/shadow paired and forward-validated.
Gate evidence: commit + test command/output + fixture hash + failure cases + benchmark + known limitations + reviewer + owner signature.

## Future acceptance/regression scenarios — G0-PAPER-01–08

Specification only; none of these tests is claimed executed by this documentation task. Use focused deterministic fixtures and frozen policy versions; add risk-based integration/recovery coverage when implementation is authorized. Reference: [canonical provisional decisions](03_DECISIONS.md#g0-paper-trading-decisions--owner-selected-provisional-rules).

| Decision | Scenario | Required evidence / expected behavior |
| --- | --- | --- |
| 01 | Entry condition never met | No manufactured fill; NO_FILL/expiry reason retained; rejection distinguishable. |
| 01 | Immediate entry and delayed availability | First eligible price strictly after availability; no earlier price or future-data entry selection. |
| 02 | Same-bar TP/SL with/without finer evidence | Resolve only with legitimate ordering; otherwise factual AMBIGUOUS plus separate best/worst paths and aggregate trader bounds; best case not verified performance. |
| 03 | Fees, missing execution evidence and stressed costs | Gross/baseline-net/stress reported independently; version/source/effective date recorded; no hard-coded 0.01% or perfect missing-data fallback. |
| 04 | Reference and smaller/larger notionals | Provisional 1,000 USDT and feasible sensitivity scenarios reflect available liquidity; insufficient evidence flagged; no portfolio/live-capital interpretation. |
| 05 | Two traders same symbol; duplicate active signal in one trader | Cross-trader independence preserved, within-trader duplicate suppressed per versioned identity; overlap reported, grouped Telegram does not merge records. |
| 06 | Expiry/early invalidation; configuration later changes | Frozen original validity remains; expired opportunities retained; entry validity does not cap filled holding duration. |
| 07 | Early exit then original TP reached | Original trade stays closed; preregistered post-exit research captures target touch independently. |
| 07 | TP1 raised stop hit before later TP2 | Record missed upside on isolated fixed/raised-stop comparison with event ordering/ambiguity; no original-path rewrite. |
| 07 | TP1 raised stop followed by further fall | Record protected downside and aggregate paired risk-adjusted costs/sample-size evidence, not anecdotal superiority. |
| 07 | Adjustment conflicts and future partial exits | Only predeclared timestamped adjustments; conflicting order uses 02; partial mechanics remain unimplemented until separately specified. |
| 08 | Outage spans TP/SL | Chronological missing-interval recovery, event vs ingestion/recovery times, no stale-last-price exit or invented offline strategy decision; unresolved ordering uses 02. |
| 08 | Restart/replay repeated | Same fills/closes/accounting/alerts produced once; durable progress and correction lineage; original decisions unchanged. |
| 08 | Irrecoverable data gap | Explicit unresolved status; exclude from confirmed performance; report unresolved denominator and any transparent scenarios. |
| 02/07/08 | Counterfactual/recovered-data leakage | Same frozen initial conditions and visibility boundaries, separate variants, no mutation/reopening or hindsight decision fabrication. |

Implementation evidence must include fixture/data hashes, source visibility/availability assumptions, policy versions, expected/actual outputs and aggregate reconciliation. No gate completion or promotion follows from documenting these scenarios.

## Future TIME/DATA acceptance and negative scenarios
Documentation expectations only, not executed tests. [Canonical provisional decisions](03_DECISIONS.md#g0-time-and-data-provisional-decisions). Freeze fixtures, source visibility assumptions and versions; compare original and corrected runs without silently rewriting evidence.

| IDs / owner extension | Scenario and required result |
| --- | --- |
| TIME-01/02 | Event occurs before decision but receipt/availability afterward: earlier decision cannot use it. Verified intra-candle observation may qualify; missing intrabar evidence permits a qualifying completed-candle fallback only when the trader's predeclared policy explicitly allows it and availability/freshness checks pass; otherwise block the affected decision and record the reason. Later final OHLCV cannot masquerade as earlier live data. Clock-skew/quality failures remain explicit. |
| TIME-03 | News published before decision, added to ATLAS later: not live-known; publication-only archive stays distinct from historically verified/observed-live evidence. Editing article cannot retroactively change version visible to past decisions. Scheduled preannounced event differs from unexpected news. |
| TIME-04 | Dataset correction creates new checksummed version/experiment references, retains original results and review flags; simulator/code correction has distinct lineage. Shared objects avoid full per-experiment copies. |
| TIME-05, A/F | Historical development, historical OOS and prospective forward reports stay separate, displayed side by side with no combined success score or backdated Shadow result. Candidate nomination does not promote automatically; failures remain. |
| TIME-06/07, A/F | Specialist evaluated over multiple regimes/independent target occurrences where available; target/off-target opportunity/trade counts, costs/net outcomes, drawdown/risk, uncertainty and sample adequacy shown for candidates AND forward traders. Strong target specialist not globally rejected for off-target weakness; insufficient evidence never proves profitability. Detector reliability tested independently. |
| TIME-05–07, A/F | Historical/forward divergence investigation distinguishes regime-distribution shifts, detector errors, costs, data quality and possible overfit; hypotheses not facts. Untouched holdout/purged later windows resist repeated tuning/overlap leakage. Forward entry requires predeclared regime and actually available inputs; hindsight-only labels never authorize earlier entry. |
| TIME-07/08, B | Rich feasible context for executed/rejected/expired/no-fill opportunities includes BTC dominance/trend, both BTC/ETH relationships, altseason/breadth, liquidity/volatility and relative strength. Missing/quality/cost limitations explicit; original snapshot immutable. During open position, context changes create separate timestamped events, never replace original. Observed, assumed-reconstruction and retrospective classes remain distinct. |
| TIME-08 | Transition can block new entries but not retroactively close an open trade outside frozen exit policy; alternate regime exits/stops are isolated cost-aware Research/Shadow versions compatible with proposed PAPER-07. |
| TIME-09 | Missing/stale essential indicator prevents affected new entries and records missed reason; optional context gaps do not halt unrelated traders. Slow daily indicators need not match intraminute cadence. |
| DATA-01, TIME-09 | Shared BTC/ETH/context requirements across traders/runs deduplicate requests and reuse cache/local calculation. Provider-specific real weights/backoff/circuit policies govern all workers; unavailable source never reports fake freshness. Each external indicator has provider/local method, provenance, freshness, budget and limitations. |
| DATA-02/03, C | Initial backfill is a separately scheduled throttled/resumable pre-operational phase with bounded cost. Inventory assets/markets/timeframes/dates/indicators/news archives, missing/unsupported/quality gaps, progress/validation/versions; completeness only verified against declared scope. Later incremental data/repairs update same library without blocking core. |
| DATA-03/04, E | Selective partition retrieval/shared cache/object reuse reduce unnecessary downloads; measure latency/footprint/transfer/cost. New paid data source, storage upgrade, compute or chargeable service rejected/deferred without prior owner approval. Workload growth triggers budget control, never silent spend or zero-cost promise. |
| DATA-04 | Partial archive gap requests only missing/changed ranges, not default full redownload; verify continuity/timestamps/duplicates/integrity/version before publication. Interrupted jobs resume idempotently and retain incomplete/error state. |
| DATA-01/02/04, D | Heavy archive downloads/repairs/news enrichment/backtests/reports NEVER become synchronous prerequisites to core live monitoring/open-position tracking. Independent schedules/queues, bounded concurrency and resource reservations/equivalents keep CPU/memory/I/O/DB/network available; background yields before starvation, shared provider budgets remain respected. |
| DATA-04, D | Overlong core cycle cannot accumulate uncontrolled overlapping runs; dedup prevents duplicate Binance requests across workers, no budget multiplication. Observe run duration/deadline misses/backlog/freshness/budgets under load and derive objectives; illustrative 30 seconds is not an SLA. |
| DATA-02/04 | Rate pressure degrades lower-priority jobs first without bypassing limits. Provider outage/gap yields explicit degraded/unknown and preserves PAPER-08 no-fabricated-fill/no-retroactive-decision semantics. |

Evidence in future implementation: versions/fixture hashes, event/receipt/availability/decision clocks, report sections and sample denominators, coverage inventory, provider/resource/cost budgets, scheduling contention and recovery traces. No application tests, CI success, paid actions or G0 approval follow from this document.

## Future GOV-01 and live-data acceptance scenarios
Specification only; no application tests executed. [Canonical rules](03_DECISIONS.md#g0-live-data-operations-decisions--data-0508).

| Rule | Scenario / required outcome |
| --- | --- |
| GOV-01 | Another-chat handoff is inaccessible: report gap/request reference; do not claim inspection/completeness. |
| GOV-01 | Decision/clarification/correction/exception after last owner-confirmed submitted baseline appears exactly once in delta dispositions with evidence. |
| GOV-01 | Draft unsent prompt is not submitted, tool receipt not external confirmation, PR-open not merged; addenda/covered range and audit recorded durably. |
| DATA-05 | WS interruption: bounded reconnect/REST recovery under joint budgets; preserved event/receipt/availability evidence, no fabricated live-observation time. |
| DATA-05/08 | REST recovers past data: chronological/idempotent facts, no retroactive live signals or fictional paper fills. |
| DATA-06 | Slow core cycle: bounded overlap/backlog/deadlines and logged skipped/coalesced scanning; no invented 30-second SLA. |
| DATA-06 | Safe scanning snapshot coalescing retains all events required for open paper positions, fill ambiguity, replay and audit. |
| DATA-07 | Large-universe scan yields; Position Monitor delivers frozen-policy-relevant data without waiting; the owning trader evaluates/decides exits, and scanner remains bounded/adaptive. The same observation reaches other offices independently without waiting for position matching or trader analysis. |
| DATA-05/07 | Both paths/traders share central WS/REST/context/cache/provider authority: no duplicated Binance requests or multiplied limits. |
| DATA-08 | Degraded BTC context blocks dependent new entries but unrelated traders with independently valid essential inputs continue. |
| DATA-07/08 | Missing required price cannot create paper TP/SL/entry/exit fill; positions stay open with explicit monitoring gap/uncertainty. |
| DATA-08 | Healthy liveness but no recent trades: do not automatically declare feed broken. |
| DATA-06/07 | Historical backfill/news/reports/Research Lab pressure cannot synchronously block or starve monitor/core; shared API/resource controls still apply. |
| DATA-08 | Recovery retains order, unresolved ambiguity, provenance, reproducibility, state transition/outage/residual-gap logs; no guaranteed recovery during provider outage. |

Use future fixtures with source/symbol/stream/type failure domains, clock/availability evidence, idempotency keys, budgets/lag/queue metrics and monitoring-event retention; independent trader state preserved. Pending PR #8 TIME/DATA and PR #7 PAPER cases remain separate proposals and must survive later reconciliation.

## Reconciliation acceptance scenarios — INT-01–06
Documentation checks are distinct from future runtime tests. Runtime status for every case below: **NOT TESTED**. No CI success is asserted.

| Decision/dependency | Future acceptance condition |
| --- | --- |
| INT-04 / TIME-01/02/09 / DATA-05/08 | For the same unavailable intrabar input, policy A explicitly allows a qualifying completed-candle fallback and policy B prohibits it: only A may use that fallback after availability/freshness checks; B blocks with reason. Missing policy evidence also blocks. |
| INT-04 / TIME-01/02 | Live price and provisional intrabar value retain their original version/completion state; final H/L/C cannot appear before completion and actual availability. Event-before-decision but receipt/availability-after-decision is ineligible. |
| PAPER-08 / DATA-06/08 | Repeated recovery preserves required event sequences, deterministic chronology and idempotency for fills/closes/accounting/alerts; recovered facts never fabricate earlier live decisions. Unresolved order stays AMBIGUOUS with separate best/worst aggregates. |
| TIME-09 / DATA-07/08 | Stale essential regime input blocks only dependent entries; unrelated eligible traders continue. Open-position tracking retains gaps/uncertainty and frozen exits without invented fills. |
| DATA-01–08 / owner D/E | Background backfill/research/report pressure yields before core starvation; shared budgets still apply, monitoring does not wait for scanner and safe scanner coalescing never drops monitor/audit events. Objectives require later measurement. |
| TIME-05–08 / owner A/B/F | Historical development/OOS/forward stay separate, all opportunity contexts immutable, later observations append, specialist sample adequacy/detector evidence remains visible and nomination is not promotion. |
| INT-05 / GOV-01 | Two branch references to one handoff event count once; distinct submission/addendum/correction events remain distinct with source evidence. Clause changes require explicit semantic review. |
| INT-06 | Later PR merge updates current STATE and appends a new log/register event; the earlier OPEN observation is unchanged. Missing evidence is UNVERIFIED; material contradiction is BLOCKED. |

Documentary acceptance additionally requires 8 PAPER + 9 TIME + 8 DATA + GOV-01 + 6 INT records, owner A–G coverage, one canonical GOV-01 definition, preserved historical log/register events, and the independent future dashboard requirement. Exact evidence and dispositions are in the decision register's reconciliation matrix.

## Future secretarial acceptance and negative scenarios — G1-ARCH-01–11
All runtime/application/recovery/load/CI behavior below is **NOT TESTED** in this documentation task. These are future expectations, not executed fixtures or permission to implement.

| ID | Scenario and required evidence |
| --- | --- |
| G1-ARCH-01 | Slow archival/deep review stalls: minimally qualified committed observations continue to offices via Fast Lane without a second Binance collector or strategy decisions by either lane. |
| G1-ARCH-02 | Combined latency/backlog/resource/provider pressure causes bounded Slow yield/pause; resume uses measured hysteresis, with no hard-coded SLA and no unnecessary starvation of other office deliveries. |
| G1-ARCH-03 | Crash before commit, after commit/before delivery, after Fast consumption/before archive, after archive/before ack, and after ack/before reclaim: report actual durability boundary, retain required consumer state, no premature deletion, replay/ack/reclaim idempotently. |
| G1-ARCH-03 | Disk-full, corrupt record or finite capacity under paused Slow processing: explicit bounded-capacity/backpressure/alert/gap behavior under a later approved policy, never false continuous reception or zero-loss claim. Heavy pause is not itself reception shutdown while capacity permits. |
| G1-ARCH-04 | Two traders hold one symbol with different policies: one acquired observation reaches both logical secretaries; no shared mutable decisions, provider duplication, cross-trader blocking or secretary-generated fills. |
| G1-ARCH-05 | Delay position matching or trader evaluation: Scanner/other offices still receive the observation independently; higher priority is not a blocking fan-out gate. Owning trader alone makes hold/close/adjust/TP1/SL decisions; measure office lag/degradation. |
| G1-ARCH-05/06 | Rapid equal-price distinct events and potential TP/SL touches survive fan-out/replay despite safe Scanner snapshot aggregation; stable identity/order, not equal price, determines dedup. |
| G1-ARCH-06 | Live scan stage receives eligible provisional live observations; completed-candle stage receives bounded/scheduled final inputs. No provisional observation relabeled final; Scanner secretary generates no signal. |
| G1-ARCH-07 | Interrupt Forward/Shadow and delay historical jobs: retain real interruption/lag/missingness, no invented continuous coverage; historical development/OOS/forward stay separate and heavy jobs yield. |
| G1-ARCH-08 | Two frozen eligibility policies allow/prohibit fallback differently: only explicitly permitted fresh/available completed-candle fallback qualifies; missing essential evidence blocks with reason. Later deep-quality annotation cannot rewrite past knowledge. |
| G1-ARCH-09 | Restart restores durable Inbox/acks/open positions idempotently, reconciles authoritative state where applicable before dependent actions, reconnects eligible current service without historical catch-up, and resumes bounded Slow backlog. |
| G1-ARCH-10 | Recover candles but lack exact trade sequence: gap ledger tracks attempts/evidence/residual coverage, uses shared budget, yields to live needs and never clears an unverified scope or fabricates availability/order. |
| G1-ARCH-11 | Recovered paper TP/SL crossing is recorded as fact/uncertainty/gap, not historical fill or old live decision; owning trader receives current and recovered facts separately and applies predeclared recovery policy at actual availability. Ambiguity/scenario bounds persist. |
| G1-ARCH-11 future only | If separately authorized someday, reconnect must reconcile actual exchange orders/trades/fills/partial fills and protection status before execution-dependent truth updates; historical touch alone fails execution-proof acceptance. No real orders run here. |
| Merge deferral / GOV-01 | Source PRs/branches #6–#11 remain unchanged/open; main is not claimed to contain unmerged proposals; register preserves old observations and appends actual new lifecycle evidence. |

Documentation acceptance: verify all eleven canonical definitions and owner corrections, 12-item delta ledger (eleven decisions plus merge deferral), exact destinations/source conflicts, inherited PAPER/TIME/DATA/GOV/INT+A–G/dashboard/history, nine-file delta against #11 and thirteen-file cumulative documentation scope against main. Runtime acceptance remains NOT TESTED.

## Future progressive screening and readiness acceptance — G1-ARCH-12–20
Every application/runtime/cache/performance/recovery/CI scenario below is **NOT TESTED** by this documentation task. No executable tests or application code are added.

| Decision | Negative/acceptance scenario and required evidence |
| --- | --- |
| G1-ARCH-12 | Two traders have different preliminary filters for one symbol: central Scanner routes only qualifying candidates per trader, shares acquisition/computation when valid, secretary adds inputs and no Scanner/secretary opens a trade. |
| G1-ARCH-13 | Screening passes but a mandatory additional input is missing/stale/invalid: affected entry cannot pass. Preserve both manifest lists/versions, original context and reasons; optional evidence must not be mislabeled mandatory or vice versa. |
| G1-ARCH-14 | Candidate qualifies before READY: preparation begins at the actual earliest relevant stage and increases with development; no late result is backdated, duplicate acquisition or Fast/position starvation. |
| G1-ARCH-15 | Same symbol follows different per-trader stage graphs, including skip/reverse/exit edges where declared: transitions/states remain independent despite shared calculations; no invented compulsory sequence. |
| G1-ARCH-16 | Historical result is an eligible cache hit: return without heavy Slow queue waiting. Cache miss/stale/invalid result records actual analysis wait and cannot masquerade as ready. A delayed secretary/history request never blocks independent live fan-out. |
| G1-ARCH-16 | Queue/analysis delay, missing clock endpoint and concurrent office deliveries: measure ingestion/delivery, history service, readiness, strategy wait and active trader processing separately; no upstream wait charged to trader, zero substituted or parallel wait double-counting. |
| G1-ARCH-17 | Demotion/exit reduces unnecessary historical prefetch; another trader still needs shared work: preserve that consumer/result, raw archive/history and demand evidence. Refresh historical precomputation when policy/input context requires, not merely because LIVE/HISTORICAL label exists. |
| G1-ARCH-18 | Scanner READY occurs while mandatory evidence incomplete; available evidence is delivered progressively but entry blocks. Later completion/freshness invalidation updates decision-specific readiness; trader alone decides whether to act. |
| G1-ARCH-19 | Vary one of symbol/timeframe/definition/parameters/version/input provenance/finality/temporal context: incompatible computation cannot reuse a result. Exact match still requires consumer eligibility. Identical price alone is not identity; no shared mutable strategy decisions. |
| G1-ARCH-20 | LIVE label on stale data and HISTORICAL label on fast valid cache hit: classify planning separately from freshness/provenance. Preserve timestamps, validity, input range, completeness/version; no assumed latency. |
| G1-ARCH-20 | Declared WATCH -> READY condition becomes true during heavy-job cooldown: record the transition and adjust preparation priorities immediately; do not require BUILDING or delay live delivery/position protection. Cooldown affects unnecessary heavy scheduling only. |
| Cross-cutting | Inbox crash-safe commit/independent consumers, event ordering, selective recovery, budget throttling, policy-specific fallback and no backdated decisions/fills remain as specified by prior PAPER/TIME/DATA/INT and G1-ARCH-01–11 scenarios. Historical recovery ownership does not make eligible live restart wait for archival catch-up. |

Documentary acceptance requires nine unique new provisional decision definitions, complete owner subrequirements/cross-cutting constraints, a nine-item source/destination ledger, inherited decisions/addenda/dashboard/history preserved, and separate incremental/cumulative scope verification. Numeric targets, TTLs, thresholds and capacity promises remain unselected.

## Future shared-box acceptance and negative scenarios — G1-ARCH-21–28
All runtime/application/cache/concurrency/notification/recovery/performance/CI behaviors below are **NOT TESTED** in this documentation-only task. These are specifications, not executable tests or operational guarantees.

| Decision/check | Future scenario and required evidence |
| --- | --- |
| G1-ARCH-21 | Change one relevant input version/provenance/finality/temporal context or qualifying dependency event: stale/incompatible result cannot be reused. Unrelated event must follow declared rule rather than universal TTL. Consumer eligibility still required for technically valid reuse. |
| G1-ARCH-22 | Concurrent identical full-identity requests share one execution; one differing input/version/context does not. One subscriber cancels while another needs work: remaining execution/demand preserved, independently qualified deliveries and no shared strategy mutation. |
| G1-ARCH-23 | Market update/completed candle/correction invalidates the applicable active result while Slow archive is stalled: active eligibility revokes without archival waiting, original history/provenance/replay references remain, no premature Inbox reclaim. |
| G1-ARCH-24 | Replacement is slow/fails: expired old payload cannot remain active under UPDATING. Record reason/version/UNAVAILABLE as appropriate; activate only technically validated currently applicable replacement. Mandatory evidence cannot be bypassed via silent historical fallback. |
| G1-ARCH-25 | Logical manager processes dependencies/definitions/demand/result state and subscribed notifications without entries/exits or new independent provider collectors; resource pressure preserves Fast/positions. |
| G1-ARCH-26 | Secretary subscribes/changes scope/unsubscribes: receive authoritative current state and relevant pushes only. No indiscriminate broadcast or repeated per-trader polling/provider subscriptions. Preserve other subscribers' demand. |
| G1-ARCH-27 | Manager says technically invalid but secretary's manifest would otherwise pass: reject. Manager says VALID but mandatory decision evidence insufficient: secretary may reject/request more or refresh. Only trader decides hold/entry/exit. |
| G1-ARCH-28 | Expiration with no demand immediately loses active eligibility but does not trigger all-symbol updates; new position/READY/qualifying earlier-stage demand schedules by priority without forced BUILDING or slowing live fan-out. |
| Stale computation | Old execution A finishes after newer dependency/replacement B activation: A cannot overwrite B or restore expired eligibility; compare input/context/current revision, preserve audit lineage. |
| Subscription race / delayed notification | Invalidation occurs during initial snapshot handshake, notifications are duplicated/reordered or old VALID arrives after invalidation: no missed/current-invalid resurrection; detect/reconcile ordering and block uncertain eligibility. |
| Restart / missed messages | Manager/secretary disconnect or restore old checkpoint: reconcile authoritative current dependencies/states/subscriptions and ordered changes before affected use; no cache/old epoch silently claims VALID. Record gaps and actual available times. |
| Historical fallback | Predeclared policy allows/prohibits a distinct technically qualified historical context: enforce policy, freshness/availability and mandatory requirements; never reclassify current invalid data as valid or backdate fills/decisions. |
| Archive / replay / shared providers | Archive backlog/crash replay retains immutable result history and decision-critical events, idempotent progress and shared API budget authority. Internal indicator subscriptions do not duplicate Binance feeds; no universal TTL, numeric latency or capacity claim. |

Documentation acceptance: eight unique canonical definitions with all owner subrequirements; eight-item compatibility/destination ledger; explicit result-state/subscription model and eight example sequences; inherited G0/G1/A–G/dashboard/history preserved; nine incremental/thirteen cumulative Markdown files only. Runtime/CI/performance evidence not inferred from documentary checks.


## G1-ARCH-29–44 proposed documentary and future executable acceptance

Documentation checks: 16 unique canonical decisions numbered 29–44, all C and provisional; sixteen-row inherited compatibility/destination matrix; full conceptual catalog/dependency/subscription/failure/quality/warm-up/correction/recovery/observability models; inherited G0/G1/A–G and dashboard preserved; no physical technology, numerical SLA, code or merge.

**Future negative/positive tests — NOT TESTED:** dependency cycle rejection; unrelated indicator remains valid on scoped correction; definition version migration and PIT preservation; two subscribers with one cancellation; high-priority position event during Slow backlog; delayed computation fencing; missed/duplicate/reordered notifications; reconnect snapshot gap; bounded retries and retry storm avoidance; warm-up insufficient; mandatory READY evidence missing; historical correction and immutable prior evidence; restart/Inbox ACK safety; Slow secretary cannot block others; overlapping latency attribution and clock skew; dormant demand not counted as failure; alert dedupe/escalation/recovery. Executable CI, runtime, performance, concurrency, notification, recovery and provider budgets remain NOT TESTED until separately authorized.