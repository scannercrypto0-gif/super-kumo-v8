# Fresh PING deployment baseline diagnostics

Owner reported `FRESH_PING_BASELINE_DRIFT` on candidate 856220e7 before deployment. The old compound condition did not identify the failing predicate. The host cause remains unproven: no configuration, task, quota or manifest mismatch is inferred from this message.

The unified bootstrap now emits every failed predicate, actual installed configuration digest, HOLD reason, manifest verification, task enabled/state, collector count, supervisor lock availability and quota summary. Terminal results are create-once JSON files under owner-results and fail before permit creation. Empty and null blocker arrays are normalized consistently on Windows PowerShell 5 and PowerShell 7.

Only enabled scheduled-task readiness/lock contention, with zero collectors and no other blocker, receives a bounded three-minute read-only wait, five seconds between checks. Unknown, quota, collector, stop, disk, manifest, configuration and HOLD changes never receive retries or automatic clearance. The Apply phase still repeats exact identity authorization and acquires its original exclusive locks; a race cannot authorize a different baseline.

No task starts, schedule/principal changes, source calls, counter resets, HOLD removals or data changes occur during this assessment. The installed configuration remains pinned to 857bea957d1da3fa1ef1c01ace44a0bfda27f84c2750523184455936a48f2cf2. Existing fresh-PING correction, admission/circuit policy and original evidence remain unchanged. Successful engineering tests do not attest owner-host continuous operation.

Regression checks execute the actual bootstrap function extracted from its PowerShell AST, covering empty/null blockers, every terminal blocker category, transient scheduler contention, disabled tasks and multiple simultaneous drift predicates. CI runs these on Ubuntu PowerShell 7 and Windows PowerShell 7/5, alongside the native runtime suite.
