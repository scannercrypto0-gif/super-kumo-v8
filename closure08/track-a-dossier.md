# ATLAS Track A | Integrated current-phase repair

Current main 8b7f28f27cd960bbc201187f8d4b8390648f5ed2. This update follows [the owner directive](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-6947456283). The [prior baseline and Windows fault proof](https://github.com/scannercrypto0-gif/super-kumo-v8/blob/46500ac75e8e6da80ad6d4e576d03a8de1f38ef9/closure07/repair-dossier.md) are reused. No original repair PR has been merged. The historical CI red remains documented. Current successful checks on unchanged #316/#317/#318 were not rerun.

## Exact review units and acceptance

| Sequence | PR | Head | Tree | Scope |
| --- | --- | --- | --- | --- |
| 1 | #316 | b73a028f01d2d97025ce264de62750c216f07bf2 | feaf9cc9b8e27ca9754842158a96ac0c299f3bdb | Native prospective read, six paths |
| 2 | #318 | 0cf6428826ac990a918df7843359db8e13c5ce62 | 4144b523afde5fe8e7e889f7bbb1830cc04a2fce | Offline source and wire seams, six paths |
| 3 | #319 | f54cb5a963a1279b292d42035cc84dce90fa157e | 8d2b2e78c3810f879ca2aa30ea68e49d132a1ca4 | Factory read-only Experiment/Attempt and sealed retrospective Scanner reader, four paths |
| 4 | #317 | 872bf1823cfb41c8185ad6199caafb9768780802 | a79f0363f72e9931a413cb519330e270a8b277a3 | Restored exact offline CI, four paths |

[Exact path and composed-tree proof](candidate-proof.json): all 20 paths disjoint, composed tree 88cefbc6398adc08c1dd75725073ed10e0a543f9, 15 local generated/mocked checks passed, reverse composition reproduced every predecessor tree. Hosted review heads are separate from the scratch composition. [#319 focused Windows/Ubuntu CI](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/44084361792) verifies the new saved consumer on its exact head. PR-level readbacks are in this dossier.

The new consumer reads the native v1 Factory experiment from a detached SQLite snapshot, validates its schema, identity and expected pin, rejects unfinished WAL/rollback journals, and joins the pinned #309 Scanner census to the exact source/strategy/config and attempt/candidate parent. It verifies source row grid and deterministic order and emits counts only. Generated tests prove repeated native writer-to-reader output, unchanged database bytes, forbidden authority and tampered parent/order denial. Known-at stays UNKNOWN, Core SOURCE_BLOCKED, historical PIT NOT_ATTESTED, Secretary WAIT and zero orders. The readback does not reopen original source, result store, signal dispatch or a trading interface. Producer-side #309 attempt chain and #292 full gateway are separate from this narrow projection.

## All 14 original PRs

| Original | Review scope | Residual disposition and exact reopening condition |
| --- | --- | --- |
| #144 | No release unit | AUTHORITY_BLOCKED. Existing evidence guardian calls an owner-configured rclone/Drive custody path and expects independently retained bundle, ledger head and acknowledgement. Owner must designate the admitted custody witness and explicitly authorize access. No private file or receipt read here. |
| #195 | No release unit | NOT_DUE. Exact legacy pin 20928693f30b1730f0693a293bbf4a1f8ab21c88 exists in Git, but dev_result_bundle and test_first_dev_integration are absent on main. No current native producer of that legacy contract was established. Reopen if Factory selects the DEV engine/consumer pair and permits a generated replay. |
| #226 | #318 exact native ZIP parser scope | PARTIAL. Generated daily ms/µs tests pass. HistoricalLibrary custody and scoped original acquisition require separate rights and authority. |
| #267 | #319 Factory read-only delta | PARTIAL. Scoped canonical Experiment/Attempt identity works. Broad Factory E store/authority integration and topic stack stay separate. |
| #271 | #316/#318 observer and diagnostics | PARTIAL. No Windows supervisor rollout, local config, route grant or retained receipt change. Keep existing independently accepted hold/retry policy in the owner runtime. |
| #286 | #316 native observer and journal | PARTIAL. Collector and original-April archive acquisition were excluded. |
| #287 | #317 exact G1 workflow | SELECTED_RESIDUAL_IMPLEMENTED. Existing production changes already on main. |
| #288 | #317 exact simulator workflow | PARTIAL. Native simulator already on main; promotion/dashboard and prospective live Paper control remain outside scope. |
| #289 | #316 exact forward read | PARTIAL. Archive-coupled CLI/combined workflow remain separate and unnecessary for this native read. |
| #292 | #319 bounded provenance projection | PARTIAL. Full gateway requires independently pinned source and retained fixture classification outside this repair. |
| #305 | #318 wire framing and diagnostics | PARTIAL. Single research stream parser is tested without a live socket. Session, quota, approved live route and worker deployment remain separate. |
| #308 | #317 both exact missing workflows | SELECTED_RESIDUAL_IMPLEMENTED. Existing custody code already on main. |
| #309 | #319 verified ordered saved output | PARTIAL. Source is retrospective and Core blocked; no original batch run or promotion of timing. Full producer/ledger evidence still requires the pinned upstream batch and its authority. |
| #312 | #318 portable daily reader and #319 detached Factory read | PARTIAL. Full operator and research capacity reporting imports require a reviewed composition with #267/#297, with live and publisher evidence distinct. |

## Stage disposition

1. **Governance** — ENGINEERING_ONLY. Protected main, G0 freeze remains separate.
2. **Real-time Binance** — OPEN. #318 wire fixture ready for review; no new live authorization or proof.
3. **Historical/daily publisher** — ENGINEERING_ONLY. C01 QA landed; #318 daily parser/status still review-only. Original acquisition is out of scope.
4. **Core custody/replay** — ENGINEERING_ONLY. #316 prospective replay and #319 detached snapshot validated on fixtures. Independent custody outside this scope.
5. **Scanner/Discoverer/Secretary** — ENGINEERING_ONLY. Both read seams preserve independent source identity, WAIT and no dispatch.
6. **Factory/Lab** — ENGINEERING_ONLY. #319 Experiment/Attempt and read boundary checked. Wider Lab registry contracts not accepted.
7. **Isolated Paper** — ENGINEERING_ONLY. Offline simulator remains in main; #317 CI is review-only. Paper activation remains separate.
8. **Scientific PIT/OOS** — NOT_DUE. No independent known-at, original source rights or holdout release.
9. **Integration/reporting/recovery** — OPEN. Four tested review units; no full Windows operator or candidate-host deployment.
10. **Sustained research** — OPEN. Reuse prior owner evidence. Genuine post-fault recovery and daily continuity have not been verified in this package.

After terminal independent Audit and eligible native approval, recheck active protected-main rules, exact heads, approvals and green required CI after each later authorized merge. The protected check against current main may require a new head and review on the next unit. Rollback uses reverse-order reviewed reverts and the verified predecessor tree boundaries. No source data, secrets, live service, Paper operation or G0 authority entered this repair.
