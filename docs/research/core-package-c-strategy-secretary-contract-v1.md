# ATLAS Quant Lab — Core Package C strategy-level Secretary contract (research-only v1)

Owner authorization [Core #226/6650417711](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/226#issuecomment-6650417711), **provisional**. This is **NEW Core C Draft PR #261** stacked on **OPEN, unmerged Core B Draft #226**. It does not alter B #226, Factory #255, Scanner B #257, frozen RAW #211, Scanner Engine #227, Work Strategy #235 or Discoverer #230. No G0, merge, holdout, operational Paper or trading.

## Purpose / boundary

Prevent three different events being mistaken for a single authorization:

1. **SOURCE_ACK** — actual Core B `aql.core.secretary-offline-ack.v1` receipt, independently verified against the **persisted** B SQLite `distribution_outbox` payload and append-only hash-linked `distribution_events` trace. Only confirms consumer-reported source custody handoff.
2. **STRATEGY_APPROVAL** — separate explicit, SHA-sealed TEST_ONLY policy action; never inferred from SOURCE_ACK, Scanner synthetic SELECTED, or price availability. The internal research-only Core route currently requires `aql.scanner.c.strategy-approval.v1` projected approval and a `aql.scanner.native15m-policy.v1` Frozen policy root. **This projected receipt schema is not interchangeable with actual Scanner C #259's `aql.scanner-c.strategy-approval.v1` Frozen receipt.** The latter is separately verified by the read-only compatibility seam below. Neither source constitutes signed real-world governance or commercial trading approval; SHA256 seals prove self-integrity, not issuer authentication.
3. **CONSUMER_ACK** — separate explicit `aql.factory.c.strategy-consumer-ack.v1` research consumer receipt (provisional Core internal test interface), tied to the exact route/request/policy approval/nomination/warehouse/query/source parent chain, with Paper and trading authority `NONE`. **Factory C #260 has its own provisional different wire schema**; no equivalence/production connection is inferred. A source ACK is not a strategy consumer ACK.

The authenticated historical availability and market-wide opportunity universe are still **NOT_ATTESTED**. `historical_known_at_ms = null`, `RETROSPECTIVE_NON_PIT`, `operational_scanner_status = UNKNOWN`, Work235 operational 15m = `NOT_CONNECTED_15M_UNSUPPORTED`, no actual order/position/fill.

## Core-owned durable strategy route (internal software interface)

Code: `research_wp_r0/aql_core_c_strategy_secretary_route_v1.py`.

The existing Core B **source** Secretary outbox remains untouched. A **separate**, SQLite/WAL/FULL-synchronous, versioned `c_strategy_routes` table and append-only hash-linked `c_strategy_events` track only the Core C **strategy** route. The source outbox and the strategy route are independently verified on read/restart. No message is sent to any network, exchange or broker.

Main API:

```python
from research_wp_r0.aql_core_c_strategy_secretary_route_v1 import (
    make_strategy_route_request, enqueue_strategy_route,
    approve_strategy_route, acknowledge_strategy_consumer,
    retry_strategy_route, strategy_route_snapshot, strategy_route_trace,
)
# Inputs MUST be actual independently SHA-verified Core B:
#   identity_map: aql.core.historical-dual-query-identity-map.v1
#   warehouse: aql.core.local-history-warehouse.v1, RAW COMMITTED
#   native_source_nomination: real Core B AQL-SCANNER-V1 UNKNOWN receipt
#   source_ack: actual B ACK, DB verified; Scanner B policy: Frozen receipt
request = make_strategy_route_request(
    identity_map=identity_map, warehouse=warehouse,
    nomination=native_source_nomination, source_ack=source_ack,
    strategy_policy_receipt=native15m_policy_receipt,
    strategy_id=policy_id, strategy_version=policy_version,
    config_digest=policy_config_digest,
    strategy_definition_digest=policy_definition_digest,
    expires_at_ms=research_route_expiry_ms,
)
pending = enqueue_strategy_route(
    core_private_root, request, identity_map, warehouse,
    native_source_nomination, source_ack, native15m_policy_receipt,
    approval=None, now_ms=research_clock_ms, route_id=stable_route_key,
)
assert pending["state"] == "WAIT_APPROVAL"
# Only an explicitly supplied and separately SHA-verified TEST_ONLY
# approval may move a route to PENDING_CONSUMER. Core never manufactures one.
pending = approve_strategy_route(
    core_private_root, stable_route_key, external_verified_test_only_approval,
    now_ms=research_clock_ms,
)
# Only an actual research consumer may later create its own signed ACK.
# No auto ACK, no auto Paper activation. Any wrong/expired parent fails closed.
```

The Core-owned internal test-only approval projection is a **provisional** state-machine test contract pending the canonical Scanner C / Factory C owner handshake. No caller should fabricate these receipts to activate the Lab. A SHA-only receipt is not identity authentication.

**State transitions:** `WAIT_APPROVAL -> PENDING_CONSUMER -> ACKED_CONSUMER`, retry `PENDING_CONSUMER -> RETRY -> QUARANTINED`, and expiry `* -> EXPIRED` (mutable state on explicit transition, read-only state projection otherwise). Missing approval stays WAIT. Parent and route collisions fail closed; one request SHA can have at most one route id; idempotent replays do not append events. Bounded retry respects backoff. Terminal quarantine/expiry cannot silently ACK. A formerly ACKed route retains historical ledger state but `route_ready_for_isolated_lab=False` once policy/route has expired. All receipts remain TEST_ONLY, authority NONE.

**Preserved source/version parent fields:**
`strategy_id`, `strategy_version`, `config_digest`, `strategy_definition_digest`, `symbol`, `timeframe=15m`, `source_zip_sha256`, `manifest_integrity_sha256`, `warehouse_receipt_sha256`, `identity_map_sha256`, **distinct** `core_245_price_query_sha256` vs `core_253_query_local_sha256`, `scanner_nomination_sha256` (legacy native AQL-SCANNER-V1), `source_ack_sha256`, `policy_receipt_sha256`, explicit `approval_sha256`, optional `consumer_ack_sha256`, `cutoff_ms`, `expires_at_ms`, NULL historical known-at, NONE authority. Scanner B native policy is independently SHA-sealed and its `config_digest` is recomputed; Core B source ACK is verified against actual outbox/trace on every read.

### Canonical Core C internal TEST_ONLY examples (metadata only, not evidence)

Valid transition example: an independently verified same-source Core B warehouse/query/nomination with a genuine source outbox ACK, matched Scanner native15m policy ID/version/config and explicit separate TEST_ONLY research approval -> `PENDING_CONSUMER`; a **separately supplied** matching consumer ACK -> `ACKED_CONSUMER`. Even this gives **no operational Paper** authority, and a TEST_ONLY receipt is not a real-world G0 approval.

Invalid example: `source_ack_sha256` supplied where `approval_sha256` belongs; or policy's `config_digest` changed; or Core245 native SHA reused as Core253 local SHA; or expired approval; or a previously-ACKED SOURCE event used for consumer ACK. All must yield WAIT, refusal or quarantine — never a silently approved strategy.

## Canonical Scanner C #259 verified separately; source lineage stays WAIT

Actual Scanner owner Code: `tools/scanner_strategy_c/approval_route.py` (frozen #259 `72ea87fc22a45df43fc4a990ade176837e7c42af`). Its **true owner schemas** are:

- `aql.scanner-c.strategy-approval.v1`, `{payload, sha256}`, **explicit** `APPROVE_TEST_ONLY`/`DENY_TEST_ONLY`, governance policy ID/approver ID/nonce, `scope=SYNTHETIC_OFFLINE_ENGINEERING_ONLY`; **no authenticated issuer timestamp/expiry**, no PIT authority.
- `aql.scanner-c.strategy-route-request.v1`, `{payload,sha256}`, binds the strategy ID/version, native15m policy `config_digest`, Work235 definition/DNA, actual Scanner run/nomination SHA, synthetic raw/manifest/universe/denominator/census, declared Core B custody/ZIP/245/253 SHA pins, `strategy_secretary_status=NOT_ENQUEUED`, 0 orders, trading NONE.

Core Code: `research_wp_r0/aql_core_c_scanner_reconciliation_v1.py::reconcile_scanner_c_candidate`. It calls **Scanner C's own existing re-computation/verifier**, exact Work235 + Scanner B policy validation, checks actual source Core B outbox durable ACK and immutable Core dual-query parent, and returns SHA-sealed `aql.core.c.scanner-source-reconciliation.v1` with **WAIT** and exact immutable parent SHAs / blocking conditions. It **never** converts the synthetic Scanner raw JSON `source_raw_sha256` into authentic original-format native ZIP `source_zip_sha256`, nor Scanner synthetic SELECTED into historical operational SELECTED.

If source/policy/nomination/query parents mismatch, reasons explicitly record `SCANNER_DECLARED_CORE_ZIP_PARENT_DRIFT`, `SCANNER_SYMBOL_NOT_CORE_ORIGINAL`, `SCANNER_CUTOFF_NOT_CORE_ORIGINAL`, etc.; **even when all declared hashes match**, the actual independent original→synthetic source bridge is still absent (`SCANNER_SYNTHETIC_RAW_TO_CORE_ZIP_NOT_ATTESTED`). No Core C strategy-level route is enqueued by this reconciliation method; no factory consumer ACK, no Lab activation or Paper authority is minted.

Canonical positive example of a **safe reconciliation**, not a strategy approval:

```json
{
  "schema": "aql.core.c.scanner-source-reconciliation.v1",
  "decision": "WAIT",
  "blocking_conditions": ["SCANNER_SYNTHETIC_RAW_TO_CORE_ZIP_NOT_ATTESTED"],
  "strategy_secretary_status": "NOT_ENQUEUED",
  "historical_known_at_ms": null,
  "trading_authority": "NONE",
  "orders_created": 0
}
```

All other required parent SHA and denomination fields are present in the actual receipt. This example is explanatory; never treat it as a genuine executed receipt. Invalid scanner route with `source_secretary_ack_is_strategy_approval=true`, altered inner signed nomination, modified config or a forged source outbox ACK is **rejected**, not transformed to a valid strategy.

**Factory #260 compatibility limitation:** Factory C provisional `artifact_sha256` receipt schemas are currently **different** from Scanner C's frozen `{payload,sha256}` and Core C's sealed route shape. No claimed conversion/field alias; Factory owner must integrate actual Scanner/ Core owner schemas once a real same-source strategy proof exists. A WAIT-only reconciliation receipt can be consumed as a hard non-activation guard. The ONE combined C integration gate is led by Factory after all owners reconcile, not by repeating B's previously accepted 96 focused executions.

## Reproducible focused new-delta tests and pins

Dedicated `.github/workflows/aql-core-c-strategy-secretary-focused.yml` checks out C branch and read-only exact frozen code SHA pins:
- Core B #226 `5cde010bac4a087bbed9fbf0791c56fb2e41aa2b` (base).
- RAW #211 `7d97b09c0c6ee2650a61d523acb8d8c771a99c46`; native Scanner Engine #227 `b9c9ff8602e79c534402f44bce83c56ec2fa6bb9`.
- Work235 `6acbcc7fc243b132f58170df4c6469bbf7f4eff8`, Scanner B #257 `30c37ae56851488b882998c7fa0085ec51dbfc92`, Scanner C #259 `72ea87fc22a45df43fc4a990ade176837e7c42af`, Factory B #255 `e66ac39a6443853c60463f7bd5bfaf590bb125a6` (transitive only).

Only existing test-only fixtures; **no** owner-private Feb/Aug ZIP/CHECKSUM, OHLCV, holdout or 106 old reports used. Two focused new C tests: `test_aql_core_c_strategy_secretary_route_v1.py` (13) + `test_aql_core_c_scanner_reconciliation_v1.py` (6) on Python3.11/3.12/3.13. Parent C software tests are separate from the **future Factory-led ONE cross-component C gate** and independent Audit. The exact CI run ID and final commit SHA will be recorded at handoff; do not infer overall G0 or scientific validity from unit passing.

**Open blockers:** Scanner #259 synthetic source/nomination is not independently matched to Core B original-format ZIP in provenance or decision cutoff; Scanner C approval lacks an independent approved Paper registry, trusted issuer timestamp and historical PIT; Factory #260 provisional wire schema differs from Scanner C actual and Core C. New authentic 2024 15m monthly ZIP+publisher CHECKSUM remains `SOURCE_UNAVAILABLE` for further genuine E2E. No G0, merging, broker, trading, paid infrastructure, or new Work order.
