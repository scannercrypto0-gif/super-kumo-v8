## Core F5 — authority evidence and exact dependency contract (2026-11-07)

This section is an **engineering readiness contract**, not a Source ACK, StrategyApproval, Factory ACK or external legal attestation. All values below must be verified against source artifacts and exact HEADs, never assumed because an owner-local run or CI was green.

### Current immutable owner-local F2 evidence (do not rerun private warehouse/vault)

* BTCUSDT native 15m 2024: 10 admitted original months and 29,376 bars; 2024-02/08 remain **inventory-only**. This is an **owner-reported local execution**, not a source signature independently witnessed in GitHub.
* F2 report SHA: `daf1208bf824e58040858a817c709f7943c19668dc23ce3fd3b0368e01156f40`.
* Manifest SHA: `f559c82c2c3827382338ab8f84f4a71a1e6705e08105b9b1bdbfaceb3bcbc8b7`, fresh F1 coverage ledger SHA: `557c38ecb58d9c0c22784ee105c6cb0a29bf2d4dc2ba44f5ed4e2a08c1a89862`.
* Canonical JSON authorization SHA `ced74dade0ee151eff61109bddb912c5203cbb4d091f6ba77545cb262e332439` **differs** from raw authorization *file bytes* SHA `a954b81e67cf731b19aba73d916dda59c80a55ed93442d6abab086972e18cbef`. Integrity/owner permission must not be misrepresented as issuer-authenticated historical provenance.

### RawVault Windows lock/fsync dependency — exact integration inclusion

| Item | GitHub ref / evidence | Status |
|---|---|---|
| Core F draft | `core/package-f-bulk-source-20261105` at `a640c7822794bd2a7fd510b77ae7eb3507cf463f`; PR #275 | OPEN/DRAFT/UNMERGED |
| Separate Windows RawVault fix | `core/rawvault-windows-lock-20261105` at `e368dd491a0d80618bdc6c6e8f731a195d763dda`; preceding `cd720cf7549719639add7180b9321067358607d0` | EXISTING SEPARATE BRANCH; NOT merged into Core F |
| Changed source file on Windows fix branch | `tools/raw_vault_offline/vault.py` blob `6b5bcc1d684088934f5ed7110064380b8d2bc0cd` | Content-addressed reference |
| Core F **Git tree** at exact head | no `tools/raw_vault_offline/vault.py` or `tools/raw_vault_offline/` directory present in tree | **NOT INCLUDED**; external branch/worktree dependency |
| Integration PR #271 at `75b8ddc47cfecc526df101937bda6d56e69e5dcd` | no `tools/raw_vault_offline/vault.py` in its own git tree | **NOT INCLUDED** in integration tree either |
| Branch comparison | Core F and Windows fix histories **diverged** (raw branch 10 ahead / 173 behind Core F relative compare); do not fast-forward/merge wholesale | Owner-controlled explicit source overlay/stack reconciliation required |

**Mandatory integration resolution:** pin the exact `vault.py` blob in the one canonical assembled deployable source tree, with stable module path `tools.raw_vault_offline.vault`, consistent with the existing canonical #211 RAW API, and verify imported module `__file__` and SHA-256 of exact source bytes against the pinned blob. Reconcile other files needed for the package imports rather than shipping a standalone `vault.py` into a non-existent package. Preserve the existing on-disk manifest/index format, locking and `fsync` semantics. Test Windows cross-process lock exclusion, lock timeout, crash release, append readback, restart and idempotency in **disposable fixture roots only**. Do not alter real populated `E:\ATLAS\private\raw_vault` or `warehouse`. No release inclusion claim before an assembled-tree byte-identical and import-path test passes. Current Core #275 Windows NTFS ACL gate passed at CI #42037180123, Factory matrix #42037179996; neither establishes RawVault inclusion in #271.

### Distinct real authority graph (NOT auto-issued by Core F2)

`F2 source custody/rights evidence` → **independent Core Source Secretary ACK** → **independently authorized, signed research policy + authentic strategy-specific evaluator decision** → **independent Core Strategy Secretary Approval** → **Factory Consumer ACK** → **research-only Lab gate**. All links must point to their actual signed parent receipts and independently verified issuer/trust root.

Scanner #277 at `012f9f19de2111ac4113a9f773fe3ef6baca9b02` documents the pending interface in `tools/scanner_strategy_f/secretary_ack_requirements.py`:
* `aql.core.f.historical-source-ack.v1` issuer role: `CORE_SOURCE_SECRETARY`; separate from the F2 report itself.
* `aql.core.f.historical-strategy-approval.v1` issuer role: `CORE_STRATEGY_SECRETARY`; only after independently authenticated evaluator and strategy/policy approval; must not be self-signed from Scanner's proposal.
* `aql.factory.f.consumer-ack.v1` issuer role: `FACTORY`; cannot be auto-emitted by Core.
* Required immutable parents of strategy-specific proposal: `strategy_decision_sha256`, `source_bound_census_sha256`, `policy_approval_sha256`, `core_f2_report_sha256`, `external_source_authorization_sha256`, strategy ID/version/definition digest/native15m config digest, source ZIP SHA, warehouse receipt SHA, **distinct** `core245_native_query_sha256` and `core253_local_query_sha256`, and decision cutoff. Source/Strategy/Factory ACK SHAs must start `null` and remain independent.

**Independent custodian/source-rights witness requirements:** authorized custodian legal identity and scope/permissions/expiry/revocation, original publisher provenance (venue/symbol/interval/months), exact original ZIP/CHECKSUM+manifest+F2 report SHA chain, externally authorized signer/key ID, trusted independent key registry or pinned public key, signature/algorithm, signed time and trusted-now/anti-replay constraints; reject any missing/mismatched/expired/revoked signer or month/identity SHA. An authenticated current publisher TLS checksum plus a caller-supplied JSON/document hash alone is **not** a historical issuer signature, independent custody authorization or PIT attestation. Keep `RETROSPECTIVE_NON_PIT`, `historical_pit=NOT_ATTESTED`, `trading_authority=NONE`.

**Positive route precondition:** independently re-verify actual immutable Core #245/#253 per-month query and warehouse source parent chain against the owner-private receipts using the authorized private read-only environment; verify the signed research policy on an independently provisioned trust root and trusted clock; verify *actual* frozen strategy-definition/DNA/config and audited evaluator signal on causally closed 15m bars. Only independently authorized roles may issue the corresponding Source ACK/StrategyApproval. Scanner's proposal (`WAIT_INDEPENDENT_EVALUATOR_AND_CORE_SECRETARY_STRATEGY_APPROVAL`) and 24 `UNKNOWN`/nonselected attempts never constitute approval. No positive example with fabricated signer/private key is acceptable as authentic F5 evidence.

**State:** interfaces defined and lineage pinned for integration, **NOT** actual third-party sign-offs. Without separate independent custodian witness, strategy evaluator evidence and authorizer roles, the only valid secretary state is `NOT_ENQUEUED`, with `source_ack_sha256=null`, `strategy_approval_sha256=null`, `factory_consumer_ack_sha256=null`. Do not paper/live trade, merge PR or assert G0. Integration #271 owns final assembled tree and consolidated F2–F5 gate; this Core document is an exact handoff, not cross-owner task allocation.
