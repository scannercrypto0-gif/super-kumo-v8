# G4 WP03 — synthetic paired cost sensitivity evidence

This bounded integration uses actual Discoverer candidate projection and attempt ledger, Scanner registration/evaluation and Factory adapter/Lab/immutable store. The Core immutable query call is replaced with a sealed generated 15m fixture. No external market data or execution routes. The synthetic holdout is a hash and execution-order seal, not independently custodied data. All three generated partitions repeat the same price shape at distinct times. No independent market uncertainty or alpha can be estimated. The placebo is a separately evaluated identical-policy null control, not an independent market sample.

- Factory #267: 04b63cc9b406b1f3eae2ac7de5d43ebda26dbfdf, reusable Adapter, Lab and immutable store.
- Scanner #277: ccf57ad3db7e71290a8321840e800136567e3af4, causal signal generation and verifier. Exact integration tests executed locally.
- Discoverer #276: 711fd97a65e3bcc37695ec3f33ce3a97772ee8fd, candidate bridge and attempt ledger.
- Main: 90af9794880cbeb00e7e974bfa906ff5e9666183. All three PRs draft/unmerged at reconciliation.
- Reused staged pins in registration-v2.json: Core fixture interface 59510d302e7bb97a63e3d9603b9fb9f81f8f378a, Scanner B 30c37ae56851488b882998c7fa0085ec51dbfc92, Work235 6acbcc7fc243b132f58170df4c6469bbf7f4eff8.
- The first preregistration commit 84793ba1adb3dcb4c91ca7dc8eb66830c1b2eb04 failed its pre-evaluation equality check because a fixture generated a fresh candidate UUID. No arm was run under that registration. The corrected preregistration 4c9cd9af0fb6ef799ca2aecfe6ab056d8eb9e02d fixes candidate identity and uses Factory's required experiment ID prefix, preserving the original candidate, query pins, hypothesis, costs, sample plan and selection rule. Both revisions precede successful evaluation.
- Execution: isolated local processes run-02 and run-03, 2026-11-10, byte-identical result JSON. No separate G4 CI run. Factory/Discoverer upstream CI remains separately scoped.
- REAL_PIT_OOS_BLOCKED. No qualified original source rights + known-at + independently untouched OOS cohort established. No Core admission or independent Audit request.

## Reproduce

In an isolated git checkout of exact Factory HEAD, use the existing `tools/atlas_factory_h_scanner_ci_stage.py` with only its Scanner SHA substituted to the #277 pin above. That existing script fetches and stages only missing files for Scanner/Core/Work235/Scanner B. Fetch the exact #276 head and extract only `tools/strategy_discoverer_offline` into the disposable checkout. Make these evidence files available from the evidence branch in a separate directory. Install pytest for the reused fixture modules. With `PYTHONPATH=src:.:tests`, run from the Factory checkout:

```bash
python -B /path/to/evidence/run_wp03.py run /path/to/evidence/registration-v2.json /tmp/g4-replay-a
python -B /path/to/evidence/run_wp03.py run /path/to/evidence/registration-v2.json /tmp/g4-replay-b
python -B /path/to/evidence/check_wp03.py /path/to/evidence/registration-v2.json /tmp/g4-replay-a /tmp/g4-replay-b
python -B -m pytest -q tests/test_aql_factory_h_generic_signal_adapter_v1.py tools/strategy_discoverer_offline/tests/test_d_scan_1_candidate_bridge.py -k 'tamper or duplicate or incomplete_query or replay_conflict'
```

Expected result SHA-256 (canonical report): `de2f5ee30444edb37bf1cd96e5bd63265b03c104216c68e456d8b8b8c6b13178`. The registry JSON includes wall clock metadata excluded from the immutable chain digest. Archive contains no broker data or real market bars.
