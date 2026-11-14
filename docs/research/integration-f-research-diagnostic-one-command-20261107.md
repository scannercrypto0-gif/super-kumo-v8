# ATLAS RESEARCH_E2E_DIAGNOSTIC — one-command owner-private operator handoff

**Owner decision:** provisional B, [ADR-F-DIAG-01](./adr-f-research-e2e-diagnostic-boundary-20261107.md). This is **not signed F5**, G0, Paper, trading, third-party issuer source authorization or scientific PIT. All existing signed Core F5/Scanner F3/Factory F4 approval code remains fail-closed. No second warehouse or original F2 ingest. Discoverer optional, never blocks mandatory route.

## 0. Exact assembled code required

Run in a **local assembled checkout** with Integration `tools/atlas_f_research_diagnostic_operator.py` and the **exact owner module versions** staged by the existing `.github/workflows/atlas-package-e-combined-gate.yml` overlay recipe (or an equivalent byte-identical owner-controlled assembly). The CLI independently rechecks Git blob plus runtime SHA256 identities of these files before opening owner-private source:

- Core: `research_wp_r0/aql_core_f_research_diagnostic_query_v1.py`, Git blob `ee129da558867d195258fc6507fba93be2fd6066`
- Scanner: `tools/scanner_strategy_f/research_e2e_diagnostic.py`, Git blob `1878666e92b641c49a93330fc21afd084668e1e8`
- Factory: `research_wp_r0/aql_factory_f_research_e2e_diagnostic_v1.py`, Git blob `65b74ef25bc9fc223e490fdc81d0c2fe93767c1d`

**Stop if a module is missing or a blob differs.** Do not run the CLI directly from an unassembled Integration-only checkout. Pin and verify source HEAD at execution time, don't assume any open PR merged. Existing Windows Core RawVault disposable cross-process lock/fsync/ACL test and latest combined engineering checks are separate; they do not prove an owner-private Lab run.

## 1. Private operator input

Create a local JSON manifest, not a GitHub attachment, at e.g. `E:\ATLAS\private\historical\diagnostic\operator-manifest.json`:

```json
{
  "schema": "aql.integration.f.research-e2e-diagnostic-operator.v1",
  "owner_operator_authorized": true,
  "warehouse_root": "E:\\ATLAS\\private\\warehouse",
  "vault_root": "E:\\ATLAS\\private\\raw_vault",
  "core_f2_report_path": "E:\\ATLAS\\private\\historical\\f2\\actual-f2-report.json",
  "scanner_policy_draft_path": "E:\\ATLAS\\private\\historical\\diagnostic\\frozen-policy-draft.json",
  "scanner_proposal_path": "E:\\ATLAS\\private\\historical\\diagnostic\\frozen-proposal.json",
  "scanner_approval_request_path": "E:\\ATLAS\\private\\historical\\diagnostic\\frozen-approval-request.json",
  "frozen_work_specs_path": "E:\\ATLAS\\private\\historical\\diagnostic\\frozen-work235-specs.json",
  "factory_diagnostic_input_path": "E:\\ATLAS\\private\\historical\\diagnostic\\factory-input.json",
  "diagnostic_store_path": "E:\\ATLAS\\private\\historical\\diagnostic\\fresh-diagnostic.sqlite",
  "sanitized_output_path": "E:\\ATLAS\\private\\historical\\diagnostic\\sanitized-diagnostic.json"
}
```

Paths shown are **examples**, not evidence the files exist; use exact actual owner-private locations. The full private F2 report must match SHA `daf1208bf824e58040858a817c709f7943c19668dc23ce3fd3b0368e01156f40` and ten 2024 original admitted months (29,376 native 15m bars), with Feb/Aug inventory-only. Preserve RAW #211, one Warehouse #226, native #245 and local #253 **distinct** query parents. Source roots must already exist. Output files must **not** already exist and must be outside RAW/warehouse directories. The `true` value is **owner-local operator authorization only**, never an independent Ed25519 research policy approval.

`frozen-work235-specs.json` is the actual immutable two-strategy Work235 receipt list; policy/proposal/request must be the matching frozen Scanner research-only forms. The separate `factory-input.json` is the existing Factory `aql.factory.f.research-e2e-diagnostic-input.v1` schema documented in [Factory operator runbook](https://github.com/scannercrypto0-gif/super-kumo-v8/blob/7a0d26641f2a97b23aeaf5bfa5d2e6593ec74978/docs/research/factory-f-research-e2e-diagnostic-one-command.md): full **24** rows, two *same frozen strategy IDs* for each of ten admitted months plus Feb/Aug four UNKNOWN, one **UNKNOWN** computational focus attempt on one admitted month; the focus is *not* historical `SELECTED`. Include actual original Core-selected month closed-bar subset and the real ZIP/warehouse/native/local SHA parents, one valid fixed 53-trial AST envelope, explicit fee/spread/slippage, retrospective NON_PIT and sealed holdout. No synthetic positive or caller-invented checksum is accepted as a real execution.

## 2. ONE owner-authorized local run

In the **exact assembled** and locally owner-authorized Windows checkout:

```powershell
Set-Location 'E:\ATLAS\repo'
& 'E:\ATLAS\.venv\Scripts\python.exe' -m tools.atlas_f_research_diagnostic_operator `
  --operator-manifest 'E:\ATLAS\private\historical\diagnostic\operator-manifest.json' `
  --owner-private-authorized
if ($LASTEXITCODE -ne 0) { throw 'ATLAS_RESEARCH_DIAGNOSTIC_PRIVATE_WAIT' }
```

This single command orchestrates **ten actual Core F2 pinned RAW/warehouse/native245/local253 readbacks** (not reingest), **two frozen Scanner AST strategies across ten months = twenty diagnostic-evaluated attempts**, **Feb/Aug four UNKNOWN**, and **one Factory causal focus Lab computation** on true original bars, then stores it in a **fresh separate SQLite v2** namespace and validates immutable `REPLAY_IDENTICAL` on a second internal call. It checks original-bar OHLCV equality between the Core readback and Factory focus; dynamic closed 15m bar cutoff; user strategy digest and exact 24-attempt identity; wrong SHA, resealed source/authority promotion and future/unclosed bar negatives. It emits a **sanitized SHA-only** `aql.research-e2e.diagnostic.v1` receipt. It does **not** publish any actual bar, ZIP or private key or produce a signed F5 ACK.

**Strict scopes:** 20 Scanner strategy-month signal evaluations do **not** imply 20 Factory full backtests; Factory runs one bounded computational focus trial on one admitted month. All `selected`/ACK/null/PIT/trading authority boundaries stay nonpositive. That is what scoped diagnostic PASS means; no strategy profitability determination.

## 3. What a PASS or WAIT actually means

- **`ENGINEERING_PASS_PRIVATE_NOT_RUN`**: bounded GitHub CI contract / negatives succeeded, but no authorized actual original `E:` execution. No diagnostic historical PASS.
- **`PRIVATE_WAIT`**: absent or mismatched private input, no authority to use local source, wrong owner blob, source/query checksum mismatch, tampered/future trial, non-replay or any other fail-closed reason. The CLI prints only a sanitized error **code**, no source bytes or private paths.
- **`RESEARCH_E2E_DIAGNOSTIC_PASS`**: only emitted if the actual owner-private original F2 readback, twenty Scanner signals, single causal Factory Lab focus, v2 sealed restart/replay and negative tests all pass in the approved environment. Requires operator review of the private data source binding. **Not** `AUTHENTIC_F5_LAB_PASS`.

An independent F5 requires genuine out-of-band custodian rights, research policy signer and evaluator plus distinct Core Source ACK/StrategyApproval and Factory Consumer ACK, and one independent Audit #256. A diagnostic receipt is never input authority for signed F5.

## 4. One sanitized GitHub handoff only after the private run

Owner may share **only** the `sanitized-diagnostic.json` and appropriate source/role provenance references that do not expose E: paths, keys, raw OHLCV or ZIPs. Integration verifies exact module blob SHA and input/output digests, bar census and twenty/four attempt denominator, causal result cost metadata, `REPLAY_IDENTICAL`, negative-case list and NON_PIT/zero-authority fields. Then reports separate `RESEARCH_E2E_DIAGNOSTIC_PASS` (if actually proved) and F5 still `BLOCKED_EXTERNAL_INPUT`; Audit #256 remains scoped to **signed F5**, not diagnostic acceptance.
