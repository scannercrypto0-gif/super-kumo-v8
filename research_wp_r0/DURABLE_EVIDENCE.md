# WP-R7: Durable Research Evidence (isolated synthetic prototype)

**Authority:** research-only; does not grant trader operation, G0 acceptance, shadow, paper or live trading access.

## Mechanism
`DurableTrialJournal(path, FrozenSearchFamily)` persists canonical UTF-8 JSONL entries with:
- monotonically increasing sequence and single, pinned `FAMILY` header;
- previous SHA-256 hash and current SHA-256 hash;
- caller-defined event ID for exact retry idempotency;
- attempted candidates, pre-holdout selection, and holdout OPEN/TUNE/REOPEN events;
- full chain and in-memory trial-state-machine replay before recovering or changing records;
- exclusive cooperative `.lock` file to refuse concurrent writers;
- `fsync` for the append file after each record;
- hard rejection of incomplete tail, altered records, skipped sequence, unknown state transitions or family mismatch.

`close()` / `with` releases the cooperative lock. If a process crashes, a stale lock **must be investigated manually**, never automatically deleted or broken by untrusted code.

## WP-R8 audit hardening (follow-up)

- External anchor checks pin an **exact checkpoint prefix** at the trusted sequence, so valid subsequent appends remain possible. The pin is rechecked whenever the full journal is replayed, including before every mutation.
- The writer detects replacement of the journal's file identity (device/inode, where the OS provides it), refuses nonregular journal files and uses no-follow flags where available.
- The anchor is still only as trustworthy as its *external* custodian. Hashes alone cannot authenticate original author, arrival time or historical completeness.
- File-identity checks do not block hostile **in-place** rewriting and are not a filesystem security boundary; external signing/ACLs and OS-specific crash testing are still required.
- Lock files remain cooperative and stale locks must not be automatically broken. Windows storage and power-loss durability are not certified by the Linux CI runs.

## External anchor and threat model

Once an external system separately records a **trusted** `{family_digest, sequence, head}` checkpoint, pass `expected_head` and `expected_sequence` to the constructor (or call `verify_anchor`). Failure must stop processing.

**No external anchor is written or stored by this prototype.** Merely copying a checkpoint elsewhere on the *same* writable machine is not proof of immutability. Trusted custody and signing, monotonic external timestamps and retention policy remain for a later authorized integration.

A fully writable local adversary can rewrite the entire JSONL file and recompute the entire hash chain. SHA-256 chaining by itself does not prevent deletion/rewrite of history, and an attacker could replace this Python code or bypass the advisory `.lock`.

`fsync` reduces data-loss exposure but durability of directory entries, device caches, filesystem/hardware guarantees and power-loss behavior varies by platform (Windows vs POSIX). Torn-tail recovery is **manual**, not auto-truncate or auto-ignore. The implementation does not claim crash-safe atomicity for multi-process independent writers or network/shared storage.

## Unit test

```sh
python -B -m unittest discover -s tests -p 'test_research_wp_r*.py' -v
```

All tests use temporary local directories; no third-party packages, provider access, database, API keys or real funds.

## Known integration limitations

- The journal verifies historical **logical events**, not truthful upstream timestamps, provenance or untouched holdout access.
- Retry idempotency requires the caller to reuse the same stable event ID and byte-identical event payload.
- Writer replays the entire journal before each mutation (safety-oriented prototype, not optimized for high-throughput).
- No enforced record retention, disk quotas, key management, access control or authenticated external publishing.
- No source permissions to alter research candidate authority; `confirmatory_eligible` remains false in inherited WP-R6.

**Do not merge before owner G0 review and dedicated durability/security audit.**

## WP-R19 read-boundary verification
`DurableTrialJournal.report()` now replays/verifies current disk evidence (and any pinned prefix) before returning, and poisons the instance on failure. Reports never repair/write evidence; reads have linear validation cost. Checkpoint independent-trust assertions accept only literal `True`; this is still not authentication. Frozen scalar identity/provenance references must be nonempty strings. Journal bytes/hash format, per-event fsync/ACK and all holdout fail-closed gates remain unchanged.
See [executed adversarial cases, measurements and source limitations](READ_BOUNDARY_REVIEW.md). Fully rewritten unanchored history is still unauthenticated; no hardware power-loss or actual external-custody proof is claimed.

## WP-R19 read-boundary verification
`DurableTrialJournal.report()` now replays/verifies current disk evidence (and any pinned prefix) before returning, and poisons the instance on failure. Reports never repair/write evidence; reads have linear validation cost. Checkpoint independent-trust assertions accept only literal `True`; this is still not authentication. Frozen scalar identity/provenance references must be nonempty strings. Journal bytes/hash format, per-event fsync/ACK and all holdout fail-closed gates remain unchanged.
See [executed adversarial cases, measurements and source limitations](READ_BOUNDARY_REVIEW.md). Fully rewritten unanchored history is still unauthenticated; no hardware power-loss or actual external-custody proof is claimed.
