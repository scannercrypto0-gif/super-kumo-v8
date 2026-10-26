# SF-DEC-23 B / SF-DEC-24 B / SF-DEC-25 B — DEV-only historical admission

**Owner authority:** one bounded Draft PR for the Factory-only research preflight.
**Out of scope:** real historical/OOS/holdout reads, split creation, live or paper
orders, StrategyDefinition evaluation, PnL, attempt COMPLETE, shared/Core
schemas, operational receipts, new databases, externally certified custody.

## Boundary

`preflight_dev` takes an already-provisioned in-memory **complete DEV-only**
manifest and bar sequence, frozen DEV bounds, declared source reference and
an expected `content_hash_v1` supplied by the caller. It has no file access,
does not fetch archives or make network calls and never opens reserved OOS.
It checks manifest and exact DEV bounds before it enumerates bars, and rejects
combined DEV/OOS manifest bounds before touching the supplied iterator.

**Important limitation:** a caller may still improperly load a combined dataset
before invoking this function. `DevBoundary` is a *caller claim*, not a
cryptographic access grant, trusted signer or independent storage-ACL proof.
The current Draft does not establish physical isolation of real data; the
operator must separately provision DEV-only storage with protected reserved
OOS and independently review permission boundaries. Do not provide combined
source material to the caller. This code cannot independently certify an
external custodian, original producer or genuine as-of receipt.

## Report contract

The read-only report always sets `oos_access=LOCKED`,
`independent_custody=NOT_VERIFIED`, `confirmed_pit_eligible=false`,
and `state=INPUTS_ONLY_NOT_EVALUATED`. Three contemplated proof tiers are:

* `RETROSPECTIVE_DEV`: structurally accepted DEV-only data with original
  historical arrival unknown. Only eligibility for later separately authorized
  exploratory DEV; it is not a proof of source receipt or OOS readiness.
* `PIT_METADATA_VALID`: internally consistent locally marked CONFIRMED
  receipt/cutoff data, **not externally authenticated PIT**. Missing or invalid\n  decision cutoff in CONFIRMED-labelled data is BLOCKED, not silently\n  reclassified as retrospective. Mixed RETROSPECTIVE/CONFIRMED bars are BLOCKED.
* `CONFIRMED_PIT_VERIFIED`: **never emitted by this version**. External
  verified producer delivery, independent anchor and custody are missing;
  a subsequent architecture decision and separate approval are required.

The positive structural tier still records\n\`DEV_PARTITION_AUTHORITY_NOT_VERIFIED\`. A trusted real DEV-only partition\nprovisioner and approved license/source authority remain unimplemented and\nrequire a distinct owner-approved interface and verification evidence.\n\nBad or unverified DEV partition, wrong expected content identity or quality
produces `BLOCKED` with a stable reason. The `report_digest` is for
reproducibility and tamper-evidence only; `verify_admission_report` requires a
caller-retained digest AND rejects semantic promotion even if the malicious
report was rehashed. Verification does not replay the input dataset:
source replay and independently held report commitment remain external tasks.

## Identity and isolation

Uses the existing merged `content_hash_v1` (#78) only on a *complete* DEV-only
manifest and ordered bars. That hash is different from original raw archive
SHA and legacy `manifest_integrity_hash`; hashes alone are not provenance
authentication. Do not compute an identity on a slice of a combined DEV+OOS
manifest. Only a separately authorized custody/split workflow may prepare
a DEV-only artifact from a source that contains reserved OOS.

The `source_reference` field is descriptive/caller-asserted, not an
independently validated URI or a source license attestation. No production
source admission should follow from an in-memory fixture pass. The first
PR focuses on synthetic unit fixtures. Real data access remains DATA_BLOCKED.

## Focused acceptance

`python -m pytest -q tests/test_sf_historical_admission.py` under Ubuntu and
Windows. Cases include source-arrival UNKNOWN, metadata-only PIT, forged tier
and eligibility and OOS claims with rehashing, wrong caller-held digest,
wrong/mixed DEV manifest rejected before iterator read, incomplete bars,
wrong units/content hash and replay determinism. This is not an actual
historical/backtest or an external custody/ACL drill.

Historical OOS [#120] remains blocked; Core archive/backup [#71] remains
independent. Code/merge restrictions are governed by distinct owner consent.
