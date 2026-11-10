# G4 current-head engineering closeout

PASS_ENGINEERING, bounded generated-data scope. REAL_PIT_OOS_BLOCKED separately. Independent WP04 verdict pending.

## Source and execution pins

Main 90af9794880cbeb00e7e974bfa906ff5e9666183. Factory #267 04b63cc9b406b1f3eae2ac7de5d43ebda26dbfdf (base a695e262da6787f752a13820f02dd00eef8ef1cd), Scanner #277 ccf57ad3db7e71290a8321840e800136567e3af4 (base a2aa9c195095bcfe852fdc760e385ccb2acf3d5d), Discoverer #276 c568e3b281795f9eef2165c0e6f571b87157a23c (base 149ca90c09b96abb45d3bc2839b657711c9826ac). Draft/unmerged. Refreshed #276 advanced beyond a0dd52f7f9fb1d82fb2651be69d5dcba2c074f5b referenced by the order. Factory base tree 26a87eee2d068a1a5e3550195eb590e8e079c17f, Discoverer tree ea7dd593ccaeae16d9c9eae826a3815c62cd5e86. Disposable staged local overlay tree b2aab6a0715153f46babb46ea8e6ad0d0fb5bfa9. Actual Scanner blob 0c381e358c45dd9031d4e2fa00b1ca9d956f3858; Factory adapter e8bba726487cafb2c15abdea893d43867ad13ed6; current Discoverer Factory seam 327d5799cafeacc6b5e3471907f297bd31fbba23.

Pre-execution freeze commit 95eebcac704df284f4ce4a9aaa3e64033e1ecea8. Previous 10-variant baseline commit 6aab422f523319f8494a83b21f1591423ef393f1 reused as driver, with no change to that evidence. The new execution uses persisted latest #276 checkpoint, revalidates frozen candidate, nomination, family, plan, protocol and Scanner binding, seals a shared generated source manifest across nomination and query partitions, and enters all three candidate-generation rows in Factory E. It links all ten scheduled variant IDs and their exact Factory H package digests to the Factory E generation receipt. Same-ID replay is a duplicate check, not an eleventh trial. The synthetic Core245 ID is a fixture tag, not a real Core245 receipt. Core253-shaped immutable query is mocked at the Scanner IO boundary, while the actual scanner, strategy, evaluator, Factory and SQLite code run. The initial fixture setup rejected a list/tuple shape before freeze; corrected it before the preregistered evidence commit. No arm ran before that commit.

## Reproduction

Use the exact isolated Factory/Scanner/Core/Work235/Scanner B staging recipe from the prior WP03 README at commit 6aab422f523319f8494a83b21f1591423ef393f1, then extract only tools/strategy_discoverer_offline from the current exact #276 pin above. The prior staged fixture also includes the pinned Core H Secretary module at 99c27ea2c1a4d41aaae361141301a8a9ea3b33c3; the closeout does not call it. Copy the prior run_wp03.py and check_wp03.py beside this closeout.py, byte-for-byte. From the isolated staged checkout with pytest 9.1.1 and PYTHONPATH=src:.:tests, create a disposable copy of frozen-v2. Rebuild its SQLite checkpoint using DurableDiscovererCheckpoint(.../g4-discoverer.sqlite).append_ledger(checkpoint.json["entries"]), and verify read_latest_ledger() equals checkpoint.json. This exact reconstruction was checked. Then:

```bash
python -B /path/to/evidence/closeout.py run /path/to/frozen-v2 /tmp/g4-closeout-a
python -B /path/to/evidence/closeout.py run /path/to/frozen-v2 /tmp/g4-closeout-b
cmp /tmp/g4-closeout-a/closeout.json /tmp/g4-closeout-b/closeout.json
python -B /path/to/evidence/check_wp03.py /path/to/frozen-v2/registration.json /tmp/g4-closeout-a /tmp/g4-closeout-b
python -B -m pytest -q tools/strategy_discoverer_offline/tests/test_g4_factory_acceptance_seam.py tests/test_aql_factory_h_generic_signal_adapter_v1.py -k 'test_g4_factory_acceptance_seam or tamper or incomplete_query or replay_conflict'
```

Local exact run IDs run-a and run-b on 2026-11-10; receipts byte-identical. Canonical closeout SHA 467cafcb8ad8cd82c59abb6e563d6f6312b16d54c302c00e9daa9343c77784bf. Full closeout includes local runtime version in environment identity, so reproduce on the same platform/Python version to match the full digest. No new integrated cross-platform CI. Existing #276 exact-head CI 42812639698, 42812640014 and 42812639792 remain separate.

| Owner science predicate | Disposition |
| --- | --- |
| Paired gross, market/taker modeled net, stress, cost once | TESTED: equal gross/entry/exit/risk, 6 vs 18 bps modeled friction, delta -12 bps per modeled outcome; separately registered identical-policy null placebo delta 0. |
| Passive maker touch, nonfill/partial/queue/adverse selection | TESTED: false maker-touch claim rejected. UNSUPPORTED_BY_SYNTHETIC_FIXTURE: passive queue/partial/adverse-selection estimates and observed executions. One UNKNOWN per ordinary arm and 64 UNKNOWN/zero modeled outcomes in the missing control, kept explicitly. |
| Exit A/B/C ranking | UNSUPPORTED_BY_SYNTHETIC_FIXTURE: fixed existing rule used identically; no staged exits or intrabar chronology evidence. |
| Automatic research validity and multiplicity | TESTED for one frozen hypothesis, fixed family budget, full attempt/variant census, no tuning or promotion. Statistical multiplicity and market uncertainty BLOCKED for scientific inference; one generated shape repeated at different times. |
| Independent real PIT/OOS | BLOCKED: authentic permission/rights, independently witnessed decision-time availability and untouched genuine cohort not established. Synthetic holdout is logical hash and execution-order control only. |

No live/Secretary/Paper routing, G2 observer changes, merge, G0, or owner promotion.
