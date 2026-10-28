# CORE-DATA-PROOF-01 — producer contract v1 (provisional G0)

This module is an isolated **contract and falsifier test**, not a live ingestion hook,
authenticated provider attestation, Factory admission, or empirical PIT certification.

- Logical candle identity is distinct from immutable per-revision `version_id`.
- Canonical SHA-256 of revision fields binds content digest, event time, first local
  observation, provenance references and supersession ancestry.
- First local observation is **not** proof of global provider publication. Legacy
  `MarketBar.committed_at` is pre-COMMIT and must not be substituted for a
  post-commit evidence receipt.
- Provider availability requires a separate source evidence reference. This v1
  only validates presence of the reference; it does **not** authenticate it.
- `LOCAL_EVIDENCE_ONLY` is **not** `REAL_PIT_ACCEPTED`. Missing clock/commit
  evidence returns `UNKNOWN_PENDING_EVIDENCE`. Late revisions reject.
- Immutable revision chain rejects missing ancestor, branching and reversed
  local-first-seen timestamps.
- The current implementation does not persist revisions or asynchronously deliver
  manifests. Those are later Core-owned slices, independently reviewed.
- Factory retains the decision-time fail-closed scientific admission and pre-Scanner
  universe denominator checks (M16/M17). Council owns independent review.
- No OOS, Paper, Shadow, Live, merge or G0 activation.
