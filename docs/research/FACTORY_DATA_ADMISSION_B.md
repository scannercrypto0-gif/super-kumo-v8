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
