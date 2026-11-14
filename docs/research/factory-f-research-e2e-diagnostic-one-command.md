# ATLAS Factory — Owner-private RESEARCH_E2E_DIAGNOSTIC single run

Authorized owner instruction: https://github.com/scannercrypto0-gif/super-kumo-v8/pull/267#issuecomment-6703070403

## Boundary: diagnostic vs signed F5

**This is a distinct limited local-trust diagnostic, NOT F5 source custody or a policy/strategy authorization.** It imports the existing AQL causal retrospective rule kernel and immutable SQLite Results Store, **not** the five-role F5 gate. It cannot issue Factory Consumer ACK, Source ACK, StrategyApproval, signed policy, SELECTED authorization, Paper/live orders or scientific PIT.

Local operator must preserve canonical existing RAW #211→Warehouse #226→native Core #245/local #253; never rerun F2 or write original ZIPs. Owner reported 10 actual admitted 2024 BTCUSDT Spot native15m months / 29,376 bars in Core F2 report SHA `daf1208bf824e58040858a817c709f7943c19668dc23ce3fd3b0368e01156f40`. Feb/Aug are **not admitted**, only inventory. Operator must **independently** compare actual private query readback/bar origin and full original report against the same immutable source bytes. An input SHA alone cannot establish publisher rights/issuer origin.

## Exact operator input: private SHA-sealed JSON

Python module `research_wp_r0.aql_factory_f_research_e2e_diagnostic_v1`. Input schema `aql.factory.f.research-e2e-diagnostic-input.v1`. Seal JSON with the current AQL `digest()` canonical SHA of all non-`sha256` fields. All fields mandatory:

`schema`, `sha256`, `experiment_id` prefixed `DIAG-F4-`, `purpose=RESEARCH_E2E_DIAGNOSTIC`, `local_source_mode=OWNER_PRIVATE_READ_ONLY`, `market=BINANCE:SPOT:USDT`, `symbol=BTCUSDT`, `timeframe=15m`, Core `core_f2_report_sha256`, `source_manifest_sha256`, `core_245_query_sha256`, distinct `core_253_query_sha256`, `operator_local_source_readback_sha256` from actual owner-private read-only source, immutable `strategy_definition_sha256`, `config_sha256`, `code_sha256`, `environment_sha256`, `strategy` canonical definition, `admitted_months` sorted ten (every 2024 month except Feb/Aug), `attempts` full 24-row population, `source_coverage`, `trial_packet` canonical existing historical rule AST input.

`source_coverage`: exactly `new_admitted_months=10`, `new_admitted_bars=29376`, `retained_inventory_months=[2024-02,2024-08]`, `retained_inventory_status=INVENTORY_ONLY_NOT_READBACK`, `historical_pit=NOT_ATTESTED`, `source_rights_assurance=LOCAL_OPERATOR_DECLARED_NOT_INDEPENDENT`.

`attempts`: 2 frozen strategies × 10 admitted months (20 UNKNOWN or REJECTED) + 2 strategies × 2 not-yet-admitted Feb/Aug (4 UNKNOWN), each with unique `attempt_id`, `candidate_id`, month, state and source receipt SHA. No historical SELECTED or positive approval inside diagnostic. Never mark Feb/Aug as admitted.

`trial_packet`: input to existing `aql.factory.historical-rule-projection.v1` kernel. Owner extracts **real** native 15m consecutive FINAL closed bars for exactly one admitted month from actual original Core #253 readback and compares to native #245. `source_kind=ORIGINAL_UNVERIFIED`, `availability=RETROSPECTIVE_NON_PIT`, `execution_authority=NONE`, `holdout=SEALED_UNOPENED`, `width_ms=900000`, `market=SPOT`, `source_manifest_sha256` exact input parent, `source_bytes_sha256` exact owner-local readback parent, `strategy` exact canonical definition, `diagnostic_month` one admitted month. Existing kernel also requires fixed 53-trial research population, selected trial **as computational focus only** (not strategy authorization), opportunity census, complete indicator/rule AST, risk, train/embargo/holdout, next-open exit, nonnegative decimal entry/exit fees + spread + slippage and spot funding zero. Every bar `known_at_ms=null`; no scientific known-at/PIT claim. Next-open decision requires bar close inside training cutoff; no holdout/future bars.

## The ONE private PowerShell operator command (after local authentic readback)

```powershell
Set-Location 'E:\ATLAS\repo'
& 'E:\ATLAS\.venv\Scripts\python.exe' -m research_wp_r0.aql_factory_f_research_e2e_diagnostic_v1 `
  --private-input-json 'E:\ATLAS\private\historical\diagnostic\diag-f4-input.json' `
  --diagnostic-store 'E:\ATLAS\private\historical\diagnostic\diag-f4.sqlite' `
  --sanitized-out-json 'E:\ATLAS\private\historical\diagnostic\diag-f4-sanitized.json'
if ($LASTEXITCODE -ne 0) { throw 'PRIVATE_DIAGNOSTIC_WAIT' }
```

Run from the local checkout that includes the Factory Draft #267 diagnostic code; use a separate **new diagnostic experiment ID** and a private SQLite database, not the signed F5 store/experiment ID. **Do not upload real OHLCV or the private raw files, credentials or actual signer keys** to GitHub. A positive diagnostic outcome must be witnessed by an approved private operator on real read-only Core #245/#253 source; GitHub CI covers only missing-data negatives.

## Exact success and failure outputs

Only after a real private run, `diag-f4-sanitized.json` returns `aql.factory.f.research-e2e-diagnostic-report.v1`, `status=DIAGNOSTIC_ONLY_NOT_F5`, full `attempt_count=24`, `feb_aug_inventory_unknown=4`, `lab_sha256`, `result_sha256`, `experiment_sha256`, `input_sha256`, original Core F2 and readback SHA, modeled outcome and unknown counts, explicit cost assumptions, SQLite layout and `store_status=STORED_IMMUTABLE` initially. Rerun exact same packet → `REPLAY_IDENTICAL` with stable experiment/lab/result SHA. New data or config demands new experiment ID. Tamper or any future/unclosed bars must fail closed. `factory_consumer_ack_sha256=null`, `source_ack_sha256=null`, `strategy_approval_sha256=null`, `independent_policy_approval_sha256=null`, trading `NONE`, Paper `NOT_ACTIVATED`, orders and positions zero. This diagnostic **cannot** be promoted into a successful F5 source, strategy or scientific judgment.

**At current GitHub-only inspection:** the owner's original E: readback and exact private input JSON are not available here. Therefore actual diagnostic status **PRIVATE_WAIT**, no local Lab PASS, no F5 Audit, no G0, no PR merge and no trades. No replacement warehouse or repeated F2.