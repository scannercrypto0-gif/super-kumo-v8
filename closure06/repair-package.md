# Accelerated Closure 06 | Repair package

Baseline 894738437139857be5ee43b90223567b5296c867. This package uses one repair queue ordered by contracts and source authority. The [frozen decision matrix](../atlas-closure-05/pr-decision-ledger.json) remains the path-level comparison for all 123 original open PRs. Newly created review vehicles are tracked separately and do not reclassify the original PRs as merged or closed.

## Order and exact outstanding disposition

| Order | PR | Repair disposition | Remaining work and stop condition |
| --- | --- | --- | --- |
| R1 native read seam | #286 | Prepared partial review unit | Use d072544 pinned observer, durable replay callback and Factory read. No archive runner, collector or custody changes from the broader #286 head. The existing legacy journal still rejects unknown kinds without the explicitly supplied callback. |
| R1 native read seam | #289 | Prepared partial review unit | Use exact forward_evidence.py. Legacy CLI and combined archive/forward workflow stay outside native read seam. |
| R2 authority/custody | #144 | Held outside R1 | Whole head conflicts at .gitattributes and brings 94 absent paths. Scope only an explicitly needed observation authority contract. Require a named producer/consumer and proof that MAIN and the owner runtime retain a consistent source policy. |
| R2 authority/custody | #195 | Held outside R1 | Exact head is a fixture-engine pin on a separate DEV branch. Four changed paths are absent in main; conflict at inherited .gitattributes. Close only once a current native consumer adopts or supersedes the fixture contract with evidence. |
| R2 authority/custody | #226 | Held outside R1 | Main diverges in aql_core_backbone_local_v1.py and aql_native_binance_zip_v1.py. Carry neither broad history nor original data. Split only the native parser/custody change after proving current UTC microsecond boundaries against generated fixtures. |
| R3 transport | #305 | Depends on R1 and scope split | Standalone #305 transport is pinned in the owner runtime. Its draft includes feed/pilot/session modules outside the one-channel release. Separate socket framing/quota from REST/probe harness without changing approved egress or retry limits. |
| R3 transport | #271 | Depends on R1 and R3/R4 | Whole head conflicts in Factory E result-store, historical projection and Generic Secretary bridge. Existing diagnostic Audit and owner runtime are reused. Extract only operators with a closed, importable dependency set. No runtime mutation. |
| R4 immutable results and reporting | #267 | Held for contract reconciliation | Result-store, Factory H research package and historical projection collide with Generic H. Match schema/namespace and immutable attempt/result keys before identifying a minimal adapter. #310/#311 are Factory E topic landings. |
| R4 immutable results and reporting | #292 | Held for fixture/source boundary | 24 absent paths include native-current source/evaluation fixtures. Admit only clearly generated fixture inputs with a distinct identity and a declared observer/report contract. No original market input. |
| R4 immutable results and reporting | #312 | Blocked on #267/#297 contract | Two own paths remain outside main. The full reporter imports atlas_operator_readback, atlas_strategy_operations and research_capacity_scale.runtime absent from the native read unit. Separate the daily freshness projector once the operator API is reviewed. |
| R4 immutable results and reporting | #309 | Retrospective only | Ordered Scanner census records unknown contemporaneous availability and lacks prospective parent authority. Preserve offline evidence without wiring it into live or Paper decisions. |
| R5 native acceptance residuals | #287 | CI-only residual in #317 | Exact g1-foundation-closeout.yml proposed. Landed foundation files are untouched. |
| R5 native acceptance residuals | #308 | CI-only residual in #317 | Both exact workflows proposed. Existing pinned Discoverer, Factory and Scanner fixture evidence is reused. |
| R5 native acceptance residuals | #288 | Simulator CI in #317, operational promotion deferred | Exact g3-paper-sim.yml proposed. Four promotion/dashboard files have a distinct authorization surface and cannot be treated as delivered or authorized. Landed simulator and previous native upstream fixture evidence are reused. |

R1 and C01 touch disjoint paths. R1 restores the replay hook missing from the merged DurableG2Bridge and imports the existing prospective observer, forward-window projection and Factory consumer into one native chain; no new strategy, database, API, host job or authority grant. Test injects generated BTCUSDT closes, uses native journal/store/Scanner, reopens G2 read-only, and compares stable Factory and forward views. Fixture status remains SYNTHETIC_TESTED and historical PIT NOT_ATTESTED. Rollback is an approved revert of the six selected paths on the exact reviewed predecessor.

## Ten-stage update

| Stage | Verdict | Change in this package |
| --- | --- | --- |
| Foundation/governance | ENGINEERING_ONLY | Active protected-main rule retained. #287 CI residual is reviewed in #317 |
| Real-time Binance | OPEN | R1 supplies native prospective read building blocks; transport/profile split still separate |
| Historical publisher archive | ENGINEERING_ONLY | C01 published for native QA review. Publisher execution out of scope |
| Core custody/replay | ENGINEERING_ONLY | R1 covers generated input and read-only reopen. #144/#226 authority/custody stack separate |
| Scanner/Discoverer/Secretary | ENGINEERING_ONLY | R1 Scanner evidence path. Factory leaves orders disabled and Secretary unenqueued |
| Factory/Lab | ENGINEERING_ONLY | R1 read-only Factory census. Immutable experiment registry/renderer pending |
| Isolated Paper | ENGINEERING_ONLY | #314 simulator remains main; #317 proposes offline CI only |
| Scientific PIT/OOS | NOT_DUE | New generated evidence is not scientific evidence |
| Integration/reporting/recovery | OPEN | R1 reusable read boundary. #267/#312 reporting unresolved |
| Sustained research | OPEN | Reuses owner delivery of nine finals/rollover. No new operator evidence; real recovery and daily continuity not independently attested here |

