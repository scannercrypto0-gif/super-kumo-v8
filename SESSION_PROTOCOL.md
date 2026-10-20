# Session protocol — mandatory

## START
- Confirm repository location, branch and latest commit (`git status`, `git log -1`).
- Read `00_START_HERE.md`, `01_CONTRACT.md`, `02_ROADMAP.md`, `03_DECISIONS.md`, `04_STATE.md`, and active WP.
- Restate current gate, active WP, blockers, and one exact next action.
- Do not implement tasks outside the approved WP.

## EXECUTION
- Use one WP per branch; define acceptance tests before code.
- Preserve point-in-time data semantics, reproducibility and versioning.
- Record failing tests and missing evidence; no silent gate closure.
- Document new architectural choices in `03_DECISIONS.md` before adoption.

## END
- Update `04_STATE.md` and append `05_WORK_LOG.md`.
- Record commit hash, tests executed, outcomes, outstanding issues and next exact task.
- Produce a handoff message using `HANDOFF_TEMPLATE.md`.
- Owner approves gate closures; reviewers cannot self-approve.

## RECOVERY
If context is missing, STOP and reread repository. Never reconstruct the project state from model memory alone.
