# ATLAS Quant Lab session protocol — mandatory

## START

Every new ChatGPT, Work or Claude session must verify Project ID `AQL-CRYPTO-RESEARCH-001` and canonical repository `scannercrypto0-gif/super-kumo-v8` against current GitHub files before using previous context. If either mismatches, STOP and report a possible cross-project context collision. A matching former name alone is insufficient.

Unrelated conversations describing V7 step 311, `gate_spot_cvd.py`, or other projects are not authoritative evidence of ATLAS Quant Lab implementation. Preserve legitimate repository history and legacy references; use them only with traceable evidence tied to this Project ID and repository.

- Confirm repository location, branch and latest commit (`git status`, `git log -1`).
- Follow the exact reading order and resume map in `00_START_HERE.md`; use the active task and evidence linked from `04_STATE.md`.
- Restate current gate, active WP, blockers, and one exact next action.
- Do not implement tasks outside the approved WP.

## EXECUTION
- Use one WP per branch; define acceptance tests before code.
- Preserve point-in-time data semantics, reproducibility and versioning.
- Record failing tests and missing evidence; no silent gate closure.
- Document new architectural choices in `03_DECISIONS.md` before adoption.

## END
- Completed work must update `04_STATE.md` and append `05_WORK_LOG.md` on GitHub through the authorized PR workflow, with direct evidence links to the relevant PR, commit, Issue, or validation output. Distinguish branch/proposed results from merged main; retain prior log entries.
- Record commit hash, tests executed, outcomes, outstanding issues and next exact task.
- Produce a handoff message using `HANDOFF_TEMPLATE.md`.
- Owner approves gate closures; reviewers cannot self-approve.

## RECOVERY
If context is missing, STOP and reread repository. Never reconstruct the project state from model memory alone.
