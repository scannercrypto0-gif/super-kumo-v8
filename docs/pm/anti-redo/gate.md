# ATLAS pre-assignment reuse gate

Provisional Owner B, Issue #205 comment 6824875424. PM owns disposition before assigning Work, Codex or another manager. Review artifacts are versioned with the architecture draft. A documented disposition conveys no new execution, coding, data, trading, merge or G0 authority.

## Inputs and decision order

1. Record task, affected capability IDs, exact existing PR/owner, current main and relevant head/base pins. Attach lookups over the coverage index, code paths, symbols, stacked branches and prior Work/Audit. Cite the last actual Owner handoff and later applicable decisions. Record exclusion and uncertainty explicitly.
2. Review the old/current crosswalk at those pins. State the changed seam, path/contract, observable failure and smallest remedy. Unchanged accepted scope resolves to `ALREADY_COVERED`. Existing disconnected code resolves to `CONNECT_EXISTING` with `REUSE_WITH_ADAPTER` only if the contract delta is proven. Missing inventory or stale pins resolve to `INVENTORY_REQUIRED`. A parallel build with unresolved overlap resolves to `BLOCKED_DUPLICATE_RISK`.
3. A proved `REAL_GAP` can proceed to approval. Identify accountable role, required decision, current scope authority, and rollback. An approval-only finding grants no runtime action. Evidence-only gaps belong to custody and review first.
4. For every accepted test used, cite ledger ID and compare exact source/test/workflow, fixture, environment, authority and result scope. If a prior test is proposed again, require a changed pin or assumption, a reproduced failure, or demonstrated missing coverage. Record the affected assertion and minimal new case. Unknown test identity or scope cannot be promoted. A path match, title match or common blob alone cannot prove semantic duplication.
5. PM signs disposition at exact task revision and pins. Component owner signs the overlap determination. Audit independently reviews the changed evidence scope when the task's authority requires it. Refresh on new commit, changed fixture/contract, policy change, expiry, or superseding decision. In a stale/unknown state, hold assignment.

## Proposed GitHub integration

Use a PR template that links the versioned pre-assignment record and its decision; use the same record for non-PR work on #205. A future read-only check should validate against `gate.schema.json`, resolve IDs and exact pins, detect historical paths/symbol overlap and test intersections, and confirm a human review reference. The check should reject missing fields, unknown IDs, stale pins, unjustified reruns, unreviewed overlap, and unauthorized scopes. Check failure should link the precise missing field or conflicting capability. Once separately approved, register a single required check on protected target branches using stable check naming; use consistent results for docs-only PRs and avoid ambiguous duplicate workflow check names. PM should gate assignment itself before any branch protection runs.

A false positive requires a scoped, time-bounded reviewer decision that identifies the overlap and proves the differing contract or assertion. Record the approving PM, component owner, reason, exception scope, expiry and pinned revision. Revalidate on pin changes. Exception review cannot bypass source rights, trading, G0 or independent approval controls. Rollback is to revoke the assignment record and withdraw the scoped proposal; keep all evidence and commit history. Enforcement code and changes to repository protection require separate Owner authority.

## Dry runs

See `dry-runs.json`. The duplicate proposal to rebuild the Factory attempt writer was rejected. The independently documented February native custody gap may go to an evidence-only approval path. Neither case creates a Work assignment or runs existing tests.
