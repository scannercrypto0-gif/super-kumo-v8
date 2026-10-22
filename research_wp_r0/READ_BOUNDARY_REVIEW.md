# WP-R19 — Verified research read-boundary hardening

Project: ATLAS Quant Lab / AQL-CRYPTO-RESEARCH-001. Recorded `2026-10-22T12:14:00.627993+00:00` (UTC; Asia/Riyadh UTC+03:00). Actual fix/test/measurement evidence, not strategy-performance evidence.

## Actual results
- Parent #38 `51b7d8c82ea05fb9438aeb25d9053eb481c0d9c0`: unified suite **153 tests PASS**, unittest **0.575 s**, subprocess wall **0.766 s**.
- New regression file against unfixed code: **16 tests**, **23 failing assertions across 12 methods**, unittest **0.032 s**. The other methods document valid behavior/limitations.
- After fixes: focused **16 tests PASS**, unittest **0.031 s**; final unified **169 tests PASS**, unittest **0.476 s**, subprocess wall **0.666 s**.
- Executed on Linux/Python 3.12.14 with stdlib only. Full suite ran once before and once after substantive code changes; focused reproduction/fix checks did not repeat the entire suite. No claim of speedup from these different-count runs.
- Five deterministic probes (malformed report, torn report, string-false trust, mutable family reference, mutable manifest reference): rejected **0/5 before -> 5/5 after**. The 16 new test methods additionally cover same-size tamper, file replacement/deletion, anchored rehash/rollback, poison-on-read failure, holdout contamination after restart and valid behavior.

## Confirmed defects and fixes
1. `DurableTrialJournal.report()` previously returned the cached ledger after disk corruption/removal/replacement/rollback without checking it. It now fully restores/verifies the chain/state machine/current file identity and pinned prefix before returning; failure poisons the instance. It does not write/repair/re-sign evidence. No checkpoint authentication or hardware-durability guarantee is invented.
2. `verify_owner_checkpoint(..., independently_trusted="false")` previously accepted the truthy string (and other truthy non-bools) as independent custody. Only literal `True` is now accepted. This is still a caller assertion, never cryptographic proof or actual independent custody.
3. Frozen family/temporal metadata accepted mutable list references despite declared string types. Callers could mutate protocol/source/group references after construction, changing supposedly frozen context/digest. Constructors now reject non-string/empty scalar identity/provenance fields. Candidate and ordered-event tuple snapshots remain unchanged.

No journal wire format, hash algorithm, per-event fsync/write/ACK boundary, strict append validation, holdout permissions or fail-closed confirmation flag changed. No telemetry batching migration. Tests and benchmark assert identical journal bytes/head across equivalent before/after workloads, unchanged counts/fsync and false confirmatory eligibility.

## Measured safety cost — median of 3 temporary-file runs per size
Each sample performs **12 report reads**. Times below are milliseconds for those twelve reads, not per-read SLA or throughput guarantees. All use real per-event `os.fsync`; no fsync mock bypass.

| Attempts / events | Before cached report ms | After verified report ms | Full report replays | Fsync calls, unchanged |
| --- | ---: | ---: | --- | ---: |
| 8 / 11 | 0.214 | 3.710 | 0 -> 12 | 11 |
| 32 / 35 | 0.477 | 11.433 | 0 -> 12 | 35 |
| 128 / 131 | 1.291 | 39.481 | 0 -> 12 | 131 |

At 128 attempts/131 events, verified reporting costs about 3.290 ms/read locally versus 0.108 ms/read cached. This is an intentional integrity cost, **not a performance improvement claim**. Append medians and all three raw samples are in the JSON; host/cache variation prevents attributing append timing changes to this read fix. Benchmark workloads are explicit research measurements, not new operational constants.

Reproduce on a reviewed checkout, with no credentials/network:
```bash
python -B -m unittest discover -s tests -p 'test_research_wp_r*.py'
python -B -m research_wp_r0.read_boundary_benchmark --label reviewed-working-tree
```
Before measurements used parent module content plus one extra EOF LF introduced by local staging. Raw measured and parent SHA-256 values are retained; the exact difference and unchanged Python AST are independently checked. After module hashes match the tested/published working-tree modules exactly. This normalization is disclosed rather than claiming byte-identical parent staging. [Machine-readable results and complete test logs](evidence/r19-read-boundary-results.json).

## Continuity, source review and security boundary
Last owner-actually-submitted baseline remains **AQL-HO-20261021-002 / PR #14**, explicitly owner-confirmed; later observed tool/assistant-created PRs are not silently treated as owner submissions. Current directly submitted execution task is AQL-HO-20261022-001. Reviewed current main/ref, all open PR bodies, issue comments, PR review/review-comment endpoints, relevant main contracts/decisions/risks/tests/protocols/register/log and research architecture proposal #17. Open PR comments were empty; the independently inspected #32 review is a separate ingest track and does not authorize changing it. Other originating chats inaccessible: no exhaustive historical cross-chat audit.
Main is `e4c1f9ec5df9265405c62bab97b2ecc807ceab7b`; #15 merged at that SHA. Issue #1 is CLOSED and its owner final G0 decision is explicit: **G0 APPROVED**. Older START_HERE/STATE/decision snippets still say OPEN; this is a documentary inconsistency, not a reversal of owner signoff. No final state on main or Issue was changed here.
R09 remains mandatory before legacy V7/key reuse; no rotation proof verified. This task executed only newly isolated research/standard-library modules with synthetic fixtures, no legacy code, keys, network client, provider or paid service. AST import inspection found stdlib plus the isolated research namespace only. Test/benchmark child processes used a minimal environment for unified/final/measurement-after executions; no credentials were read or printed.

## Research dependency/adoption and conflicts — proposal only
Research stack follows exact base/head links: #18 -> #19 -> #20 -> #21 -> #22 -> #23 -> #24 -> #25 -> #26 -> #27 -> #28 -> #29 -> #30 -> #31 -> #33 -> #34 -> #35 -> #36 -> #37 -> #38 -> this Draft fix. All existing research PRs remain Draft/unmerged; no adoption is authorized by ancestry or test success. #17 is a separate proposed architecture reference, not merged runtime authority. #32 is an independent ingest proposal based on current main, not an ancestor of research #33–38.
Research vs current main diverges at `ed188f1902d397fe74613dd966c5a3e88b32f8c0`; root governance documents differ. Research code paths and #32's `src/aql/**` have no direct changed-path collision, but future combined testing, package/CI discovery and governance reconciliation are still required. This fix targets exact #38 branch so only its small delta is reviewed; it is not a blind merge/rebase of the backlog or an adoption decision. Consolidated CI/path routing only governs branches where integrated; do not claim global CI cost savings.

| Research PR | Inspected head | Actual base | Status at inspection |
| --- | --- | --- | --- |
| [#18](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/18) | `d790b0fe7b5e07c54f5368f6223a3e555d0df2cb` | `ed188f1902d397fe74613dd966c5a3e88b32f8c0` | Draft/unmerged |
| [#19](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/19) | `04041b1a07ba3c701a3daa33da348ce78a54968b` | `d790b0fe7b5e07c54f5368f6223a3e555d0df2cb` | Draft/unmerged |
| [#20](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/20) | `59507e0ffe4d93ca6d03a5ef9fc6e16d2ace2f76` | `04041b1a07ba3c701a3daa33da348ce78a54968b` | Draft/unmerged |
| [#21](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/21) | `13575869949beb52bea2cb80a422edf18327d1ae` | `59507e0ffe4d93ca6d03a5ef9fc6e16d2ace2f76` | Draft/unmerged |
| [#22](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/22) | `372eca5c18fec6c8d341d6296d586d5cdfb4d668` | `13575869949beb52bea2cb80a422edf18327d1ae` | Draft/unmerged |
| [#23](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/23) | `d64446a0431d952cb501c2bcac20c6d83c4376d4` | `372eca5c18fec6c8d341d6296d586d5cdfb4d668` | Draft/unmerged |
| [#24](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/24) | `3f028b13237863ec33d54176e2d02f5c56fe48b4` | `d64446a0431d952cb501c2bcac20c6d83c4376d4` | Draft/unmerged |
| [#25](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/25) | `d6259aa6436ca03a688b6242d150a1f007f7fa24` | `3f028b13237863ec33d54176e2d02f5c56fe48b4` | Draft/unmerged |
| [#26](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/26) | `1c14b7367c243658acd538442c8e3408fd093758` | `d6259aa6436ca03a688b6242d150a1f007f7fa24` | Draft/unmerged |
| [#27](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/27) | `2c3f5893eeb76093b4962f75c78c2e2ea94d37e8` | `1c14b7367c243658acd538442c8e3408fd093758` | Draft/unmerged |
| [#28](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/28) | `e9a3650c6f3a16e5646e85c0631ae03b591d59af` | `2c3f5893eeb76093b4962f75c78c2e2ea94d37e8` | Draft/unmerged |
| [#29](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/29) | `1c61ee80808413405a5a57edc05bded4ef1928de` | `e9a3650c6f3a16e5646e85c0631ae03b591d59af` | Draft/unmerged |
| [#30](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/30) | `c69965945b50403557d2b18f1e26f955513500f4` | `1c61ee80808413405a5a57edc05bded4ef1928de` | Draft/unmerged |
| [#31](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/31) | `4cd132e344a803e17803cfd2e09b41c7d869ee9a` | `c69965945b50403557d2b18f1e26f955513500f4` | Draft/unmerged |
| [#33](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/33) | `062d9be1ab291a9fa3c110ae74e76b4843c188f3` | `4cd132e344a803e17803cfd2e09b41c7d869ee9a` | Draft/unmerged |
| [#34](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/34) | `387196133152d1b8b7b5fcb54a59b31c99850ab5` | `062d9be1ab291a9fa3c110ae74e76b4843c188f3` | Draft/unmerged |
| [#35](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/35) | `649e66d8ff68fc080acda19f47615c5831cf0685` | `387196133152d1b8b7b5fcb54a59b31c99850ab5` | Draft/unmerged |
| [#36](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/36) | `aa479403d1cf7ba0b450929ee5b4a0f1672023da` | `649e66d8ff68fc080acda19f47615c5831cf0685` | Draft/unmerged |
| [#37](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/37) | `ca24bd10f5d88d1782c94878f0a82908c5c009a9` | `aa479403d1cf7ba0b450929ee5b4a0f1672023da` | Draft/unmerged |
| [#38](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/38) | `51b7d8c82ea05fb9438aeb25d9053eb481c0d9c0` | `ca24bd10f5d88d1782c94878f0a82908c5c009a9` | Draft/unmerged |

Future owner-approved integration must reconcile current main governance/R09 and approve the research sequence separately from the independent #32 pipeline. Prior approvals and immutable evidence preservation cannot be weakened to obtain a passing benchmark. No existing PR/branch/main changed.

## Remaining limitations and stop boundary
- Windows and Python 3.14 for this patch: not executed locally; new CI results must be independently checked before claiming PASS. Historical PR-body CI claims are not this patch's results.
- Fully rehashed **unanchored** history remains unauthenticated; a negative test preserves this limitation. Actual independent checkpoint custody and secret rotation are NOT VERIFIED. No real holdout/provider/time authenticity or strategy alpha proven.
- No physical power-loss/network/live/paid test. Tests restore/reopen files and inject corruption/rollback, not hardware crashes or proof of all adversarial concurrency cases. Existing single-writer/cooperating-lock threat boundary remains.
- Read validation is linear in journal size and raises reporting latency; no unsafe metadata-only cache optimization introduced. Larger-scale/OS measurements and any durability-policy change need separately reviewed evidence/approval.
- No architecture/promotion decision, merge or real trading is performed. Useful confirmed defects in this bounded pass are fixed and tested; next authority gate is owner/independent review of this Draft and the unmerged chain, not another redundant local full-suite run.
