# ATLAS integrated repair | Post-C01 release dossier

Pinned main `8b7f28f27cd960bbc201187f8d4b8390648f5ed2`. C01 #315 is merged; #304 remains open. C01 added only the historical source QA workflow. None of the fourteen original repair PRs or the three repair vehicles has merged. [PM scope](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-6946781378) · [Original path-level ledger](https://github.com/scannercrypto0-gif/super-kumo-v8/blob/c2d130b6b9db94b680fcbe99a815a5c7d22c2250/closure06/repair-ledger.json)

## Hosted review units

| Unit | Exact head | Exact tree | Native scope |
| --- | --- | --- | --- |
| [#316](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/316) | `b73a028f01d2d97025ce264de62750c216f07bf2` | `feaf9cc9b8e27ca9754842158a96ac0c299f3bdb` | Six paths. Core journal callback, prospective observer, Scanner→Factory readback and forward synthetic evidence |
| [#317](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/317) | `872bf1823cfb41c8185ad6199caafb9768780802` | `a79f0363f72e9931a413cb519330e270a8b277a3` | Four exact offline CI workflows for code already merged through #314 |
| [#318](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/318) | `0cf6428826ac990a918df7843359db8e13c5ce62` | `4144b523afde5fe8e7e889f7bbb1830cc04a2fce` | Six paths. Native daily ZIP parser, saved daily-health reader, single-channel read-only wire/diagnostics and focused tests |

#316 and #317 were behind main after C01. Both were rebased onto current main using GitHub's PR branch rebase, with every prior reviewed path/blob/mode preserved. The current three reviews have disjoint paths. [Composition proof](candidate-proof.json) records the full path sets, exact candidate trees and scratch composite `2dcc3111a1cbb12f532b6d4b6c357c695245e7ab`. Nine generated/mocked tests passed on the scratch composition. The composition is an integration proof, not a fourth release vehicle.

### Windows throughput finding

The original #317 Windows job failed the exact WP03 threshold at 100 bars in 22.972 s, or 4.353 bars/s. The historical baseline and C01 both passed that same test. #317 only added CI workflows, so its patch did not modify the ingest implementation or threshold. Re-ran the failed original Windows job only; attempt 2 succeeded. The rebased #317's new protected-main Windows and Ubuntu checks also passed. Runtime contention is plausible but unverified; a repeatable code regression was not established. The red result is retained and the >5 bars/s threshold is unchanged. [Original failure and attempt history](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/44073105253/attempts/1) · [Successful rerun](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/44073105253/attempts/2)

## Fourteen original dispositions

| Original | Current coverage | Remaining release boundary |
| --- | --- | --- |
| #144 | Deferred authority/custody package | Broad authority/evidence stack and historical private artifacts. Need a scoped owner-approved witness and a named main consumer; no copy of private reports or authorization changes |
| #195 | Deferred separate DEV fixture | A pinned historical Factory test seam without its DEV engine/custody parent. Requires exact producer plus scoped generated fixture, with original research owner approval if real evaluation is proposed |
| #226 | Partial in #318 | Exact pinned parser now validates UTC daily filename, ms/µs source endpoints and only then converts to ms. Rejected one-unit error on generated days. Broader native custody intake and original data remain separate |
| #267 | Deferred immutable experiment contract | Factory E result-store and historical projection conflict with Generic H. Requires selection of a canonical Experiment/Attempt identity and read/write boundary before adopting producer/store code |
| #271 | Partial in #316/#318 | Read seam and audited phase/reset diagnostic extracted. Full supervisor, private config and market worker remain out of main. No transition of owner Windows or expansion of receive budget |
| #286 | Partial in #316 | Native prospective observer and Factory view. April archive acquisition and collector/custody changes remain outside |
| #287 | Exact CI residual in #317 | Landed production/test paths are already in main. Native review and exact approval required before deciding source PR closure |
| #288 | Partial offline CI in #317 | Exact simulator workflow. Promotion/dashboard and authority changes remain separate |
| #289 | Partial in #316 | Native forward projector plus readback. Archive-coupled CLI and combined workflow remain separate |
| #292 | Deferred provenance-dependent gateway | Existing 24-path branch includes bundled native-current source/manifest/evaluation fixtures. Establish witness and fixture classification before releasing gateway on reviewed inputs |
| #305 | Partial in #318 | Single BTCUSDT Spot 15m public framing and private-detail-free fault context on mocked tests. No REST or probe, no live session/quota orchestration changes |
| #308 | Exact CI residual in #317 | Both missing workflows restored in review; custody implementation already landed |
| #309 | Deferred retrospective parent contract | Native verifier imports market_cycle and requires immutable Factory attempt/native-plan/decision-census chain not on main. Known-at UNKNOWN and Core source blocked. Never adapt it as contemporaneous output |
| #312 | Partial in #318 | Pinned daily-only snapshot projection with independent source-age and scheduler-age. Full Factory operator still depends on #267/#297 saved batch imports |

No external-market call enters the new fixture suites. #318 returns only named status, clock and source-day fields from the pinned snapshot, and keeps authority NONE. The wire module requires exact endpoint, TLS hostname validation and existing bounded frame logic. It exposes no REST entry point and none of these modules is deployed. The standalone daily reader does not enable acquisition or replace the installed task.

## Ten-stage readback

| Stage | State | Exit still required |
| --- | --- | --- |
| Foundation/governance | ENGINEERING_ONLY | G0 decision remains separate. #317 CI review |
| Real-time Binance | OPEN | #318 wire is a fixture-tested building block. Real route, quota and service integration remain distinct |
| Historical publisher | ENGINEERING_ONLY | C01 native QA in main. #318 parser and saved health still draft. Real scheduled receipts require separate verification |
| Core custody/replay | ENGINEERING_ONLY | #316 prospective read on native fixtures. Authoritative full custody/rights remain separate |
| Scanner/Discoverer/Secretary | ENGINEERING_ONLY | #316 native evidence path. No authority or dispatch |
| Factory/Lab | ENGINEERING_ONLY | #316 read-only Factory view. #267 store boundary unresolved |
| Isolated Paper | ENGINEERING_ONLY | Main simulator and #317 offline CI. No operation/activation |
| Scientific PIT/OOS | NOT_DUE | Independent first-release/custody witness and sealed protocol |
| Integration/reporting/recovery | OPEN | #318 readback boundary plus #316 fixtures. Full #312 operator/capacity path unresolved |
| Sustained research-only operation | OPEN | Existing owner evidence reused. No new host or publisher testimony in this package |

Protected main remains active, and production merge requires the terminal independent Audit, native non-author approval for each exact head, green required CI on the current base and a separate owner decision. Planned order #316 → #318 → #317 is a review sequence. If approved later, each new main requires strict revalidation of the next candidate and any changed-head approval. Rollback by reviewed reverse-order reverts with the path scopes above; never touch stored research data or task definitions.
