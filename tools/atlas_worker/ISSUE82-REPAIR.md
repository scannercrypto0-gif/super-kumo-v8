Issue 82 local repair
====================

The runner targets its own repository. Execution still requires --execute and
all existing issue authorization labels and owner checks. --quota-confirmed
has been removed. QUOTA_PROVIDER defaults to None, blocking execution.

An operator must install a trusted provider in code before unattended use.
It must return observed_at (Unix seconds) and remaining_execution_seconds
(a conservative execution allowance derived from authoritative quota data).
Snapshots older than 60 seconds, future timestamps, invalid values and budgets
below --max-seconds are rejected. No issue text or CLI option supplies telemetry.
There is deliberately no bundled quota estimator or affirmative bypass.

SQLite claims are committed before worktree creation or Codex invocation.
The unique key is issue number, resolved origin/main SHA, and a digest of the
approved request snapshot (including updated_at and labels). Claims remain
after success, failure, crash, and timeout. An interrupted claim is not resumed
automatically; an operator must inspect it. Do not delete the state database to
retry. The directory lock is an additional conservative concurrency guard;
after a crash it also requires manual inspection.

After Codex produces changes, unittest discovery runs in a separate process
with a 120-second timeout. Zero discovered tests, discovery errors, failures,
or timeout stop execution before staging, commit, push, or draft PR creation.
Projects using another test framework must adapt this fixed test policy before
enabling the runner. Test code itself runs inside the worktree and must be
reviewed as executable code.

Local verification: python -m unittest -v test_atlas_runner
The tests mock Codex and publication commands; they never invoke either.
