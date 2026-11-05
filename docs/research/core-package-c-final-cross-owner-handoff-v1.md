# ATLAS Package C — Core / Scanner / Factory exact-contract handoff

Owner C instruction on #226/6650417711; final coordination. **Do not merge owner Draft PRs.** This is a synthetic TEST_ONLY contract, not PIT, source-backed Scanner screening, G0 or operational Paper.

## Pinned canonical owners and exact interfaces

- Core C #261: `research_wp_r0/aql_core_c_scanner_reconciliation_v1.py::reconcile_scanner_c_candidate` and `aql_core_c_strategy_secretary_route_v1.py`; stacked on Core B #226.
- Scanner C #259: `tools/scanner_strategy_c/approval_route.py`; `Frozen.receipt() = {"payload": ..., "sha256": ...}`. Approval schema **`aql.scanner-c.strategy-approval.v1`**, request schema **`aql.scanner-c.strategy-route-request.v1`**; independently verified using Scanner's actual `verify_test_only_approval` and `seal_strategy_route_request` (byte-identical replay). Scanner's approval is explicit `governance_action=APPROVE_TEST_ONLY`, `scope=SYNTHETIC_OFFLINE_ENGINEERING_ONLY`, not an independently signed production approval, not time-expiring (no timestamp in its actual schema). The route has `source_raw_sha256` for synthetic Scanner JSON, **separate** from caller-supplied `source_zip_sha256` for original-format Core ZIP; both are retained, never asserted equal.
- Core B #226: sealed `aql.core.historical-dual-query-identity-map.v1` has **`core_245_native_price_query_sha256`** and **`core_253_query_local_sha256`**, separately verified. The Core source-only Secretary ACK uses `receipt_sha256` and must exist in the durable outbox/event chain. Source ACK **is not** strategy approval.
- Core C internal strategy Secretary is **`aql.core.c.strategy-secretary-route.v1`** with distinct research-only route approval, PENDING/RETRY/ACKED/QUARANTINED; this internal approval is **not the same schema as Scanner's Frozen approval**, and cannot be silently adapted. Its Factory consumer ACK is a separate event, never source ACK.
- Factory C #260 provisional consumer expects `aql.scanner.strategy-approval-test-only.v1`, `aql.scanner.native15m-strategy-nomination.factory-c.v1`, `aql.core.secretary-strategy-route.v1`, all with **`artifact_sha256`**. Those are **not canonical Scanner #259/Core #261 receipts**. Factory must use an explicit new versioned consumer adapter that verifies original owner parent receipts, rather than renaming `sha256` to `artifact_sha256`, assuming approval expiry, or re-sealing as though equivalent. Factory owns that adapter.

## Reproducible canonical **WAIT** example (current connected evidence)

The already committed focused test `tests/test_aql_core_c_scanner_reconciliation_v1.py::CoreCActualScannerContract.test_authentic_scanner_c_envelopes_verify_but_source_waits` constructs **actual Scanner #259** Work235 policy, native15m policy, Scanner run, nomination, explicit approval and route request using Scanner's own fixture. It also constructs an **actual Core B #226** TEST_ONLY original-format ZIP, pinned RawVault, native #245 and indexed #253 query parent, immutable warehouse and durable source-only ACK. This is **not** a replay of accepted Feb/Aug or Bundle B 96-test gate.

After staging exact owner code in the Core C CI workflow, execute:

```bash
PYTHONPATH="$PWD:$PWD/tests" python -m unittest -v tests.test_aql_core_c_scanner_reconciliation_v1
```

Or in the Core C CI workflow use the existing unittest discovery command with the same test file. In the positive **parent verification / negative source provenance** test:

```python
receipt = reconcile_scanner_c_candidate(
    core.root,
    scanner_route_receipt=scan_route.receipt(),
    scanner_approval_receipt=explicit_approval.receipt(),
    scanner_run_receipt=scan_run.receipt(),
    scanner_nomination_receipt=nomination.receipt(),
    work235_spec_receipt=work_spec.receipt(),
    native15m_policy_receipt=native15m_policy.receipt(),
    identity_map=core_dual_sha_map,
    warehouse_receipt=committed_warehouse,
    source_ack_receipt=durable_source_only_ack,
)
assert receipt["decision"] == "WAIT"
assert receipt["reason"] == "WAIT_SOURCE_PROVENANCE_NOT_CONNECTED"
assert "SCANNER_SYNTHETIC_RAW_TO_CORE_ZIP_NOT_ATTESTED" in receipt["blocking_conditions"]
assert receipt["scanner_c_approval_sha256"] == explicit_approval.receipt()["sha256"]
assert receipt["core_source_only_ack_sha256"] == durable_source_only_ack["receipt_sha256"]
assert receipt["core_245_price_query_sha256"] == core_dual_sha_map["core_245_native_price_query_sha256"]
assert receipt["core_253_query_local_sha256"] == core_dual_sha_map["core_253_query_local_sha256"]
assert receipt["strategy_secretary_status"] == "NOT_ENQUEUED"
assert receipt["factory_consumer_ack"] is None
assert receipt["orders_created"] == receipt["paper_positions"] == 0
```

The full executable fixture, including all constructor parameters, is in the named test; the code above illustrates its output contract, not a standalone file. Replaying identical parents gives byte-for-byte identical sealed `reconciliation_sha256`.

## Reproducible negatives

- `test_wrong_core_parent_is_explicit_wait_not_connected`: Scanner `source_zip_sha256="f"*64` yields `SCANNER_DECLARED_CORE_ZIP_PARENT_DRIFT`, still **`WAIT_SOURCE_PROVENANCE_NOT_CONNECTED`**.
- `test_explicit_denied_governance_is_retained_as_wait`: `DENY_TEST_ONLY` yields `NO_EXPLICIT_TEST_ONLY_ROUTE_CANDIDATE`; no strategy enqueue.
- `test_resealed_forgery_of_scanner_c_route_is_not_trusted`: even recomputing the outer Scanner Frozen SHA with `source_secretary_ack_is_strategy_approval=True` fails Scanner canonical replay.
- `test_broken_core_source_only_ack_is_rejected`: changing ACK evidence and recomputing the outer SHA does not bypass durable outbox verification.
- `test_work235_native_policy_parent_tamper_fails_closed`: altered native policy fails independent Scanner Work235 policy verification.

## Gate handoff and blocking facts

**Factory lead** should consume canonical Scanner Frozen receipts and Core sealed reconciliation receipt, preserving the two query SHA domains, strategy ID/version/config/definition, nomination/run/policy, source SHA, cutoff, symbol/timeframe and separate ACKs. Until a **separately independently verified same-source bridge** binds synthetic Scanner JSON to the Core original-format ZIP, Factory must return **WAIT**; it must not treat Scanner `ROUTE_CANDIDATE_TEST_ONLY` as Core PENDING, Core strategy approval or Factory ACK. No new authentic month is needed to validate this fail-closed software contract. A positive fully-connected same-source E2E is **not evidenced** and must not be simulated by relabeling fields. A future versioned same-source attestation requires explicit owner authorization, source lineage and a new test gate.

Only **one consolidated C new-delta integration gate** after Factory adapts. Audit independently afterward. Discoverer non-blocking. No Bundle B rerun, Feb/Aug originals, holdout, trading, merge or G0.
