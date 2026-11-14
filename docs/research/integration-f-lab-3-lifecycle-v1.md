# F-LAB-3 — Restartable synthetic research lifecycle (bounded)

**Status:** real-module **synthetic/offline** lifecycle and recovery demonstrated at exact Integration code SHA `317f80e4164f12969b71fda867eea78bc9becd6a`. Not a live or original E: run. Last original owner historical evidence remains [Integration #271/6707587050](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/271#issuecomment-6707587050); one original H2 permission remains conditional and original H2 not run.

## Exact unmerged role heads

- Integration #271 code: `317f80e4164f12969b71fda867eea78bc9becd6a`
- Core #275: `99c27ea2c1a4d41aaae361141301a8a9ea3b33c3`
- Scanner #277: `3c82448702c9ae35783716e4e2c3b640010db97c`
- Scanner B native dependency: `30c37ae56851488b882998c7fa0085ec51dbfc92`
- Work235: `6acbcc7fc243b132f58170df4c6469bbf7f4eff8`
- Factory #267 **F-LAB-1/2 latest**: `04b63cc9b406b1f3eae2ac7de5d43ebda26dbfdf`

All role modules are overlaid **only** in disposable GitHub Actions runner worktrees; no upstream PR changes, branch merges, owner local checkout or 43 staged files modified.

## Reproducible actual-module interoperability

| Boundary | Existing native API | Integration action | Result |
|---|---|---|---|
| Synthetic Core/Scanner input | Scanner #277 `case_for` test fixture, Core253 bounded `core_query` | Verify packet canonical hash, source/query/cutoff and `NOT_ATTESTED`; derive deterministic run ID | PASS, no original-source IO |
| Scanner → Factory H | `run_factory_h_generic_research`, `factory_h_research_results_v1` | Use actual H runner and SHA-verified immutable SQLite readback | PASS, same experiment |
| Factory → Lab | Factory H `scientific_lab` nested immutable SHA | Check ledger/Lab digest chain | PASS, no copied evaluator |
| Factory → index | F-LAB-1 `build_link/prepare_experiment_link` | Write existing additive typed cross-reference, preserve true Scanner decision census | PASS; no fabricated F2 attempts |
| Factory → Secretary | Core #275 `build_generic_research_result_route/route_generic_research_result` | Persist `WAIT_RESEARCH_REVIEW`, all **four** ACKs null; F-LAB-1 `finalize_experiment_link` | PASS, actual durable SQLite |
| Secretary → paired Lab | F-LAB-2 `build_generic_paired_lab` | Reuse actual existing 4/24/72h P2 producer/consumer | PASS; future 72h unavailable remains UNKNOWN |
| Recovery | New `tools/atlas_f_lab_3_lifecycle_v1.py` | Durable SHA-sealed versioned checkpoint with PLANNED → SOURCE_VERIFIED_SYNTHETIC → SCANNER_VERIFIED → FACTORY_IMMUTABLE → LAB_EVALUATED → SECRETARY_WAIT. Existing Factory and Secretary remain sole canonical stores | PASS, crash after scanner and lab; idempotent restart/replay |

**Identity and no-false-promotion:** synthetic fixture covers two genuinely distinct source/strategy/cost run identities plus one `PARTIAL` source cohort whose 64 Scanner decisions are quarantined `UNKNOWN`, zero modeled trades. Separate F-LAB-2 paired 4/24/72h windows remain descriptive, never approved economic/PIT/holdout/future observation. Existing F2 24=20+4 is untouched. New coordinator does NOT duplicate experiment registry, scanner engine, Factory cost/fill logic, Lab metrics, Secretary service, market IO or broker.

**Fail-closed cases:** source/query hash conflict, same experiment ID changed strategy, tampered checkpoint digest, conflicting in-flight pending checkpoint, unsafe checkpoint output overlap, false historical PIT, incomplete source paired outcomes, second run replay conflicts and Windows SQLite connection lifetime. The packed fixture calls the actual H runner, F-LAB-1, Lab, Secretary, F-LAB-2 modules; only synthetic Core source fixture is injected, not mocked cross-stage success. Pre-existing official Binance mode remains an independent fail-closed H2 path; **do not run or bypass original E: rights/terms gate**.

## Exact test execution

[GitHub Actions F-LAB-3 run #42465770108](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/42465770108): 4/4 jobs terminal SUCCESS, **8/8 tests each** on Ubuntu Python 3.11/3.12 and Windows Python 3.11/3.12 (32 test executions). All tests use synthetic, nonprivate fixtures. The ephemeral runner loads actual pinned Core/Scanner/Work235/Factory heads, not assumed merged-to-main code.

## Final limits

**`F_LAB_3_SYNTHETIC_ENGINEERING_PASS`** covers engineering lifecycle/restart/readback only. Original owner Binance H2 remains `BLOCKED_EXTERNAL_LICENSE_AND_PRIVATE_EVIDENCE`; historical PIT `NOT_ATTESTED`; G2 outcomes not externally verified; research review not approved; `F5` blocked; `holdout` sealed; `Paper/live` and trading NONE; no merge or G0. Independent Audit #256 final consolidated delta review deferred by owner.
