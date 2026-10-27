# D3 synthetic sparse catalog verifier — experimental

Opt-in pure offline contract in `aql.d3_synthetic_archive`. No runtime wiring, filesystem writes, scheduler, external storage, trading, restore overwrite or custody. Catalog creation is deterministic; verification requires a separately pinned catalog digest, exact source inventory, actual target receipt digests for CONFIRMED rows, generation, consumer and epoch floor. WITHHELD, IN_DOUBT and UNKNOWN never become implicit ACKs; absent sequences are gaps, not proof of successful delivery.

## Independent audit traceability

- Core Council #128/6440407428: preserves ordered-prefix quarantine and source/target authority; no healthy-suffix progress guarantee.
- AG-F01 startup journal boundary: unchanged; no replay implementation modified.
- D3 only covers synthetic manifest integrity. SHA-256 alone does not protect against coordinated replacement of catalog and independent pin; physical power-loss, external custody, independent target receipt authenticity, PIT restore, D4 COMPLETE and full D2 remain **OPEN / NOT PROVEN**.
- Factory Council #134 M14 regime path and M15 economic capital-path findings remain Factory-owned; no claim to resolve them.
- Existing backup #111/#116 and G2 #93/#118/#119 branches remain separate and unmerged by this change.

## Test and delivery limits

`tests/test_d3_synthetic_archive.py` tests sparse gaps, withheld/IN_DOUBT, changed or missing target receipt, stale epoch, wrong version/generation, inventory corruption, missing source and deterministic read-only verification. No existing D1/D2/Factory/backup tests repeated. This is a **first implementation slice**, not the complete CORE-ARCH-65 sparse archive writer/restore workflow: durable catalog publication, independent manifest custody, real archive sink stall isolation and crash-consistent restore remain outstanding gates. Do not activate OOS/PAPER/SHADOW/LIVE.

## Slice 2 — offline archive publication and restore rehearsal

`aql.d3_offline_archive.publish_generation` writes a single-generation JSON manifest into an existing local directory, fsyncs the file, uses no-overwrite hard-link promotion, and attempts directory fsync where available. Existing generation or abandoned `.pending` fails closed and requires manual investigation. `verify_restore` reads at most 4 MiB and calls the independent pinned/source/target evidence verifier; it never overwrites a live store. `OfflineArchiveLane` has a bounded in-memory queue, a dedicated worker thread, immediate reject-on-full submit and futures for publication outcomes; upstream MUST retain evidence and retry after any rejection or failure. Closing the lane is a blocking offline control-plane action, not a realtime callback.

Targeted tests in `tests/test_d3_offline_archive.py` cover publication/restore parity, immutable no-overwrite, corruption, missing target receipt, stale epoch and blocked archive worker while submissions remain bounded. This is an isolated synthetic nonblocking demonstration, **not** an integration test of the actual realtime G1 collector and not a latency/throughput SLA.

**Remaining audit gates:** external independent custody and genuine receipt authenticity; crash/power-loss host and filesystem matrix; restart recovery for abandoned pending generations; durable upstream handoff for accepted-but-unconfirmed volatile jobs; integration proof with real collector and source/target authorities; Windows portability of hard-link/directory sync; formal independent Council review and exact-head CI. These are not claimed complete or production-ready.
