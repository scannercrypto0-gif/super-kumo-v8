# ATLAS Package C — Scanner/Strategy shared native15m contract

**Separate owner C branch**, not a modification or merge of Bundle B #257, frozen Work #235 or Scanner #227. Exact upstream refs at authorization: #235 `6acbcc7fc243b132f58170df4c6469bbf7f4eff8`, #257 `30c37ae56851488b882998c7fa0085ec51dbfc92`, Core #226 `5cde010bac4a087bbed9fbf0791c56fb2e41aa2b`, Factory #255 `e66ac39a6443853c60463f7bd5bfaf590bb125a6`. All Draft OPEN/UNMERGED. Local imports need those owner modules staged into the same *disposable* integration checkout; never imply upstream branches merged.

## One shared strategy identity

`approval_route.py` defines two SHA-sealed immutable envelopes with Work #235 canonical `Frozen.build`/restore semantics.

`aql.scanner-c.strategy-approval.v1`:
- Identical `strategy_id, strategy_version, config_digest` for a validated separate **native 15m** policy; source Work235 spec hash/config, StrategyDefinition digest and DNA digest, market and native timeframe
- `governance_action`: **APPROVE_TEST_ONLY** or **DENY_TEST_ONLY** explicitly invoked with `governance_policy_id`, `approver_id`, and `approval_nonce`; these are engineering authorization labels **not** an external authenticated G0/Paper registry
- `strategy_governance_status`: APPROVED_TEST_ONLY / DENIED_TEST_ONLY, `scope=SYNTHETIC_OFFLINE_ENGINEERING_ONLY`, trading authority **NONE**. The approval does **not** depend on Scanner SELECTED or source Secretary ACK, cannot grant PIT or operational rights.

`aql.scanner-c.strategy-route-request.v1`:
- All the same strategy identity, explicit approval receipt SHA/policy and precise Scanner nomination SHA/attempt/run SHA, symbol/native15m, source raw/manifest/universe SHA, decision cutoff, full per-strategy denominator and census
- Separate original source-custody SHA, Core #245 native **price_query SHA**, Core #253 **query_local SHA** (must differ), and `historical_known_at_ms=None` (no invented historical PIT)
- Independent statuses: `source_custody_status` (TEST_ONLY_ATTESTED / RETROSPECTIVE_NON_PIT), `scanner_nomination_status` (SELECTED/REJECTED/UNKNOWN etc), `strategy_governance_status` (explicit APPROVED_TEST_ONLY / DENIED_TEST_ONLY), and `strategy_secretary_status=NOT_ENQUEUED`. `strategy_route_status=ROUTE_CANDIDATE_TEST_ONLY` only for explicit test approval **plus** synthetic Scanner SELECTED and TEST_ONLY source custody; otherwise WAIT.
- A *candidate* is never a Core Secretary ACK, strategy routing commit, Factory Lab pass, Paper approval, order, fill or operational activation. Every request contains NONE trading/paper authority and zero orders/positions. No source-only ACK can upgrade strategy approval.

`service.py::scan_and_prepare_test_only_routes` reuses Scanner B native 15m indicator+DNA adapter and Work235 spec validation, one sealed approval action per policy, all source-universe symbol pairs, exact per-strategy census, deterministically sealed route proposals. No bar resampling and no Discoverer gate.

## Canonical valid schema example (shortened illustrative values)

```json
{
  "schema": "aql.scanner-c.strategy-route-request.v1",
  "strategy_id": "test_momentum", "strategy_version": "1.0.0",
  "config_digest": "<sha256 of native15m policy>",
  "timeframe": "15m", "market": "fixture", "symbol": "AAA",
  "strategy_governance_status": "APPROVED_TEST_ONLY",
  "scanner_nomination_status": "SELECTED",
  "scanner_operational_status": "UNKNOWN",
  "strategy_approval_sha256": "<sealed approval receipt sha256>",
  "scanner_nomination_sha256": "<sealed nomination sha256>",
  "source_raw_sha256": "<synthetic raw source sha256>",
  "source_custody_receipt_sha256": "<independent Core test custody sha256>",
  "core245_price_query_sha256": "<SHA256 of native price query>",
  "core253_query_local_sha256": "<DIFFERENT SHA256 of query_local>",
  "historical_known_at_ms": null,
  "source_custody_status": "TEST_ONLY_ATTESTED",
  "strategy_secretary_status": "NOT_ENQUEUED",
  "strategy_route_status": "ROUTE_CANDIDATE_TEST_ONLY",
  "source_secretary_ack_is_strategy_approval": false,
  "paper_authority": "NONE", "trading_authority": "NONE",
  "orders_created": 0
}
```

An actual full receipt contains the same immutable parent identity fields and `{"payload":{...},"sha256":"..."}` wrapper; **never** use the illustrative strings as evidence.

## Canonical invalid schema example

```json
{
  "strategy_governance_status": "APPROVED_TEST_ONLY",
  "governance_action": "ACKED_SOURCE_ONLY",
  "source_secretary_ack_is_strategy_approval": true,
  "scanner_operational_status": "SELECTED",
  "paper_authority": "ALLOW_TRADING"
}
```

This fails: ACK is not a governance action; historical Scanner operational status cannot be SELECTED; Paper authority remains NONE. Also reject wrong policy config/strategy version, modified inner receipt, future cutoff, mixed timeframe, source SHA drift, incomplete per-strategy census, replay conflict, tampered known-at/PIT, aliasing Core query SHA domains, or absence of explicitly recorded governance decision.

## Next cross-owner contract

**Core C owner**: add a *separate durable strategy-level Secretary queue* accepting the EXACT `StrategyRouteRequest` and its approval/nomination parent receipts; Core must verify the complete SHA-sealed identity, policy decision, distinct SHA parents and TEST_ONLY restrictions; provide PENDING→explicit ACK/quarantine/replay, not replace B source-only queue. Naming suggestion `aql.core.secretary-strategy-route.v1`, subject to Core approval.

**Factory C owner**: consume only this new **strategy-level Core-verified** route and explicit ACK/evidence; check approved policy identity and all parent SHAs, fail closed on missing/mismatched approval, PIT or source drift, expired/unknown nomination; execute existing Lab→isolated TEST_ONLY Paper WAIT/REJECT with 0 orders/positions/fills. The Scanner `ROUTE_CANDIDATE_TEST_ONLY` status alone MUST NOT be treated as Factory-ready.

Open integration seams: authentic independently verified new original 15m source unavailable; Work #235 operational native15m is NOT_CONNECTED; no full live/paper path or scientific PIT claims. Keep SOURCE_UNAVAILABLE separately. Do not repeat Feb/Aug, old 106 reports, prior B 96 test executions; one new C consolidated gate after all three owners deliver.


## Package C canonical reconciliation with Core #261 / Factory #260 (2026-11-05)

Canonical Scanner C receipts stay **unchanged**: `Frozen` `{payload, sha256}`, schemas `aql.scanner-c.strategy-approval.v1` and `aql.scanner-c.strategy-route-request.v1`. SHA256 seals alone establish immutable content, not an independently authenticated signer, historical PIT or authorization to trade. No alias to Factory's `artifact_sha256` or Core's separate projected internal schemas.

| Field / meaning | Scanner C #259 authoritative wire | Core C #261 actual read-only seam | Factory C #260 provisional fields / action |
|---|---|---|---|
| Approval | `strategy_approval_sha256` references `aql.scanner-c.strategy-approval.v1` Frozen receipt, `APPROVE_TEST_ONLY` / `DENY_TEST_ONLY`, `governance_policy_id`, `approver_id`, `approval_nonce`, `scope=SYNTHETIC_OFFLINE_ENGINEERING_ONLY` | `reconcile_scanner_c_candidate` calls Scanner owner `verify_test_only_approval`; Core's internal `aql.scanner.c.strategy-approval.v1` is **different** | Factory provisional `aql.scanner.strategy-approval-test-only.v1` and `artifact_sha256` **not wire compatible** |
| Request | `aql.scanner-c.strategy-route-request.v1` Frozen `sha256`, `ROUTE_CANDIDATE_TEST_ONLY` or WAIT | Core replays actual `seal_strategy_route_request` and independently verifies all Frozen parents; its internal `aql.core.c.strategy-route-request.v1` is **different** | Factory provisional `aql.core.secretary-strategy-route.v1` and `artifact_sha256` **not wire compatible** |
| Strategy identity | `strategy_id`, `strategy_version`, native15m `config_digest`, `definition_digest`, `dna_digest`, `work235_spec_sha256`, `native15m_policy_sha256` | Core validates exact Work235/Scanner policy and preserves fields | Factory `strategy_definition_digest` and Core ROC `strategy_digest` **cannot be equated** to Scanner definition without independent evidence |
| Nomination and census | `scanner_nomination_sha256`, `scanner_run_sha256`, `scanner_attempt_id`, `symbol`, `timeframe=15m`, `cutoff_ms`, `denominator`, `strategy_census` | Core validates actual Scanner Frozen nomination/run/parent seals and counts | Provisional `aql.scanner.native15m-strategy-nomination.factory-c.v1` differs and MUST NOT imply Core historical AQL-SCANNER-V1 `UNKNOWN` became `SELECTED` |
| Synthetic source | `source_raw_sha256` = synthetic JSON, `source_manifest_sha256`, `universe_sha256` | Core preserves distinct Scanner raw domain and identifies lack of JSON→Core ZIP bridge | Factory original-format Core source and Scanner synthetic JSON are **not same-source attested** |
| Original Core source and custody | `source_zip_sha256` and `source_custody_receipt_sha256` | Actual Core B warehouse ZIP SHA, `warehouse.receipt_sha256`, authentic source-only ACK checked against durable SQLite outbox | Factory original `source_bytes_sha256` / `core_253_warehouse_receipt_sha256` are separately checked; a declaration alone is no provenance proof |
| Query SHA identities | `core245_price_query_sha256` and `core253_query_local_sha256`, separate, unequal | `identity_map.core_245_native_price_query_sha256`, `identity_map.core_253_query_local_sha256` checked independently | `core_245_price_query_sha256` and `core_253_query_local_sha256`, only explicit mapping after parent validation |
| Time and issuer | `cutoff_ms`, `historical_known_at_ms=null`; Scanner approval has **no issued-at/expiry or source signer attestation** | Core internal route expiry cannot establish a Scanner approval issuer or historical PIT | Factory `approval_time_ms`, `expires_at_ms` MUST NOT be guessed or backfilled |
| Status and authority | `strategy_governance_status` distinct from `scanner_nomination_status`; `strategy_secretary_status=NOT_ENQUEUED`; paper/trading NONE | `aql.core.c.scanner-source-reconciliation.v1`: `decision=WAIT`, `reason=SOURCE_LINEAGE_NOT_CONNECTED`, blocking condition `SCANNER_SYNTHETIC_RAW_TO_CORE_ZIP_NOT_ATTESTED` | Factory must return WAIT without genuine matching, verified strategy-level Core ACK. Source-only ACK != strategy approval != consumer ACK |

**Canonical status translation:** `WAIT_SOURCE_PROVENANCE_NOT_CONNECTED` is a descriptive joint status, not a renamed Core wire enum. Preserve the original signed Core `decision=WAIT` and `reason=SOURCE_LINEAGE_NOT_CONNECTED` fields. The Scanner `ROUTE_CANDIDATE_TEST_ONLY` merely proposes a TEST_ONLY path and NEVER means Core PENDING, an actual Factory consumer ACK or Paper authority.

**Positive reproducible witness:** pinned Core #261 `tests/test_aql_core_c_scanner_reconciliation_v1.py::CoreCActualScannerContract.test_authentic_scanner_c_envelopes_verify_but_source_waits` uses actual Scanner C Frozen approval/request/run/nomination receipts and real Core B source ACK with distinct query SHA domains. It verifies independently, then outputs signed deterministic **WAIT** with `SCANNER_SYNTHETIC_RAW_TO_CORE_ZIP_NOT_ATTESTED` and zero orders. This is positive proof of safe *contract verification*, **not** proof of a joined source or approved execution.

**Negative reproducible witnesses:** `test_wrong_core_parent_is_explicit_wait_not_connected` changes the sealed declared Core ZIP SHA and produces `SCANNER_DECLARED_CORE_ZIP_PARENT_DRIFT`; `test_explicit_denied_governance_is_retained_as_wait` produces `NO_EXPLICIT_TEST_ONLY_ROUTE_CANDIDATE`; `test_resealed_forgery_of_scanner_c_route_is_not_trusted` recomputes the outer receipt hash after falsifying fields but fails Scanner full-parent recomputation. Execute only the new C reconciliation test module with the pinned C runner, not B suites.

**Final handshake condition:** Scanner #259's canonical fields require no rewrite to satisfy Core #261's current read-only reconciliation. The remaining owner-specific consumer mismatch is Factory #260, which must explicitly consume Scanner Frozen parents AND Core's signed read-only reconciliation, refuse to fabricate a strategy Secretary/consumer ACK or resolve the synthetic/original source mismatch, and leave isolated Paper WAIT. Core's separate internal projected route remains distinct from this canonical Scanner request. A source-backed C route can only be claimed when independent same-source provenance and matching strategy-level Core custody/ACK are actually demonstrated. No new original source/PIT attested; no G0/merge/trading/holdout.