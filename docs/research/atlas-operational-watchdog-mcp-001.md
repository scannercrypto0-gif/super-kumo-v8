# ATLAS Operational Watchdog ? engineering handoff

**Scope:** P0 read-only snapshot builder for the existing historical warehouse, daily archive, and live WS lanes. This package is engineering-only. It does not install a scheduled task, start/stop a process, alter a source lane, or expose the Windows host. P1 MCP remains gated on P0 owner-host evidence.

## Reused evidence sources

The reader consumes six explicit, bounded files; it does not enumerate the warehouse or scan raw archives:

1. A sealed `aql.warehouse.registry-snapshot.v1` from `catalog/registry/`.
2. A sealed `aql.warehouse.full-history-continuation.v1` receipt from `receipts/`.
3. The existing `aql.recurring-runtime.health.v1` daily health export.
4. The actual daily import receipt from `receipts/`.
5. The exact source catalog receipt from `catalog/`, cross-linked to the daily import and current Registry snapshot. Its ZIP and CHECKSUM digests must match the committed-source receipt.
6. The existing `atlas.ws.continuous-report.v1` output from the live lane.

Paths are input arguments and are never copied into the resulting snapshot. Every file has an 8 MiB bound; symlinks, reparse points, hard-linked inputs, duplicate JSON keys, invalid seals, path traversal, malformed counters, and mismatched daily lineage fail closed. The output includes source hashes, status reasons, bounded counters and coverage totals, but no raw market payload, secret, or source path. It is create-only and does not overwrite a prior observation.

## Status rules

`HEALTHY_PROGRESS` requires a changed committed fingerprint between two observations. PID existence, process I/O, a changing log, a scheduler heartbeat, or an archive-validation heartbeat alone cannot claim durable progress. A durable validation heartbeat may be shown as `SLOW_BUT_PROGRESSING`; it cannot refresh the committed cursor or indefinitely hide a stall. Stalling requires an unchanged durable fingerprint across observations, known eligible work, and a trusted clock. Explicit live HOLD remains `HOLD`. Missing or unlinked daily source evidence is `UNKNOWN`. Unresolved published source partitions or gaps are `COMPLETE_WITH_GAPS`, never `COMPLETE_VERIFIED`.

The first observation is a baseline and will normally be `UNKNOWN`. The next observation compares committed state against that baseline. Clock uncertainty above five seconds suppresses freshness and stall claims; an observed durable counter change can still be reported as progress.

## Local verification already run

The seven synthetic tests cover baseline behavior, durable progress, invalid Registry seals, missing original-to-commit linkage, preserved live HOLD, create-only output, unchanged inputs, and CLI file-pin checks. They passed on the available Windows Python 3.12 runtime. Exact-branch Windows and Ubuntu CI is configured in `.github/workflows/atlas-ops-watchdog.yml`; Exact-head GitHub Actions passed on both `ubuntu-latest` and `windows-latest` for commit `c290641b8d08cbed908e5f51aec2110f1182a388`.

These tests do not prove current owner-host progress, production freshness, daily task operation, or continuous WS recovery. The latest known host evidence remains limited to the previously recorded process I/O sample. No owner-host proof is claimed here.

## Owner-host proof procedure

After reviewing this candidate and making its files available in the isolated checkout, run the following read-only command twice, using the exact existing evidence files. Do not point it at raw archives or use it to start/import market data:

```powershell
$repo = 'C:\Users\dell\ATLAS-super-kumo-v8'
$sha = '<reviewed 40-character candidate SHA>'
$python = (Get-Command python.exe).Source
& $python -B "$repo\tools\atlas_ops_watchdog.py" `
  --registry '<exact sealed Registry snapshot JSON>' `
  --history '<exact sealed full-history receipt JSON>' `
  --daily '<exact existing daily health export JSON>' `
  --daily-import '<exact sealed daily import receipt JSON>' `
  --daily-source '<exact committed source receipt JSON named by its ZIP SHA>' `
  --live '<exact current live continuous-report JSON>' `
  --output '<new unique path for observation 1>' `
  --deployed-sha $sha
```

For observation 2, pass the same source files at their current versions, use a new output path, add `--previous '<observation 1 path>'`, and wait long enough to observe a real commit boundary. Reusing the same output path is rejected. If current host evidence paths are unavailable, leave the result `OWNER_HOST_PROOF_PENDING`; do not infer progress from the old PID sample.

## P1 gate: read-only MCP

Do not build or expose MCP tools until two owner-host observations verify the P0 snapshot and the same authoritative source files. The intended allowlist is `atlas.runtime.health`, `atlas.warehouse.progress`, `atlas.warehouse.coverage`, `atlas.daily.status`, `atlas.live.status`, and `atlas.gaps.summary`, all reading the identical sealed snapshot. Any client transport or remote Windows access requires separate authorization. No public tunnel, arbitrary file-read tool, command execution, acquisition, or mutation endpoint is allowed.

## Current delivery status

- **P0 code:** implemented in draft PR #331 against the existing integration branch.
- **Local tests:** 7/7 passed on Windows Python 3.12.
- **Windows/Ubuntu exact-head CI:** passed on commit `c290641b8d08cbed908e5f51aec2110f1182a388`.
- **Owner-host two-observation proof:** pending; this Work session has no authorized file-level access to the private E: warehouse or its running task outputs.
- **P1 MCP:** blocked at its explicit evidence gate.
- **Unattended execution:** not installed or enabled.

