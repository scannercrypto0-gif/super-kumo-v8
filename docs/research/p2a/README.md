# P2-A public native-15m intake and offline handoff driver

Authority: #77/6598843001. New Work-owned namespace only, separate from Core's
P2HistoricalOpportunityV1 and Factory's paired Lab consumer. Broad scientific
evaluation is deferred; focused functional tests are included.

## Explicit dependency, not a merge

New Draft is stacked on Factory #209 pin
47558bea22af5480aa84148fd22bf2890bbe22ae to reuse ONLY
research_wp_r0/aql_b1_market_research.py:parse_archive (strict 12-column native
archive validation). No old B1 runner, P0/Jan P1, Claude #219, strategy evaluator,
fill engine, or original branch is changed/invoked. Main at intake remains
dbc191df72f4b4d1ebb7d490926dcad4325dac12. This stack is not main acceptance.

## Frozen development selection

Committed development-plan.json declares two noncontiguous complete months:
2024-02-01..2024-03-01 exclusive and 2024-08-01..2024-09-01 exclusive,
BINANCE SPOT BTCUSDT native 15m UTC. Its byte SHA256 is
e21a6614317de784f4ba0ffc4ed67e4df5157dd5080ef4eb76aa9f5542af7060.
Declaration timestamp is BEFORE P2 intake, not retroactive preregistration of
strategy performance. Archive/member/CHECKSUM pins come from the previously
retained original B1 lock. Prior descriptive B1 exposure is disclosed: these
are DEVELOPMENT data, never pristine OOS. No Jan one-week study is reused.

Source URI prefix:
https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/15m/
Provider documentation: https://github.com/binance/binance-public-data
Dataset terms:
https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md
At inspection: Binance Vision Dataset Terms v1.0, updated2026-08-26,
CC BY-NC-SA4.0; attribution Binance Vision / Binance Public Data.
Use is personal noncommercial nonproduction offline research only. No claim
of commercial use, live execution, signal-distribution or enterprise rights.
Private artifacts retain attribution/license. License/provenance metadata is
not a legal certification or historical publisher-availability attestation.

Native2023/2024 millisecond archives only in this adapter. Provider documents
microsecond Spot timestamps from2025; never guess/auto-relabel units. The
reserved2025 holdout is not fetched or parsed by this version.

## Sealed period and embargo

November2025 is fixed SEALED_NO_FETCH_NO_EVALUATION. Code rejects any modified
holdout boundary, HOLDOUT phase, or period crossing its >=72h embargo. It also
requires >=72h between development intervals. No CLI flag opens the holdout.
Separate future owner authorization and bounded contract/code work would be
required before holdout access. No global claim that nobody has seen these
public data: only unfetched/unevaluated BY THIS DRIVER. Only the two declared
development datasets are handed off; source gaps between them are not bridged.

## Execute locally / source acquisition

```sh
python -m unittest -v tests.test_aql_p2a_public_intake
python -m research_wp_r0.aql_p2a_public_intake \
  --plan docs/research/p2a/development-plan.json \
  --plan-sha256 e21a6614317de784f4ba0ffc4ed67e4df5157dd5080ef4eb76aa9f5542af7060 \
  --cache /private/original-monthly-cache \
  --cache-receipt /private/original-monthly-cache/retrieval.json \
  --output /private/NEW-p2a-intake \
  --verified-at-utc ACTUAL_UTC_Z_TIMESTAMP \
  --code-sha FULL_P2A_HEAD_SHA
```

The existing cached original public archives avoid redundant downloads. Without
a retained acquisition receipt, fetch time is UNKNOWN, never filesystem mtime
or bar close. A retained receipt is checked against URLs/hash/size/status but
is still a local reported clock. Historical publication/known-at remains null.
--fetch optionally allows only missing predeclared pinned public archive and
CHECKSUM files: bounded30s/32MiB GET, no credentials, proxy, redirect, retries,
REST market recovery, alternate host or geography bypass. Denied/failed egress
is terminal for further network windows and is retained as a precise blocker.
This task's real execution uses cached sources; TEST_ONLY mock fetch cases do
not prove current network availability.

Changes to raw/archive/member/checksum bytes fail against frozen pins; no silent
correction overwrite. New legitimate corrections require a new plan/version.
Duplicates/gaps/interval/12-column/OHLCV/nonfinite/CRC errors reject the dataset.
Unavailable/invalid windows report BLOCKED_SOURCE with observed/gap counts null,
not zero-valued fake successful coverage. A partial intake is not usable by the
downstream read_validated_index contract. Original cache is read-only; output
is a NEW private directory with mode600 files, raw copies and hash manifest.

## Published handoff contract

Manifest schema aql.p2a-data-intake-manifest.v1 binds frozen plan, index hash,
source hashes, per-window quality/coverage and access receipts. bars.jsonl
schema aql.p2-historical-bar-index.v1 has:

- dataset_id/version; bar_id BINANCE:SPOT:BTCUSDT:15m:open_ms; exchange,market,symbol;
- UTC integer open_ms/close_ms and interval_ms900000;
- decimal STRING open/high/low/close/volume (no floating normalization of RAW);
- source_archive_sha256/source_member_sha256/source_version; per-record bar_sha256;
- finality ARCHIVED_CLOSED_INTERVAL,is_final=true: validates retrospective closed
  intervals, NOT an original live-finality/receipt assertion;
- historical_known_at_ms/historical_receipt_ms/historical_publication_ms=null;
  observation_lower_bound_ms=close+1 is only a mathematical lower bound;
- availability_mode RETROSPECTIVE_NON_PIT; correction generation UNKNOWN_NOT_ATTESTED,
  correction_parent=null (null means missing history, not proof of no corrections).

```python
from research_wp_r0.aql_p2a_public_intake import read_validated_index, asof_features
plan, manifest, rows = read_validated_index(
    '/private/p2a-intake', expected_manifest_sha256='INDEPENDENTLY_RETAINED_FILE_SHA256')
prefix = asof_features(rows, plan,
    dataset_id='BINANCE-SPOT-BTCUSDT-15M-2024-02-DEV-v1', cutoff_ms=1706763600000)
```

read_validated_index requires an independently retained transport digest, verifies
manifest/status/plan/index/record hashes; no default trust in arbitrary input.
asof_features uses completed bars strictly before cutoff, restricted to a declared
dataset and its native grid. It is an event-time retrospective prefix, NOT PIT.
Core owns actual feature/regime/direction evidence, opportunity scheduling and
frozen BASE/SHADOW proof; Factory owns outcomes/pairs. No duplicate producer or
Lab consumer is implemented here. The exact Core P2HistoricalOpportunityV1 schema
is pending, so interface mapping/integration remains an explicit dependency.

## What the offline driver actually does

Frozen plan -> optional lawful acquisition OR cached original bytes -> strict
source validation -> deterministic versioned bar index -> per-window coverage
and simple market-context diagnostics -> digest-bound handoff to Core/Factory.
Dataset-specific 15m close-log-return standard deviation and observed price range
describe selected development periods only; regime labels remain null absent
Core proof. These diagnostics are not candidate evaluation, alpha or a backtest.

No real strategy candidates have been registered or executed in this driver.
Manifest explicitly emits base_shadow_comparison=NOT_EXECUTED_NO_FROZEN_BASE_SHADOW_PROOF,
opportunities=null,comparative_alpha=null,market_only_opportunity_probe=NOT_RUN.
Core schema/schedules + real prespecified arms and Factory paired consumer are
prerequisites for a later separately scoped integration, not replaced by test
strategies or arbitrary Boolean approval switches. New actual data intake is a
useful source-backed result; it is not a completed paired strategy comparison.

CI covers only new TEST_ONLY fixtures and injected transport errors; raw sources,
private bar indices, old suites and owner January/P1 data stay out of Git/CI.
Final full SHA, actual CI, observed coverage/context values and private artifact
digests are recorded in the execution delivery after pinning this code.
No merge, G0, trading, deployment, Paper/Live, final holdout or broad audit here.
