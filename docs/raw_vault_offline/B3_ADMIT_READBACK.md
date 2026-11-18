# B3 actual admission/readback seam — local PASS, external parent join blocked

Authority: PM #211/6558747066, coordinated Core #180/6558746696 and Factory
#77/6558747556; independent Audit B2 #134/6558685763. This change is on existing
Vault Draft #211 only. No Core/Factory source edits, merge, G0 or deployment.

## Exact scope and source pins

Core #216 `83d44ef23392b9ca9628d18d0f6fc909cd98e4ff`, Factory #209
`ac7f160005672140a3254eb2ed82f4d586432b69`, Vault starting head
`2ddfb2f4a6e145c6579820beb03e4d678594de21` matched the PM/Audit pins on read.
The runner takes separate read-only Core and Factory worktrees and verifies
their full HEADs, tracked source cleanliness and exact bytes of executed
research modules against their respective Git blobs. No merge/overlay writes.

Input is the original **TEST_ONLY Core B2 capture-container bytes** from existing
Actions artifact13084853700, member `core-b2-integrity-input.json`, SHA256
`42005d09e3674420ddd8a761d40540c8e6509e8e79943d1f6a9821f692823b09`.
The artifact is fetched and rehashed, not rebuilt; no accepted B2 tests run.
These are original bytes of a synthetic test instrument, **not original
historical strategy decisions or original vendor market-source bytes**.

`tools/raw_vault_offline/b3_handoff.py` actually invokes existing unchanged
`RawVault.admit`, `read`, and `manifest_entries` in a dedicated new local vault.
It preserves exact input bytes, emits actual immutable-by-hash local manifest
and readback receipt, and retains per-arm F1 record digest/identity/source
version/correction/cutoff claims unchanged. No new Vault storage design.
`verify_local_readback` reopens actual stored bytes and exact manifest before
the consumer interprets JSON. A receipt flag or recomputed receipt hash is not
accepted as external authority.

`integration_tests/aql_b3_vault_seam.py` then parses the freshly verified Vault
readback (not a parallel caller copy) and calls the **actual pinned Factory**
`project_parent_authenticated_f1_slots` with the retained container bytes and
actual manifest metadata. No absent market derivative is fabricated and no
external verifier is supplied. Core original F1/cutoff/source identity is not
rewritten. The true parent gate denies authenticated market coverage; real
Core/Factory status reconciliation retains **N=2 / 2N=4 / 6N=12**, with four
UNVERIFIED arms, twelve UNKNOWN market rows and null signed MFE/MAE. This is
local data flow plus a demonstrated fail-closed boundary, **not a successfully
authenticated market-source/F1 join**.

## Precise blocker and owner action

The current input's claimed source hash is synthetic `aaaa...`, source version
`v1`, correction generation string `g1`, and cutoff900000ms in1970. The original
source-byte stream with that claimed identity is **not supplied**. The Core
container SHA is different. Never equate a captured JSON container with the
market source named inside it or silently remap Core `g1` to Vault integer0.
Container metadata uses generation0 only for this separately named local
capture object, coverage UNKNOWN, trust UNVERIFIED, evidence FIXTURE_SYNTHETIC.
Source/correction publication times remain UNKNOWN; local admission time is
measured at actual admission and is not historical source availability.

To complete the requested genuine source-parent seam, Core/owner must provide
exact retrievable original source bytes matching a real F1 source/prefix or an
explicit authenticated parent-to-prefix transformation; original parent
manifest/receipt bytes and digest; honest source-version/correction lineage
and publication/finalization/availability evidence at the F1 cutoff. An external
issuer/custodian/time verifier must independently establish authority. These
cannot be generated from the current fixture or supplied by a True callback.
Factory remains integration driver for that future joint delivery. Independent
source-parent custody/clock proof is BLOCKED_EXTERNAL_EVIDENCE. Actual monitor
and real prospective producer/pre-F3/F3 remain NOT_CONNECTED. No market reprice,
TP/SL assessment, fee/fill/PnL or profitability test was performed.

## Replay

Retrieve the exact existing Core artifact member above, recheck its SHA, fetch
the three pinned commits, and use separate clean worktrees. From the delivered
Vault commit, Python3.11+ standard library, **POSIX only** (unchanged fcntl Vault):

```bash
python -m integration_tests.aql_b3_vault_seam \
  --core-json /absolute/path/core-b2-integrity-input.json \
  --core-root /absolute/path/core-pinned-worktree \
  --factory-root /absolute/path/factory-pinned-worktree \
  --vault-root /absolute/path/new-dedicated-b3-vault \
  --out /absolute/path/new-b3-report

AQL_B3_CORE_JSON=/absolute/path/core-b2-integrity-input.json \
AQL_B3_CORE_ROOT=/absolute/path/core-pinned-worktree \
AQL_B3_FACTORY_ROOT=/absolute/path/factory-pinned-worktree \
python -m unittest -v integration_tests.test_aql_b3_vault_seam
```

`--out` must be new; a dedicated vault is required so the whole exact manifest
can be checked. The output includes original input, original local manifest
bytes, readback receipt and ONE system-integrity report with per-seam statuses.
Re-run using the **same retained vault** and a new output directory: all four
output files reproduce byte-for-byte, no manifest duplicate is appended. A
fresh independent vault has a new measured local admission timestamp and thus
different manifest/receipt/report hashes; same source identity/status/counts,
not a claim of identical admission events. Retain original local manifest to
replay its identity. Local readback hashes do not establish external custody.

Ten NEW B3 changed-seam tests exercise actual API readback and consumer replay,
changed input, corrupted stored object, missing/changed exact manifest, forged
rehashed external-authority flag, missing SHADOW, wrong source vintage, late
source availability, changed cutoff, and Core missing/forged/late parent-witness
rejection. Local Python3.12.14: ten passed. No True witness callback or test
fixture builder was run. No old B1/B2/G7 suite or full-year market replay.

The new B3 focused CI fetches only the original Core artifact, checks pinned
worktrees, runs this ten-test module and two same-vault report invocations, then
compares all output bytes and retains actual objects/index/manifest/report in
an artifact. Existing old Vault CI gets a changed-path detector to skip its
already accepted test suite for this B3-only delta; actual legacy-module changes
still select that suite. Its AST protected-import scan remains active. Exact
published SHA, real CI/log/artifact identifiers and measured artifact hashes
are posted on #211 and handed to Core/Factory/Audit after actual execution.

Verdict labels are deliberately separate:

| Boundary | Actual expected outcome |
|---|---|
| Core original TEST_ONLY container -> actual local Vault admit/read/manifest | LOCAL_VAULT_SOFTWARE_SEAM_PASS |
| Fresh verified readback -> actual Factory consumer, 4 arms / 12 unknown rows | PASS_FAIL_CLOSED |
| Original F1 market-source parent -> authenticated Factory market coverage | BLOCKED_ORIGINAL_SOURCE_PARENT_NOT_SUPPLIED |
| Independent external issuer/custody/clock and pre-F3 anchor | BLOCKED_EXTERNAL_EVIDENCE |
| Actual monitor / real prospective producer-F3 | NOT_CONNECTED |

These are author delivery classifications pending delta-only independent Audit;
they do not supersede accepted B1/B2 verdicts or authorize activation.
