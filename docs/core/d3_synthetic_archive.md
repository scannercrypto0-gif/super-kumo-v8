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
