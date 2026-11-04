## Core Bundle B — executable pinned contracts for Factory's single new-delta integration gate

Owner directive: [PR #226/6632973252](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/226#issuecomment-6632973252). This document records actual APIs. **Core/Factory/Scanner Drafts remain separate, OPEN, UNMERGED**. No new Core implementation is necessary to satisfy the already coded interfaces.

### Frozen read-only HEADs

- Core #226: `1b165f85ab0dc21e14d9150764125d92a3b0b568`
- Factory #255: `e66ac39a6443853c60463f7bd5bfaf590bb125a6`
- Scanner B #257: `c6304316883839ffba5573762baed8fbf1207ffb`
- RawVault #211: `7d97b09c0c6ee2650a61d523acb8d8c771a99c46`
- Scanner Engine #227: `b9c9ff8602e79c534402f44bce83c56ec2fa6bb9`
- Work Strategy #235: read-only dependency; native 15m screening **NOT_CONNECTED**.

Verify each SHA with `git rev-parse HEAD` in the permitted **read-only** common runner. No branch merge, no `main` assumption. Factory leads the new-delta gate. Discoverer independent/non-blocking.

### Core source custody / RAW #211

```python
from research_wp_r0.aql_core_authorized_source_transfer_v1 import run_authorized_original_intake
from research_wp_r0.aql_core_backbone_local_v1 import admit_local_original, query_local
from tools.raw_vault_offline.vault import RawVault

# Owner-private original bytes and independent source witness required.
# Vault is an actual pinned #211 RawVault instance, not a mock.
transfer, warehouse, query, queued = run_authorized_original_intake(
    private_core_root, native_zip_bytes, original_checksum_bytes,
    retained_source_witness, vault=RawVault(private_raw_root),
    cutoff_ms=offline_cutoff_ms,
    message_id=stable_source_message_key, test_only=False,
)
assert warehouse["status"] == "OFFLINE_LOCAL_WAREHOUSE_COMMITTED"
assert warehouse["vault"]["vault"] == "EXISTING_PINNED_RAW_VAULT"
assert warehouse["source_zip_sha256"] == retained_source_witness["archive_sha256"]
assert query["source_bytes_sha256"] == warehouse["source_zip_sha256"]
assert query["source_availability"] == "RETROSPECTIVE_NON_PIT"
```

This contract requires a matching source ZIP + original CHECKSUM, independent retained source pins, immutable vault admission + readback and canonical indexed Core query. `OFFLINE_LOCAL_STAGE_ONLY` **does not** satisfy a committed RAW ingestion. Correction lineage and generation identity stay immutable; no retrospective PIT or vendor-issued historical known-at is inferred.

### Two *different* price query contracts

| Core API | schema | seal key |
|---|---|---|
| `query_price_custody(HistoricalLibrary, request, expected_source_sha256=..., expected_manifest_integrity_sha256=...)` (#245) | `aql.core.historical-price-custody-query.v1` | `price_query_sha256` |
| `query_local(root,dataset_id,version,start_ms,end_exclusive_ms,cutoff_ms,required_source_sha256=...,require_complete=True)` (#253) | `aql.core.local-history-query.v1` | `query_sha256` |

`price_query_sha256` and `query_sha256` **must be independently rehashed**, not rewritten, aliased or asserted equal. Both must bind `dataset_id`, source version, original ZIP SHA, manifest SHA, cutoff, coverage/grid, original bar checksums and `historical_known_at_ms=None`. Numeric projection can differ; identical bar close/open/checksum/provenance is the enforced common identity.

```python
from research_wp_r0.aql_core_dual_query_identity_map_v1 import bind_dual_query_identities
from research_wp_r0.aql_core_offline_lab_test_strategy_v1 import calculate_one_original_test_strategy

core_strategy = calculate_one_original_test_strategy(
    private_core_root, warehouse, start_ms=source_start_ms,
    end_exclusive_ms=source_end_exclusive_ms, cutoff_ms=offline_cutoff_ms,
)
mapping = bind_dual_query_identities(
    native_price_query, query, warehouse, strategy_evaluation=core_strategy,
)
assert mapping["core_245_native_price_query_sha256"] == native_price_query["price_query_sha256"]
assert mapping["core_253_query_local_sha256"] == query["query_sha256"]
assert mapping["strategy_evaluation_sha256"] == core_strategy["evaluation_sha256"]
assert core_strategy["core_price_query_sha256"] == query["query_sha256"]
assert core_strategy["core_253_query_sha256"] == query["query_sha256"]
```

**Field semantics:** Both `core_strategy.core_price_query_sha256` and `core_strategy.core_253_query_sha256` explicitly point to **Core #253 indexed query_local**, NOT original Core #245 native price custody. The original native SHA is retained in the versioned signed mapping and Factory's *separately* signed `aql.factory.core-query-identity-bridge.v1`. Factory's existing adapter may project a new sealed read-only Lab source receipt with the local SHA in `source.core_price_query_sha256` after preserving the untouched native-source identity separately; never mutate the original receipt.

### Scanner → Core durable Secretary → genuine Factory ACK

```python
from research_wp_r0.aql_core_secretary_routing_v1 import (
    enqueue_nomination, poll_nomination, acknowledge_nomination,
    retry_or_quarantine, route_trace,
)
message=enqueue_nomination(
    private_core_root, native_scanner_v1_unknown_dict,
    strategy_id=research_strategy_id, strategy_version=research_strategy_version,
    warehouse_receipt=warehouse, lane="SLOW", idempotency_key=stable_message_key,
)
item=poll_nomination(private_core_root, now_ms=offline_clock_ms, lane="SLOW")
# Only after the Factory real consumer has independently accepted source evidence:
ack=acknowledge_nomination(
    private_core_root, message_id=item["message_id"],
    payload_sha256=item["envelope"]["payload_sha256"],
    acknowledgement_sha256=factory_source_consumer_receipt_sha256,
)
assert [event["state"] for event in route_trace(private_core_root, item["message_id"])] == ["PENDING","ACKED"]
```

`enqueue_nomination` records strategy ID/version, native #227 sealed Scanner UNKNOWN nomination, original dataset/SHA/market and cutoff. `poll_nomination` is read-only; `acknowledge_nomination` is **explicit consumer action only**, not auto-ACK. Duplicate same payload/key replays idempotently, a conflicting reuse is denied; failed dispatch may retry/backoff and end in terminal `QUARANTINED`, which must remain WAIT, **not ACKED**. Core queue has no broker, no SMTP/Telegram, no live execution. `historical_known_at_ms=None`, `RETROSPECTIVE_NON_PIT`, operational Scanner `UNKNOWN`, `publishable=false`, `delivery_authorized=false`, `trading_authority=NONE` all stay unchanged.

### Factory-led single new-delta gate (avoid duplicate suites)

Factory #255 should combine **existing** Core `tests/test_aql_core_dual_query_identity_map_v1.py` positive/negative original-format synthetic checks and `tests/test_aql_core_backbone_local_v1.py` durable Secretary replay/quarantine with Scanner B #257 `tools/scanner_strategy_b/test_integration.py::CoreSecretaryGate` and Factory `research_wp_r0/aql_factory_core_query_bridge_v1.py` consumer. Validate one source SHA through independent native/local query domains, Core strategy receipt, Scanner source/strategy config and nomination digest, genuine Factory source ACK, Lab/Paper REJECT or WAIT, **zero orders/fills/positions**, and missing ACK, conflict, quarantine, version/cutoff/PIT/known-at drift and duplicate replay negatives. Make *one consolidated evidence bundle and focused CI*. Do not rerun accepted genuine Feb/Aug 2024, existing 106 reports or earlier #256 ACCEPT_IN_SCOPE.

**Previous independently confirmed CI:** Core #226 [#41842369682](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/41842369682) **97/97**, Scanner B #257 [#41844819423](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/41844819423) **16/16 per Python 3.11–3.13**, Factory #255 [#41842035798](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/41842035798) **SUCCESS**. These are independent component CIs, **not** evidence the single new-delta cross-component gate executed.

**External-source blocker:** no additional independently authenticated 2024 BTCUSDT Spot native 15m monthly ZIP + CHECKSUM appears in accessible owner-retained inventory. Preflight implementation exists, but no original third-month RAW COMMITTED or query receipt exists. Status `READY_FOR_SOURCE`, never fake a new source, unauthorized bulk acquisition, historical issuer/PIT evidence, real operational Paper route or a scientific pass. No merge/G0/holdout/trading.
