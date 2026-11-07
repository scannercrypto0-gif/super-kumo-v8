## Core F5 — authority evidence and exact dependency contract (2026-11-07)

This section is an **engineering readiness contract**, not a Source ACK, StrategyApproval, Factory ACK or external legal attestation. All values below must be verified against source artifacts and exact HEADs, never assumed because an owner-local run or CI was green.

### Current immutable owner-local F2 evidence (do not rerun private warehouse/vault)

* BTCUSDT native 15m 2024: 10 admitted original months and 29,376 bars; 2024-02/08 remain **inventory-only**. This is an **owner-reported local execution**, not a source signature independently witnessed in GitHub.
* F2 report SHA: `daf1208bf824e58040858a817c709f7943c19668dc23ce3fd3b0368e01156f40`.
* Manifest SHA: `f559c82c2c3827382338ab8f84f4a71a1e6705e08105b9b1bdbfaceb3bcbc8b7`, fresh F1 coverage ledger SHA: `557c38ecb58d9c0c22784ee105c6cb0a29bf2d4dc2ba44f5ed4e2a08c1a89862`.
* Canonical JSON authorization SHA `ced74dade0ee151eff61109bddb912c5203cbb4d091f6ba77545cb262e332439` **differs** from raw authorization *file bytes* SHA `a954b81e67cf731b19aba73d916dda59c80a55ed93442d6abab086972e18cbef`. Integrity/owner permission must not be misrepresented as issuer-authenticated historical provenance.

### RawVault Windows lock/fsync — exact assembled Core release gate

Core F PR #275 now includes a **selected exact-source assembly**, not a wholesale merge of the divergent Windows branch:

| Module | GitHub Git blob SHA | Source |
|---|---|---|
| `tools/raw_vault_offline/vault.py` | `6b5bcc1d684088934f5ed7110064380b8d2bc0cd` | `core/rawvault-windows-lock-20261105` commit `e368dd491a0d80618bdc6c6e8f731a195d763dda` |
| `tools/raw_vault_offline/schema.py` | `ee36d05f4678a61d2163ce3b2e0e6d612a24c01a` | Same pinned source |
| `tools/raw_vault_offline/__init__.py` | `838f1ca49eb39f9f2ab846de3e0cf57321fb4e78` | Same pinned source |
| `tools/raw_vault_offline/tests/_helpers.py` | `23ce71b366812815b1d722dd1a8956891f248e42` | Same pinned source, tests only |

The original Windows-fix commits `cd720cf7549719639add7180b9321067358607d0` and `e368dd491a0d80618bdc6c6e8f731a195d763dda` stay on a **separate, unmerged** branch. Only the exact upstream source blobs were copied into the existing Core F draft tree; unchanged canonical file formats, path and API. Never infer inclusion from PR #271 until **its** final assembled checkout is independently hashed.

**Release verifier:** `tests/test_aql_core_f5_windows_rawvault_release_v1.py`, included in `.github/workflows/aql-core-f-bulk-manifest.yml`. It checks the actual Python import `__file__` and `git hash-object` of the deployed source, on Windows with repository line-ending filters, against `6b5bcc1...`. On **disposable** roots, it runs real `_vault_lock` cross-process exclusion, timeout, forced process termination + kernel release, NTFS strict directory ACL, fsync call path, restart/committed object readback and same-object identity replay. It is never pointed at `E:\ATLAS\private\raw_vault` or `warehouse`. The Windows-test-only signature verifier uses ephemeral keys, not real source rights.

Commands for an isolated checked-out Core F tree (no original data):
```powershell
python -m unittest discover -s tests -p 'test_aql_core_f5_windows_rawvault_release_v1.py' -v
python -m unittest discover -s tests -p 'test_aql_core_f5_secretary_authority_v1.py' -v
```

### Core F5 read-only authority interfaces — no ACK minted

`research_wp_r0/aql_core_f5_secretary_authority_v1.py` provides these **read-only validators**; no signing private keys, trust registry or live positive historical receipt are shipped in the repo:

* `expected_source_payload(...)`: exact original owner F2 report SHA, 10/29,376 census, Feb/Aug inventory-only, authorization JSON hash and the **distinct** monthly source ZIP, warehouse receipt, #245 native and #253 local query parents.
* `verify_source_ack(...)`: requires full sealed owner F2 report, owner-private matching authorization JSON, **independent Ed25519 SOURCE_CUSTODIAN** witness on the exact source payload digest, and separate Ed25519 `CORE_SOURCE_SECRETARY` signature using a configured independent trust registry, UTC and issuer role. A caller-supplied `source_verified=True` flag is not accepted.
* `verify_scanner_nomination(...)`: verifies canonical sealed `aql.scanner-f.original-research-nomination.v1`, explicit `NOMINATED_RESEARCH_ONLY`/not-selected, source warehouse and separate native/local query digests, exact F2, frozen strategy definition/DNA/native15m config, cutoff and research-only constraints. SHA sealing is **not** itself independent evidence of original execution.
* `verify_strategy_approval(...)`: re-runs Source ACK verification, checks the exact sealed Scanner nominee, requires separately signed **RESEARCH_POLICY_APPROVER** and **INDEPENDENT_EVALUATOR** role witnesses on the precise approved policy and evaluation receipt SHAs, checks issuer-key/approver uniqueness across all five roles and verifies the distinct `CORE_STRATEGY_SECRETARY` Ed25519 signed approval. It cannot synthesize genuine trading or Lab permission.
* `pending_authority()`: `NOT_ENQUEUED` / null source, strategy and Factory ACK SHAs, historical PIT `NOT_ATTESTED`, trading `NONE`.

Core signs **nothing**: each external role witness uses Factory-compatible `aql.factory.f.external-role-approval.v1` with `schema, role, key_id, approver_id, subject_sha256, issued_at_utc, expires_at_utc, signature_hex`. Actual authorized key IDs/public keys/approver roles, independently trusted UTC, expiry and revocation/disabled role state must be supplied **out-of-band**. Core signer receipt schema has `schema, issuer_role, approver_identity, key_id, not_before_utc, expires_at_utc, signature_scheme=Ed25519, signature, research_scope, historical_pit, trading_authority, source_ack_sha256, payload_sha256`. **Do not** use ephemeral unit-test signer keys, caller-provided trust roots or a current HTTPS publisher checksum as an independently authorized issuer.

Required private operator evidence packet: the complete original **sanitized F2 JSON report** with original report digest, the original private authorization document (do not publish legal/secrets), separate legal rights and source issuer provenance reference, explicit custodian subject-attestation and externally pinned trusted public keys/role registry, trusted timestamp and revocation evidence; signed Scanner policy/activation proof with exact frozen Work235 strategy identities, actual read-only original Core #245/#253 query and closed-bar evaluator observation/indicator receipt, genuine independently signed evaluator/nominated research-only receipt. Factory separately issues its own Consumer ACK and validates the same graph. If any artifact is missing, fail closed with `NOT_ENQUEUED` and `BLOCKED_EXTERNAL_INPUT`.

**Important limit:** verification of a signed receipt SHA does not itself demonstrate that the 2024 original bytes were independently inspected, that the evaluator actually ran on them, that the rights grant is legally sufficient, or that the signer authority registry was independently provisioned. Original-source witness + true policy/evaluator verification must happen in authorized private runtime, and Integration #271/Factory #267 must independently replay the actual causal historical Lab chain before a positive F5 claim. Retrospective `NON_PIT` always remains non-PIT.

### Distinct real authority graph (NOT auto-issued by Core F2)

`F2 source custody/rights evidence` → **independent Core Source Secretary ACK** → **independently authorized, signed research policy + authentic strategy-specific evaluator decision** → **independent Core Strategy Secretary Approval** → **Factory Consumer ACK** → **research-only Lab gate**. All links must point to their actual signed parent receipts and independently verified issuer/trust root.

Scanner #277 (re-fetch exact latest HEAD at assembly) documents the pending interface in `tools/scanner_strategy_f/secretary_ack_requirements.py`:
* `aql.core.f.historical-source-ack.v1` issuer role: `CORE_SOURCE_SECRETARY`; separate from the F2 report itself.
* `aql.core.f.historical-strategy-approval.v1` issuer role: `CORE_STRATEGY_SECRETARY`; only after independently authenticated evaluator and strategy/policy approval; must not be self-signed from Scanner's proposal.
* `aql.factory.f.consumer-ack.v1` issuer role: `FACTORY`; cannot be auto-emitted by Core.
* Required immutable parents of strategy-specific proposal: `strategy_decision_sha256`, `source_bound_census_sha256`, `policy_approval_sha256`, `core_f2_report_sha256`, `external_source_authorization_sha256`, strategy ID/version/definition digest/native15m config digest, source ZIP SHA, warehouse receipt SHA, **distinct** `core245_native_query_sha256` and `core253_local_query_sha256`, and decision cutoff. Source/Strategy/Factory ACK SHAs must start `null` and remain independent.

**Independent custodian/source-rights witness requirements:** authorized custodian legal identity and scope/permissions/expiry/revocation, original publisher provenance (venue/symbol/interval/months), exact original ZIP/CHECKSUM+manifest+F2 report SHA chain, externally authorized signer/key ID, trusted independent key registry or pinned public key, signature/algorithm, signed time and trusted-now/anti-replay constraints; reject any missing/mismatched/expired/revoked signer or month/identity SHA. An authenticated current publisher TLS checksum plus a caller-supplied JSON/document hash alone is **not** a historical issuer signature, independent custody authorization or PIT attestation. Keep `RETROSPECTIVE_NON_PIT`, `historical_pit=NOT_ATTESTED`, `trading_authority=NONE`.

**Positive route precondition:** independently re-verify actual immutable Core #245/#253 per-month query and warehouse source parent chain against the owner-private receipts using the authorized private read-only environment; verify the signed research policy on an independently provisioned trust root and trusted clock; verify *actual* frozen strategy-definition/DNA/config and audited evaluator signal on causally closed 15m bars. Only independently authorized roles may issue the corresponding Source ACK/StrategyApproval. Scanner's proposal (`WAIT_INDEPENDENT_EVALUATOR_AND_CORE_SECRETARY_STRATEGY_APPROVAL`) and 24 `UNKNOWN`/nonselected attempts never constitute approval. No positive example with fabricated signer/private key is acceptable as authentic F5 evidence.

**State:** Core Windows exact-module release gate and read-only authority verifiers implemented; authentic external sign-offs remain **NOT** available. Unit-test keys are ephemeral contract tests, not real role approval. Without separate independent custodian witness, strategy evaluator evidence and authorizer roles, the only valid secretary state is `NOT_ENQUEUED`, with `source_ack_sha256=null`, `strategy_approval_sha256=null`, `factory_consumer_ack_sha256=null`. Do not paper/live trade, merge PR or assert G0. Integration #271 owns final assembled tree and consolidated F2–F5 gate; this Core document is an exact handoff, not cross-owner task allocation.
