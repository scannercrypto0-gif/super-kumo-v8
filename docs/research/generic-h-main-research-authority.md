# Generic H research authority on main

This candidate ports the research boundary from PR #284. The JSON manifest lists
the exact source commit and original and candidate blobs for the exercised
runtime and the test fixture. The synthetic test uses Core253 SQLite, the
actual Scanner and Factory engines and the Integration authority bridge.

The new closure is restricted to Generic H. F2 recovery and F3 policy imports
move to their legacy call sites. These legacy call sites still require their
own historical overlays and are outside the candidate entrypoint. Strict F3
and its verifier remain in the historical Scanner branch. No activation,
authorization weakening, or legacy branch changes are included.

Factory historical projection uses the extracted original canonical seal
helpers and a finite Decimal parse for its existing string cost contract.
The scanner strategy identities and frozen config digests are unchanged.
The evaluator fingerprint changes because it hashes the exact two edited
source files. The candidate requires its new fingerprint, and the synthetic
test rejects the old one. A caller must regenerate plugin registration for
a new experiment. Existing sealed results retain their original identities.

The supported typed path accepts only EXPERIMENTAL and can report a blocked
RESEARCH_VALIDATED request. Operator source scope is configured outside the
candidate packet. LIVE, PAPER and ORDER are denied. Typed research writes no
Secretary entry; the explicit legacy no-lane path preserves durable WAIT and
no authority. The test's market input is generated locally and disposable.

Rollback before merge is closing the draft and dropping its branch. No
migration or operational change is required.
