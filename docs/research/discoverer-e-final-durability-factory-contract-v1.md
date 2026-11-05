# Discoverer Package E final-closure durability and Factory integration handoff

Parent: #272 (closure) / #266 (original). Owner branch: `feat/discoverer-package-e-membership-intake-20261105`; stacked on OPEN Draft #258, no merge assumed.

## Owner delivery

New: `tools/strategy_discoverer_offline/durable_checkpoint_e.py`. Local SQLite WAL + synchronous FULL, BEGIN IMMEDIATE transactional append, canonical SHA-256 and predecessor chain, monotonically increasing immutable ledger snapshots, exact-prefix extension, rejected shortening/history rewrite. Every handoff attempt — admitted/rejected/quarantined — can be appended to a distinct crash-safe immutable event chain; caller-specified attempt_key provides idempotent retry and conflicting retry rejection. A fresh process can read/verify snapshots and attempts. No private market OHLCV is stored.

Independent membership requires `DurableDiscovererCheckpoint.verify_membership(...)`, which reloads committed ledger entries from the Discoverer-owned DB, verifies all entry digests/predecessors, then matches exact package's sealed PENDING checkpoint and attempt/candidate/family/strategy/search-plan/nomination identity. Later COMPLETE is permitted. This is stronger than trusting a caller-provided digest, but **not a digital signature or third-party custody attestation**: DB owner could have originated a completely counterfeit but internally consistent history; Factory must obtain and authenticate the snapshot via its trusted source/custody boundary.

New focused tests `tests/test_package_e_durable_checkpoint.py`: cold restart readback, exact replay, forged digest, old checkpoint, append-only growth, positive/negative/quarantined event census, duplicate/conflicting retry, rollback, tampered SQLite row, uncommitted transaction drop and fake attempt rejection. Old E membership suite was not rerun as a separate gate. CI targets 3.11/3.12/3.13.

## Factory #267 consumer and integration #271

Factory's existing `research_wp_r0/aql_factory_e_discoverer_consumer_v1.py` already replays and independently checks the trusted ledger snapshot, saves a TEST_ONLY intake as `RESEARCH_INTAKE_RECORDED_NOT_EVALUATED`, and does NOT run Lab evaluation. Do not create a competing consumer. Factory may use `DurableDiscovererCheckpoint.read_latest_ledger()["entries"]` as the source snapshot once custody is authenticated, and `attempt_events()` to reconcile attempt status/census against its result store (separate transactions and database). The durable journal event SHA is an evidence pointer, not a Factory consumer ACK. Cross-store exactly-once orchestration is **not proven** by Discoverer's local SQLite transactions alone; Factory must run its own G2/G6/G8 retry/transaction/restart gate, output ACK/result SHA, and declare any distributed transaction limitation.

## Limits

- G2/G6/G8 Discoverer-owned engineering delta only; no full system G1–G12 verdict.
- No factual proof of publisher authenticity, original BTC historical custody, PIT validation, holdout access, paper/live trading authority, remote replication, cross-database atomic commit, or Lab evaluation.
- Keep original `DiscovererResearchIntakeV1` `NOT_VERIFIED` and `NOT_EVALUATED`; only external verified membership plus Factory consumer receipt can establish admission.
- No edits to Core, Scanner or Factory branches. No merge, G0, Work or trading.
