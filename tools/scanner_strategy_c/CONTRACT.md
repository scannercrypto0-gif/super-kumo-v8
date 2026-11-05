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
