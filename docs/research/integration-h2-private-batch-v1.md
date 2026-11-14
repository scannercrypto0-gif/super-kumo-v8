# H2 — ONE OWNER-LOCAL BATCH, NO HAND-WRITTEN MANIFEST

**Owner directive:** [#271/6718784223](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/271#issuecomment-6718784223). The owner has already granted a **conditional single original-source experiment** [#205/6718325330](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-6718325330). This is NOT blanket E: access; private custody and source rights still need independent authentication. Independent Audit is **deferred** until the combined engineering batch finishes. No PR merge or G0.

## One Windows command

Download the versioned [`tools/atlas_h2_windows_batch.ps1`](../../tools/atlas_h2_windows_batch.ps1) into a trusted local directory, then execute **once** with private local paths:

```powershell
& '.\atlas_h2_windows_batch.ps1' -EvidenceDir '<PRIVATE_PREEXISTING_CUSTODY_DIRECTORY>' -CustodianVerifierKey '<EXTERNALLY_PROVISIONED_CUSTODIAN_KEY>' -OwnerSigningKey '<SEPARATE_EXISTING_OWNER_KEY>' -ConfirmOneRun
```

No hand-authored operator JSON, user-calculated source SHA, or piecemeal PowerShell probes. The script builds a disposable Git repository in Windows TEMP with exact authenticated SHA pins, runs a fresh isolated Python driver, never resets or checks out the owner worktree, and removes only that disposable TEMP directory. Only explicitly named **existing** private custody files are inspected prior to independently authenticated single-run scope. **Do not pass raw source bytes, prices, private paths or key contents to GitHub or chat.** Public network use is restricted to fetching pinned public source commits.

The launcher defaults to a new private result directory under Windows **LocalApplicationData\\ATLAS\\H2-Local-Batch** (and prints its exact location). An optional `-OutputDir` override is permitted only within that protected profile subtree, never under the original source. The local result is exactly one **`h2-batch-summary.json`** under that output directory, sealed with its `sha256`. It records either `PASS_ENGINEERING_ONLY` with Core245/Core253, Strategy/Scanner, Factory/Lab/Secretary and no-write hashes, or `BLOCKED` plus a consolidated specific stop reason. In neither case are PIT, economic, alpha, paper, F5, trading, holdout or G0 permissions granted. No actual E: run can be claimed from GitHub CI.

### What must already exist privately

The trusted independent custodian or previous owner-approved data-admission process must **pre-provision**, in one explicitly selected directory, these five exact files. The bootstrap never fabricates a missing item:

| Private file | Mandatory meaning |
|---|---|
| `custody-intake.json` | Versioned **externally supplied** custody/rights scope `aql.integration.h2.private-custody-intake.v1`: real Warehouse/RawVault roots, BTCUSDT Spot 15m dataset/version, chosen one **complete** month, 15m range <=4096 bars and cutoff, original source/manifest SHA, genuine Core245 receipt file SHA, manual third AST file SHA/digest and ID, Factory code SHA, unique `RESEARCH-H-GENERIC-` experiment ID, exact owner permission reference `#205/6718325330`, source-rights attestation reference/digest |
| `custody-intake.mac` | Custodian's lowercase HMAC-SHA256 over **exact raw bytes** of `custody-intake.json`, from an **independently provisioned custodian key**. Not an operator-generated permission |
| `rights-evidence.bin` | Genuine owner-custody / source-rights evidence, byte hash pinned by the signed custody intake. May be a prior private receipt in any original format renamed by the custodian; no invented proof |
| `core245-native-receipt.json` | Retained genuine **complete-range** `aql.core.historical-price-custody-query.v1` native Core245 receipt, not a summary or synthetic fixture; actual source and range later cross-checked against Core253 immutable snapshot |
| `manual-third-ast.json` | Existing independent **manual third Scanner H AST** definition, not frozen F2 or Discoverer approval. Its JSON file SHA and strategy-definition SHA/ID are pinned by custody intake and revalidated in actual Scanner |

The external **`CustodianVerifierKey`** and separate **`OwnerSigningKey`** must already be provisioned by trusted owner/custodian control and kept outside the original Warehouse/RawVault, Git repository and published logs. A freshly invented key, an unsigned custody-intake file, a fake legal-rights declaration or test fixture cannot be used as source authorization. HMAC authenticates who holds the key; it **does not prove issuer PIT, legal ownership or economic truth**. The owner must independently trust/check the custodian's rights documentation before commissioning a real run. The filename search previously performed in `E:\ATLAS\private` did **not** find matching H2 receipt/key names; that is limited filename-search evidence, not proof that no record exists elsewhere.

### Signed-scope ceremony (automatic, but explicitly confirmed)

The script **never creates** custody proofs or trusted keys. It first verifies the independent custodian MAC and exact file hashes without opening the original source. Only after `-ConfirmOneRun` does it use the separate, externally pre-provisioned owner signing key to construct and sign one strictly bounded local operator manifest; no user manually writes JSON or SHA. It pins the already approved **research-only illustrative Spot LONG cost numbers**: fee entry/exit **10/10 bps**, spread **2/2 bps**, slippage **3/3 bps**, funding per bar **0**. The automatic MAC is an owner-controlled local signing ceremony, *not* independent proof that the rights attestation is true.

Before accessing original data, it creates an exclusive `h2-single-use-claim.json` in the authenticated private evidence directory (never in the original source roots). Changing the output directory cannot silently reuse the same one-time permission. A denied or failed run still consumes the attempt; a renewed attempt requires an explicit new owner decision and independent re-evaluation.

### Core and SQLite execution boundary

The already accepted 32 KiB `warehouse.sqlite-shm` with zero-byte WAL is **not** proof of a write. The corrected `atlas_h2_owner_local_one_shot_v1.py` permits volatile SHM and empty WAL. It refuses nonempty WAL, unknown journal states, unexpected symlinks or durable content drift, and creates a transactionally consistent WAL-aware `mode=ro` SQLite backup in disposable private scratch. Only **that** snapshot is queried by Core253 with `sqlite_immutable=True`; the original SQLite is **never** forcibly opened with `immutable=1`. The source stage is copied privately without hardlinks. Durable original Warehouse and RawVault content SHA-256 fingerprints must match pre/post.

After the complete source, cutoff and Core245/Core253 SHA verification, the operator uses the existing Scanner H manual AST to create causal signals, Factory H generic Decimal modeled fills to a **new isolated Results SQLite**, independent Lab and Core Secretary durable WAIT with four null ACKs. All access remains `RETROSPECTIVE_NON_PIT` and `NOT_ATTESTED`.

### One consolidated BLOCKED report — expected if private evidence is absent

For example, if the explicit evidence directory does not contain the five genuine signed files, the program emits a single `BLOCKED` report with `MISSING_PRIVATE_EVIDENCE:...`. It **does not enumerate E: or infer hashes**, and never asks the owner to run 20 small diagnostics. If the evidence exists but external keys are missing, it blocks with `INDEPENDENT_CUSTODIAN_VERIFIER_KEY_REQUIRED`, `INDEPENDENT_OWNER_HMAC_KEY_REQUIRED` or `CUSTODIAN_SIGNATURE_UNVERIFIED`; if a signed dataset, source range, key or SHA differs, it blocks and does not manufacture the missing parents. If actual source rights cannot be established, **BLOCKED is the correct deliverable**, not a synthetic or original `PASS`.

### Focused engineering acceptance

Windows and Linux targeted CI tests verify absent evidence refuses any source access, tampering, missing owner confirmation, two-key separation, signed file SHA mismatch, single-use claim against output-path replay, SQLite SHM/WAL read-only snapshot and source immutability. CI never receives private source files or rights/keys. The existing H/H2 accepted suites are not repeated. Final independent Audit remains deferred until the actual engineering batch is closed. The Draft Integration PR stays unmerged; G0, F5, holdout, paper/live and trading remain blocked.

**Receipt accuracy:** If the operator has already been invoked but later blocks, the consolidated report sets `source_read=null`, `source_read_status=POSSIBLE_AFTER_GATES` rather than falsely asserting the source was never accessed. Pre-source bootstrap refusals use `source_read=false`, `NOT_ATTEMPTED`; a verified successful execution uses `source_read=true`, `CONFIRMED`.
