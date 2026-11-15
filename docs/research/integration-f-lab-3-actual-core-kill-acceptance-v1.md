# F-LAB-3 acceptance hardening — real synthetic Core SQLite + actual process termination

**Status:** `REAL_MODULE_SYNTHETIC_WAREHOUSE_AND_RESTART_PASS`, with **one precise fail-closed upstream partial-cutoff mismatch**. No original owner E: source, original H2 run, G0, F5, paper, trading or independent audit conclusion. This is a small acceptance delta to the prior F-LAB-3 implementation, not a new coordinator or research engine.

## Pinned upstream contract and actual path

Integration tested code commit `294a557e1bf0a2c4f779b5f4cccc87c74c408381`; Core #275 `99c27ea2c1a4d41aaae361141301a8a9ea3b33c3`, Scanner #277 `3c82448702c9ae35783716e4e2c3b640010db97c`, Scanner B `30c37ae56851488b882998c7fa0085ec51dbfc92`, Factory #267 `04b63cc9b406b1f3eae2ac7de5d43ebda26dbfdf` (new F-LAB-1/2), Work235 `6acbcc7fc243b132f58170df4c6469bbf7f4eff8`. All role files staged from exact commits **only in throwaway CI runners**, not main or any user's local checkout.

**Actual complete-case chain**, all modules unmocked at the relevant boundary:

`synthetic ZIP+checksum` → actual Core253 `admit_local_original` (writes disposable `warehouse.sqlite`/immutable stager) → actual Core245 retained `query_price_custody` on stager readback → actual Core253 `query_local(require_complete=True,sqlite_immutable=True)` → Scanner H `evaluate_strategy_plugin`, which independently calls `query_local(require_complete=False,sqlite_immutable=True)` again against the actual warehouse → Factory generic H immutable package/SQLite + actual Scientific Lab → Factory F-LAB-1 typed PREPARED→VERIFIED_WAIT index → actual Core Secretary `WAIT_RESEARCH_REVIEW` with four NULL ACKs. Different Core245 `price_query_sha256` and Core253 `query_sha256` remain distinct; source and manifest integrity SHA parents are unchanged. TEST_ONLY, RETROSPECTIVE_NON_PIT, historical PIT NOT_ATTESTED, no alpha or trade authority.

**Two real OS process terminations:** with a disposable synthetic source and one saved packet, child #1 uses `os._exit(77)` **after** `SCANNER_VERIFIED` checkpoint was fsync'd, child #2 uses `os._exit(77)` **after** `LAB_EVALUATED` checkpoint, then two *fresh* child processes complete and replay `SECRETARY_WAIT`. Test verifies identical sealed receipt SHA, exactly one Factory H result and one F-LAB index row, durable Secretary WAIT and source stage byte hashes unchanged. This is real abrupt **process termination**, NOT physical power loss, database crash under concurrent writer, Windows directory fsync or operational failover. The existing coordinator only gained a narrow post-checkpoint callback useful for termination testing; no new database, Source lane, broker or subprocess scheduler.

**Negative acceptance:** real Core incomplete availability cutoff refused by `require_complete=True`; Scanner also rejects actual `PARTIAL` query if cutoff is before requested end (this is an **open precise interop issue**, not a bypass). Contradictory source/query SHA rejects before writing a Factory H table; prior F-LAB-3 tests cover checkpoint integrity, invalid PIT, same-ID conflict, output overlap, missing 72h outcomes, false approval. Prior H2 policy tests preserve SHM/zero-WAL safe staging, nonempty WAL refusal and external license/rights block. We do not assert that these older cases were all rerun in this focused acceptance workflow.

## One tested matrix, exact evidence

[**Actions run #42467112054**](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/42467112054), code SHA `294a557e1bf0a2c4f779b5f4cccc87c74c408381`: **4/4 jobs SUCCESS** across Windows and Ubuntu, Python 3.11 and 3.12. Each job executes **8 prior F-LAB-3 + 5 new real SQLite/process-kill tests = 13/13 PASS** (52 executions total). The staged Core/Scanner/Factory/Work commits are checked for exact SHA; no owner source or original keys in GitHub Actions.

### Single bounded source-contract blocker (reported to Scanner)

Scanner #277 at `3c82448702c9ae35783716e4e2c3b640010db97c` `tools/scanner_strategy_f/research_strategy_plugin.py::_validate_query` requires `start_ms < end_exclusive_ms <= decision_cutoff_ms`, including when the underlying real Core253 query is validly PARTIAL because cutoff is **before** end. Core253 `query_local(require_complete=False)` can return sealed `coverage=PARTIAL`/missing bars for that early cutoff; Scanner throws `H_CORE_CUTOFF_OR_RANGE` before its all-UNKNOWN quarantine branch. Existing synthetic fixture with partial/source missing and late cutoff demonstrates all UNKNOWN but is not a real Core admission proof. **Current production boundary is fail-closed**, not falsely PASS. Request to Scanner is [#277/6719800295](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/277#issuecomment-6719800295): evaluate a scoped way to accept only verified noncomplete source query and quarantine all decisions UNKNOWN without future leakage; if impossible, retain refusal and report. No upstream changes or approvals presumed.

## Files modified by this bounded delta

- `tools/atlas_f_lab_3_lifecycle_v1.py`: optional `on_durable_stage` callback immediately after checkpoint atomically written, no new stage semantics.
- `tests/test_atlas_f_lab_3_actual_warehouse_restart_v1.py`: actual Core admission/readback/Scanner and process-kill tests.
- `.github/workflows/atlas-f-lab-3-lifecycle.yml`: additional focused acceptance suite for all four environments.

The existing H2 `strict-custodian` and `official-binance` opt-in local private source lanes are untouched. The original 43 owner staged files are not accessed or modified, no code from other managers is edited or merged. Audit #256 remains deferred to one consolidated delta review per the owner.
