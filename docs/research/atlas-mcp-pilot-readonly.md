# ATLAS MCP Pilot ? Read Only

**Status:** `ENGINEERING_READY_PILOT_NOT_DEPLOYED`  
**Transport:** local stdio only  
**Source:** one create-only manifest pinning one sealed `atlas.operator.health-snapshot.v1` file  
**Authority:** observation only; scientific qualification and trading authority remain `NONE`

## What it exposes

`tools/atlas_mcp_pilot.py` reuses the validation and sealed snapshot contract in `atlas_ops_watchdog.py`. It exposes exactly two read-only tools and four fixed resources:

- `atlas.runtime.health`: overall status, UTC observation time, evidence grade, per-lane state, gaps, provenance and authority.
- `atlas.lane.latest`: one of `history`, `daily`, or `live`, with source time, last validated committed progress, freshness/expected wait, gaps, provenance and sanitized refusal.
- `atlas://runtime/health` and `atlas://lane/{history,daily,live}`: the same bounded projections as JSON resources.

The projection never returns raw snapshot contents. It omits host paths, raw candles, credentials, process IDs, task details and unrecognized fields. Only stable reason codes are returned; unsafe refusal strings become `REFUSAL_REDACTED`. A live `HOLD` stays `HELD`; a history checkpoint with `full_history_verified=false` remains unverified; daily progress requires the already-validated source-receipt link. Missing, stale, mismatched, malformed, or unsealed evidence returns `UNKNOWN` or a conservative stale/held state. A sealed snapshot is integrity evidence, not host identity: `host_attested` is always `false`.

The server supports the stateless MCP protocol `2026-07-28` and legacy `2025-11-25` stdio initialization. It does not implement HTTP, loopback sockets, subscriptions, prompts, or MCP Apps. The modern response uses private, zero-TTL cache hints so a client must not reuse an old status as fresh. Protocol reference: [MCP 2026-07-28 schema, server discovery and result contracts](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/schema/2026-07-28/schema.json).

## Local setup

Use a reviewed, existing watchdog health snapshot only. Do not point this at a registry, receipt, archive, database, log, or raw market-data file. Keep the snapshot and manifest local; do not add them to Git. The manifest helper verifies the snapshot seal and read-only contract, writes a new manifest without overwriting, and prints the exact SHA-256 pin of the manifest bytes for the server launch argument.

From the repository root, create one manifest in a local directory that already exists:

```powershell
python.exe -B .\tools\atlas_mcp_manifest.py --snapshot '<existing sealed health snapshot JSON>' --output '<new local manifest JSON>'
```

Use the printed 64-character digest as the separate `--manifest-sha256` launch argument. Configure a local MCP host with the equivalent of:

```json
{
  "command": "python.exe",
  "args": [
    "-B",
    "<repository-root>\\tools\\atlas_mcp_pilot.py",
    "--manifest",
    "<local manifest JSON>",
    "--manifest-sha256",
    "<printed 64-character digest>"
  ],
  "cwd": "<repository-root>"
}
```

The snapshot path is stored only in the local manifest and never accepted as an MCP argument or returned to a client. Pinning is over exact manifest bytes and exact snapshot bytes; the snapshot's internal seal is also checked. If evidence is absent or changes after manifest creation, the pilot reports `UNKNOWN/EVIDENCE_UNAVAILABLE` (or a specific safe seal/pin refusal) and does not search for a replacement. To refresh, an operator reviews a new snapshot and creates a new manifest path and pin.

## Optional one-time owner-local acceptance

Only if the owner wants to exercise the pilot locally, configure it against the reviewed existing snapshot above and make one `atlas.runtime.health` call followed by `atlas.lane.latest` for `live`, `daily`, and `history`. Confirm the response has no paths or raw data, `host_attested=false`, `trading_authority=NONE`, and the lane statuses and refusal match the sealed snapshot. For the owner-reported WS snapshot currently available to this task, expected reported fields are `HELD`, `PILOT_STOP_PONG_FRESH_PING_PROOF_REJECTED`, 50 receipts, and one missing-range count; that is an owner-reported observation, not an independent host inspection. If the manifest or source cannot be read, accept only `UNKNOWN` and stop; do not loosen ACLs or retry against raw directories.

No repeated PowerShell probes are needed. This procedure is optional and cannot turn an owner-local run into `HOST_VALIDATED` or `PRODUCTION_APPROVED`.

## Test and evidence boundary

The deterministic test suite uses synthetic, sealed fixtures (`SYNTHETIC_TESTED`) for status conversion, current reported `HELD`/gap shape, missing and tampered source, path/data redaction, timestamp and watermark conflicts, protocol discovery, tools/resources allowlists, and refused write-like or arbitrary-file requests. The real WS values above are labeled `OWNER_REPORTED_LOCAL`; no private E: files or running tasks were read by this engineering environment. Exact Windows/Ubuntu results must be taken from GitHub Actions for the final PR head, not inferred from a local synthetic test. The final #331 delivery comment records the exact candidate SHA, run ID, platforms, and test count.

Existing watchdog tests remain part of the same job and continue to cover two-observation progress rules, history checkpoint semantics, sealed Registry evidence and daily source/import linkage. This MCP adapter does not create new source receipts or claim that either owner-host observation has been independently validated.

## Security and limitations

- Stdio is the only transport. There is no listener, outbound networking, authentication bypass, public tunnel, or remote-host connection.
- Tools accept no paths or commands. Only the lane enum is accepted by the per-lane tool; resources have fixed URIs.
- The process has no scheduler/task/process-control or source-write feature. The adapter does not launch the watchdog, start an importer, or change any existing process.
- No original data, raw candle export, private keys, credentials, or trading endpoints are read or exposed.
- An old sealed snapshot can be internally valid but stale. The response includes its observation time and zero cache TTL; the adapter does not claim live freshness if the pinned source itself is old.
- `ENGINEERING_READY_PILOT_NOT_DEPLOYED` describes repository code only. Host validation still needs authorized, owner-local evidence. Production activation, remote access, custody expansion, merging, and any change to the live HOLD need separate exact owner consent.

## Rollback

The pilot is not installed or auto-started. Stop the local MCP client process and remove its local configuration entry. Keep or remove the local manifest and snapshot according to the owner's data-retention policy. No background service, scheduled task, host process, source file or warehouse record is changed, so there is no runtime rollback operation.



## Request-time freshness and registry gates

Every MCP tool call and resource read reopens the same manifest-pinned snapshot and verifies both its exact manifest bytes and snapshot bytes. It never discovers or adopts a replacement path. The server recalculates snapshot age on each request; the maximum age is 300,000 ms (5 minutes). An older snapshot is returned as `STALE`. Missing, future-dated, clock-uncertain, backwards-clock, or materially wall/monotonic-skewed evidence is `UNKNOWN`. The allowed clock uncertainty/drift is at most 5,000 ms. An existing live `HELD` refusal retains precedence and its sanitized reason.

Registry gaps, unavailable archive boundaries, conflicts, or a missing/zero source count force the history lane and overall snapshot away from healthy/verified-complete. The MCP projection applies the same rule even if a producer snapshot incorrectly marks the overall state healthy.

The focused MCP workflow runs only `test_atlas_ops_mcp*.py` on Ubuntu and Windows. It does not rerun unrelated watchdog-only tests. This remains an unmerged engineering candidate; passing CI does not authorize local host deployment or live use.

An overall `HELD` or `FAILED` state does not freeze child-lane freshness: each healthy/expected-wait lane is independently downgraded on expiry or clock failure, while any lane already `HELD`/`FAILED` preserves its own state and sanitized reason.
