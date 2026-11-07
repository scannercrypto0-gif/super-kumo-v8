# Factory F4 — private original-cohort E2E single operator command

PM assignment: https://github.com/scannercrypto0-gif/super-kumo-v8/pull/267#issuecomment-6657099331

**Never execute using public CI or invented original OHLCV.** Core F2 must supply actual private RAW #211, warehouse #226, distinct #245/#253 readbacks. Owner F1 10 ACCEPTED_PREFLIGHT and retained Feb/Aug alone do NOT demonstrate F2 source admission. **Update 2026-11-05:** the owner subsequently supplied a sanitized actual private F2 run report with 10 new admitted months and 29,376 native 15m bars, report SHA `daf1208bf824e58040858a817c709f7943c19668dc23ce3fd3b0368e01156f40`. This is owner-reported, not independently re-read from the private E: disk here; never substitute the report headline for complete report JSON and per-month evidence. Independent signed or externally trusted research-only Scanner policy approval, Core Source ACK, and separate Secretary StrategyApproval must be obtained and verified before Factory executes.

## Private JSON input contract

Module: `research_wp_r0.aql_factory_f_private_original_cohort_v1`, schema `aql.factory.f.private-original-cohort-input.v1`.

Input JSON is SHA-sealed: `sha256` equals SHA256 of all other keys JSON-serialized sorted/compact with `ensure_ascii=True` and `allow_nan=False`.

- New immutable `experiment_id` and `batch_id`, not a reused blocked batch ID.
- `market=BINANCE:SPOT:USDT`, `symbol=BTCUSDT`, `timeframe=15m`, `policy_id=btc-spot-15m-retrospective-non-pit-v1`, exact `policy_draft_sha256`.
- Authentic Core F2 `core_f2_report` and `core_f2_report_sha256` (per-month original SHA, checksum, RAW, warehouse, native #245, local #253, dual map, bar census).
- Separately independently verified `source_ack_sha256`, `independent_policy_approval_sha256`, `strategy_approval_sha256`; no one receipt substitutes another.
- `source_manifest_sha256`, sorted `admitted_months` (no Feb/Aug), `core_245_query_sha256`, `core_253_query_sha256`: canonical ordered monthly dual-query SHA maps.
- Canonical AQL `strategy` (StrategyDefinition.to_dict), `strategy_definition_sha256`, `config_sha256`, `code_sha256`, `environment_sha256`.
- `attempts`: exactly **20** complete per-cohort attempt ID/candidate/month/state/source SHA entries (2 frozen Scanner strategies × 10 F2 admitted new months), with two distinct candidate identities per admitted month. States SELECTED, REJECTED, UNKNOWN, QUARANTINED, INELIGIBLE. Exactly one selected SOURCE-BOUND trial for this one bounded real Lab execution **only after independent policy and Secretary approval**. Preserve the original 24-attempt 12-month audit denominator separately: 4 February/August rows remain UNKNOWN/NOT_EVALUATED, never quietly dropped or marked evaluated; never overwrite the prior blocked UNKNOWN batch.
- `trial_packet`: existing `aql.factory.historical-rule-projection.v1` input: **real** verified native 15m closed original bars for ONE F2 admitted month (max 40,000), 53 fixed research trial records, selected attempt, strategy AST and indicators, research train/embargo/holdout, native UTC grid, source SHA, and explicit decimal string costs: fee entry/exit, spread entry/exit, slippage entry/exit and spot funding zero. Holdout stays SEALED_UNOPENED.

Independent witness JSON is a different `aql.factory.f.external-independent-trust-witness.v1` record with exact `factory_input_sha256`, `trust_class=OUT_OF_BAND_INDEPENDENT_APPROVER`, distinct Core F2/Source ACK/Scanner approval/StrategyApproval/native/local query SHAs, `issuer_reference`, `authorization_reference` and sorted `approved_months`. The --trusted-witness-sha256 must come from an independently authenticated external custody/policy/Secretary channel, **not the party who constructed the input**. Input SHA and witness SHA matching alone do not verify an issuer signature or demonstrate that bars were extracted from the private original ZIP; the custodian must independently attest actual original byte-to-bar membership.

## One bounded PowerShell command (approved private Windows executor only)

```powershell
Set-Location 'E:\ATLAS\repo'
& 'E:\ATLAS\.venv\Scripts\python.exe' -m research_wp_r0.aql_factory_f_private_original_cohort_v1 `
  --input-json 'E:\ATLAS\private\historical\f4\actual-input.json' `
  --trusted-witness-json 'E:\ATLAS\private\historical\f4\independent-witness.json' `
  --trusted-witness-sha256 '<independently verified 64-char SHA>' `
  --role-attestations-json 'E:\\ATLAS\\private\\historical\\f4\\role-attestations.json' `
  --independent-trust-registry-json 'E:\\ATLAS\\private\\historical\\f4\\independent-keyring.json' `
  --trusted-now-utc '<independently trusted UTC, YYYY-MM-DDTHH:MM:SSZ>' `
  --results-store 'E:\ATLAS\private\historical\f4\results.sqlite' `
  --sanitized-out 'E:\ATLAS\private\historical\f4\factory-f4-sanitized-result.json'
if ($LASTEXITCODE -ne 0) { throw 'FACTORY_F4_FAIL_CLOSED' }
```

## Evidence output / limits

On real accepted input, the code invokes existing AQL indicator AST rule evaluation, next-open cost modeling and unknown-on-intrabar-stop barrier, then registers immutable metadata in the existing Factory E SQLite store with idempotent replay. Sanitized receipt contains all distinct SHA parents, independent source/policy/strategy ACK, Factory consumer ACK, lab result SHA, experiment SHA, modeled count, unknown count, fee/slippage assumptions, NON_PIT, zero trades, and no private OHLCV. Repeat same input to check REPLAY_IDENTICAL, use new batch ID for a new source-version cohort.

**Not executed**: source F2 original admission report, externally trusted policy approval, distinct Secretary source/strategy ACK and independent original-bar membership not available to this GitHub agent. Current Scanner F3 request is PENDING, not approval; Feb/Aug inventory only. No PIT, no Paper, no holdout, no merge/G0/trading. Final F5 independent Audit only after a source-backed real execution and exact private evidence.
## Exact F2 handoff and one final report rule

Core handoff: https://github.com/scannercrypto0-gif/super-kumo-v8/pull/275#issuecomment-6658725082 . Private F2 report SHA `daf1208bf824e58040858a817c709f7943c19668dc23ce3fd3b0368e01156f40` (owner-supplied); 10 admitted months, 29,376 bars, February/August inventory-only, historical PIT NOT_ATTESTED. The Windows RawVault lock/fsync branch is separate and should not be assumed merged into Core #275. Do NOT rerun populated warehouse/vault or invent a second store. Keep exact private source/approval proof and Lab receipt for **one** consolidated Audit #256; sanitized output only on GitHub. A later F2 report for a different exact source SHA creates a NEW immutable experiment/cohort ID.

## 2026-11-07 F4 authority hardening and full census

The private command now requires a **separate independently provisioned five-role Ed25519 key registry** and five role-signed attestation envelopes. Roles: SOURCE_CUSTODIAN, RESEARCH_POLICY_APPROVER, CORE_SOURCE_SECRETARY, CORE_STRATEGY_SECRETARY, INDEPENDENT_EVALUATOR. Each attestation `aql.factory.f.external-role-approval.v1` contains schema, role, key_id, approver_id, subject_sha256 = SHA of the entire private F4 input, issued_at_utc, expires_at_utc and Ed25519 signature_hex. The independently controlled registry maps each role to its distinct key_id, approver_id, public_key_hex and enabled flag. It must NOT be generated from F4 input or GitHub test fixtures, and the independently trusted UTC time is mandatory. The command checks five unique roots/approvers/signatures and temporal validity before issuing its own Consumer ACK or evaluating Lab. A self-created SHA-only witness no longer suffices. Original Scanner F3 Ed25519 policy verification and private source byte-to-bar membership still require independent operator checks.

The Factory E immutable experiment now carries **24 attempts** in one final census: exactly 20 source-admitted candidate×month identities plus 4 February/August `UNKNOWN` rows with special `INVENTORY_ONLY_NOT_READBACK` *metadata placeholder* SHA, not a source archive hash. The sanitized report includes `full_attempt_count=24`, `full_attempt_census_sha256`, `feb_aug_inventory_only_unknown=4`. The F4 private run stays WAIT unless a real original-source strategy-selected and separately Secretary-approved input exists. Retrospective NON_PIT, no execution/Paper/G0.
