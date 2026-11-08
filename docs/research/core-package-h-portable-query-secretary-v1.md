# ATLAS Package H — Core portable query and research Secretary adapter (Draft)

Status: **research-only engineering delta**, no original owner E: execution, no signed
approval, no G0 or PR merge. Integration #271 is the canonical cross-manager
schema owner; these are additive Core adapters pending its H-stage matrix.

## Reuse, never rebuild

- Existing #245 native custody query + #253 local Warehouse/RAW #211 and
  #226 dual identity remain authoritative for reads. **No new warehouse**.
- Existing Core F `read_recovery_diagnostic(warehouse_root, vault_root,
  recovery_file, mapping)` performs original owner-local **no-write** dual-query
  verification once per authorized session and returns 10 per-month results.
- New `adapt_verified_recovery_month(month_result, request)` selects an aligned,
  bounded interval from that verified in-memory result; does **not** infer source
  provenance from caller-created hashes. Integration must provide Core-verified
  objects, never arbitrary resealed payloads.
- Existing Secretary SQLite backend `_connect` and SHA event convention
  reused; `route_research_result(secretary_root,...)` adds only research-result
  tables in a **separate existing Secretary root**. Never pass the private
  historical Warehouse/RawVault root as `secretary_root`: those roots must be
  read-only. There is no parallel approvals or research calculation service.

## Portable query contract

Request schema `aql.core.h.portable-research-query-request.v1`, exact keys:
`schema,month,dataset_id,start_ms,end_exclusive_ms,decision_cutoff_ms,
require_complete`. Time bounds are UTC milliseconds, `[start,end)`, 15-minute
grid, maximum 4096 requested bars. The month must be one of the 10 admitted
original months. February/August inventory-only is not silently loaded;
Integration should emit four `UNKNOWN` attempt statuses upstream.

Response `aql.core.h.portable-research-query.v1`: `receipt` (SHA-sealed,
source/manifest/warehouse/native245/local253/dual-map/recovery SHA **separate**,
range bar-identity SHA, status `COMPLETE/PARTIAL/UNKNOWN`, missing bar opens,
count/coverage/cutoff, `historical_pit=NOT_ATTESTED`,
`historical_known_at_ms=null`, authority NONE) plus `bars` in memory.
`read_recovery_diagnostic` must be called first in the private owner-authorized
read-only operator; the adapter itself is **not** independent attestation.
Bars at or after cutoff cannot be passed into a strategy.

Illustrative synthetic fixture / caller pattern only:

```python
# verified is the genuine Core read_recovery_diagnostic result produced in
# an separately authorized, no-write session, not a user-made SHA dict.
from research_wp_r0.aql_core_h_portable_query_v1 import (
    REQUEST_SCHEMA, adapt_verified_recovery_month,
)
request = {
    "schema": REQUEST_SCHEMA, "month": "2024-01",
    "dataset_id": "BINANCE-SPOT-BTCUSDT-15M-2024-01-F-v1",
    "start_ms": start_ms, "end_exclusive_ms": end_ms,
    "decision_cutoff_ms": cutoff_ms, "require_complete": False,
}
view = adapt_verified_recovery_month(verified["2024-01"], request)
```

## Research-result Secretary contract

`build_research_result_route(factory_report, *, strategy_definition_sha256,
strategy_config_sha256,code_sha256,cost_policy_sha256,lab_report_sha256)`
consumes existing SHA-sealed Factory v2 research-only result and explicit
external pointers to strategy/config/code/cost policy and **separate** Lab
evaluation. No trade/evaluation recalculation. Factory `lab_sha256` is the
causal focus digest, **not** the new scientific Lab report SHA.

`route_research_result(secretary_root, factory_report, **parents)` makes one
durable idempotent `WAIT_RESEARCH_REVIEW` event, with conflict detection,
readback, SHA event trace and no source/strategy/Factory ACK. It deliberately
does **not** issue or accept a research-review ACK without Integration/Audit's
independently trusted issuer contract. This is an explicit bounded WAIT, not
a fake completion; `read_research_result_route(root, experiment_id)` verifies
stored content and trace.

Never confuse `receipt_sha256` with a trusted signature. An independently
trusted research review, if later supplied, must be a distinct role and
content-addressed parent, not `Factory ACK`, `StrategyApproval`, or F5.

## Focused engineering gate

`python -m unittest discover -s tests -p 'test_aql_core_h_portable_query_v1.py' -v`

`python -m unittest discover -s tests -p 'test_aql_core_h_research_secretary_v1.py' -v`

Workflow: `.github/workflows/aql-core-h-portable-query.yml`, Linux +
Windows / Python 3.11, 3.12 and 3.13. Synthetic-only tests exercise cutoff
exclusive boundary, partial/UNKNOWN, separate hash identity, sealing, forged
approvals, durable duplicate/restart, event tampering and no source-row writes.
Existing full F/Factory checks continue separately.

## Explicit nonclaims

The 2026-11-07 owner E: `RESEARCH_E2E_DIAGNOSTIC_PASS` is already delivered;
do not repeat it to validate this additive synthetic API. Temporary zero-cost
diagnostic policy is **not** real economic performance. No PIT certification,
original F2 report reconstruction, holdout opening, signed F5, independent
StrategyApproval, Paper/live or alpha claim.

## Generic Scanner H → Factory H → Core H (additive, not F2 coercion)

Factory #267 exact schema inspected at `52504ad59d75976ce45fb8f75c1b278c3d1b0975`. The generic path is **separate** from the immutable F2 24/20+4 route above, which stays unchanged. Core H consumes **three** SHA-sealed objects: actual Factory input `aql.factory.h.generic-signal-input.v1`, the immutable parent `aql.factory.h.generic-immutable-package.v1`, and outer result `aql.factory.h.generic-research-result.v1`. This is *not* an original-source authenticity attestation; Integration must independently call Scanner/Factory verifiers first.

```python
from research_wp_r0.aql_core_h_research_secretary_v1 import (
    route_generic_research_result, read_generic_research_result_route,
)
route = route_generic_research_result(
    existing_secretary_root, verified_factory_input,
    immutable_factory_package, sealed_factory_result)
assert route["state"] == "WAIT_RESEARCH_REVIEW"
assert read_generic_research_result_route(
    existing_secretary_root, verified_factory_input["experiment_id"]) == route
```

`build_generic_research_result_route` validates *actual Factory output field names*, and seals independently: Factory execution report `aql.factory.h.generic-execution-report.v1`, ledger `aql.factory.h.generic-trade-event-ledger.v1`, scientific Lab `aql.factory.h.scientific-lab-report.v1`, Factory review pointer `aql.factory.h.generic-secretary-review-receipt.v1` (not an ACK), and immutable package/result parents. It requires matching source ZIP / manifest / bounded Core #253 query SHA (which is **not** the distinct whole-month Core #245 native query SHA); Scanner policy/batch, strategy plugin/definition/config, Scanner and Factory code, cost policy, experiment/result, Lab/ledger/uncertainty SHA and decision cutoff. No SHA is silently renamed or reconstructed.

The variable Generic H cohort requires `expected=observed+missing`, exact event grid and signal categories, `ENTRY_SIGNAL/EXIT_SIGNAL/NO_SIGNAL/UNKNOWN` and modeled/unknown outcome count. Partial/unknown cohorts must quarantine all signals and no modeled fills. Research review remains **WAIT** with four ACK fields null, explicit `NOT_ATTESTED` PIT/economics and `NOT_GRANTED` F5. First and replay outer `receipt_sha256` may legitimately differ due to `store_status`; the stored immutable parent SHA must match, so durable Secretary route identity stays stable. The generic table lives *in the same existing Secretary SQLite root* as legacy F2, never a separate warehouse or approval service. This root must be isolated from original owner RawVault / historical Warehouse.

Focused real SQLite / Windows test:
`python -m unittest discover -s tests -p 'test_aql_core_h_generic_research_secretary_v1.py' -v`.
This is structural synthetic integration **inside Core**; Integration #271 still owns the one unmocked complete Scanner→Factory→Lab→Secretary pinned overlay, which is a different acceptance gate. Neither the tests nor self-sealing synthetic fixtures mean scientific/economic approval.
