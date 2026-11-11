# Factory Data Admission B — M16/M17 consumer slice

Owner-authorized execution-first Factory slice. The new module is an isolated
pre-feature refusal gateway. It takes caller-supplied immutable revision metadata
and a retained manifest digest. It does not authenticate provider attestations;
the optional caller assertion can ONLY reach ELIGIBLE_FOR_EMPIRICAL_REVIEW, never
REAL_PIT_ACCEPTED. No actual market OOS or Paper/Live.

The gateway MUST be invoked before empirical indicator/Scanner/Decision use.
The existing synthetic R0 implementation remains unchanged. Core #137 is
separate and unmerged; future integration must map exact Core revision schema,
verify a trusted producer/clock authority, enforce externally enumerated
opportunity universe and test the offline R0 path without copying Core runtime.
M18 requires shared frozen indicator calculation windows/seeding across consumers.

Run targeted offline tests: python -m pytest -q tests/test_sf_data_admission_b.py
No pre-existing Factory/Core green suites are re-run as part of this source delivery.
Audit #134 M16/M17/M18, Factory #77 and Core #128 remain independent gates.

## Exact Core #137 schema reconciliation (read-only review)

At Core #137 HEAD fbe3c62ef64e2009fd3c44a3094090a950ff7a26,
`ObservationVersion` exposes `version_id`, `payload_digest`,
`bar_close_ms`, `first_local_seen_ms`, optional
`provider_available_ms`, evidence refs and supersession; its envelope has
`manifest_sha256`, `gap_states`, epoch and
`provenance_scope=LOCAL_ONLY_UNATTESTED`.

The Factory F1 gateway requires `ingest_committed_ms`,
`manifest_digest`, `gap_state` and independently verified source-clock
authority. **These are not a direct field-level match**, and Core's
`local_commit_evidence_ref` is a reference, NOT a verified committed-at
timestamp. Never fill `ingest_committed_ms` from bar close, local first-seen,
or legacy pre-COMMIT `committed_at`; never set
`verified_source_timing=True` based solely on a Core-provided string ref.
Core's LOCAL_ONLY_UNATTESTED envelope cannot grant empirical admission.

The next F2 adapter must fail closed on missing committed-at evidence and
must retain immutable envelope pin/epoch, individual version hash, external
scheduled-universe denominator and every gap reason. Integrating an accepted
synthetic local-only fixture may test blocking and pipeline structure, but
must NOT pretend a real PIT-positive case exists. Current F1 tests exercise
the isolated consumer contract only, not Core-envelope-to-Factory runtime.
M18 calculation-window identity stays a later acceptance requirement.
