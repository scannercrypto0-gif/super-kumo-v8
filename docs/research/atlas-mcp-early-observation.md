# MCP EARLY_OBSERVATION — read-only qualification

**Profile:** `EARLY_OBSERVATION`  
**Snapshot:** `atlas.operator.early-observation.v1`  
**Transport:** existing local MCP stdio server only  
**Status:** engineering candidate; no owner-host run or deployment

This profile is explicitly separate from the six-input strict watchdog snapshot. It does not weaken the strict manifest contract, infer missing receipts, create source pins for absent inputs, or turn worker success into imported-data health.

## Inputs and scope

The builder accepts only explicit file arguments, at most one each:

- `--history`: `aql.warehouse.full-history-checkpoint.v1` or `aql.warehouse.full-history-continuation.v1`.
- `--registry`: one existing sealed `aql.warehouse.registry-snapshot.v1`. The builder checks its seal and bounded metadata; it does not scan SQLite, replay archives, or revalidate physical rows.
- `--daily`: existing `aql.recurring-runtime.health.v1` export.
- `--live`: existing authorized `atlas.ws.continuous-report.v1` handoff from Work 1.
- `--previous`: optional sealed EARLY_OBSERVATION snapshot used for a two-observation comparison.

No directory traversal, archive opening, database access, network calls, subprocesses, scheduler or service control are used. The CLI requires separate existing approved input and output roots; each supplied report must be a direct child of the input root, and output is create-only as a direct child of the distinct output root. The prior snapshot is read only from the output root. This blocks arbitrary path arguments; the operator must select approved directories outside protected trial paths. Each report is bounded to 256 KiB; maximum explicit file count including the prior observation is five; maximum total bytes are 1,310,720. Output is bounded to 256 KiB. Refresh is manual only, at least five minutes apart when a prior snapshot is supplied. Valid wait times are limited to 24 hours. A refresh stops if input budget or its two-second wall / one-second CPU budget is exceeded. The deterministic fixture test measures Python allocator peak and elapsed time against the test budget.

Paths never enter the output. Each supplied input includes its actual byte digest, schema, observation time, freshness and evidence grade; absent or untrusted inputs have no pin and appear as `UNKNOWN`.

## State rules

| Lane | Evidence rule | Conservative result |
| --- | --- | --- |
| History | One valid continuation/checkpoint plus an optional sealed Registry summary. A second observation must keep the same continuation identity and advance committed counters before progress is reported. Registry gaps, unavailable boundaries or conflicts are visible. | `UNKNOWN` until linked evidence and a second observation; `STALE` for gaps/conflicts or expired reports; `FAILED` for an explicit source/import failure. |
| Daily | Worker health and cadence may be shown. No Daily import receipt/Registry link is consumed by this early profile. | `EXPECTED_WAIT` only with a valid future next-check; otherwise worker success alone remains `UNKNOWN`. Expired exports are `STALE`; reported failure is `FAILED`. |
| Realtime | Only a supplied Work 1 report is read. A live HOLD remains visible. Progress requires a second observation with the same config/policy identity, a later committed cursor and a changed receipt pin. | Missing report is `UNKNOWN`; explicit HOLD/FAILED is preserved; stale receipts stay `STALE`; one report cannot claim healthy progress. |

Overall precedence is `FAILED`, `HELD`, `STALE`, `UNKNOWN`, then `HEALTHY_PROGRESS` or `EXPECTED_WAIT`. An untrusted clock suppresses progress and expected-wait claims. The MCP request-time reader keeps the five-minute TTL, pinned manifest/snapshot checks and clock rollback/drift rules. An expired early snapshot becomes `STALE`; a held lane remains `HELD`. Host attestation and trading authority are always false/none.

The strict six-input full pilot remains unchanged. Its manifest schema and snapshot schema cannot be mixed with EARLY_OBSERVATION. Both profiles expose only the existing fixed read-only MCP tools and four resources; neither adds a listener, network route, arbitrary file read or write tool.

## Fixture verification

CI runs the early-profile unit suite and the existing strict MCP suite on Ubuntu and Windows. The fixture stdio test performs initialize, list, health call, resource read and normal EOF exit. It checks missing inputs, partial lanes, stale/future times, wall-clock uncertainty, bounded expected waits, HELD/FAILED precedence, worker-without-import linkage, source/session mismatch, two-observation progress, malformed/duplicate JSON keys, symlink/hardlink/path traversal refusal, replacement during read, request-time TTL, file-size and approved-root refusal, bounded fixture resources, create-only output, manifest pinning, malicious-field redaction in both snapshot and MCP projections, and read-only contracts.

These are `SYNTHETIC_TESTED` results. They are not owner-host evidence. The known live 24-hour trial remains `UNKNOWN` until Work 1 supplies its exact genuine report. No host pilot ran in this qualification because no approved host-capable path and complete report handoff were available; product protections were not bypassed.

## Local invocation shape

Only after the exact head is independently accepted, authentic bounded exports are available outside protected trial paths, and an approved output directory exists:

```powershell
python.exe -B .\tools\atlas_early_observation.py --approved-input-root '<approved sanitized handoff directory>' --approved-output-root '<separate approved pilot output directory>' --history '<direct child of approved input root>' --registry '<direct child of approved input root>' --daily '<direct child of approved input root>' --live '<direct child of approved input root>' --output '<new direct-child file in approved output root>' --clock-uncertainty-ms <measured value>
```

For a later observation, use new current report files, a new output path, and `--previous '<prior EARLY_OBSERVATION snapshot>'` from the approved output root. Do not point this profile at raw ZIPs, SQLite files, service directories or the running 24-hour trial. Missing evidence yields `UNKNOWN`; there is no fallback search.

Create the local early manifest and run the transient stdio server with the same approved output root:

```powershell
python.exe -B .\\tools\\atlas_mcp_manifest.py --profile early --approved-output-root '<approved pilot output directory>' --snapshot '<direct child early snapshot>' --output '<direct child manifest>'
python.exe -B .\\tools\\atlas_mcp_pilot.py --profile early --approved-output-root '<approved pilot output directory>' --manifest '<direct child manifest>' --manifest-sha256 '<printed manifest SHA-256>'
```


## Current gate

**`EARLY_MONITOR_READY_HOST_BLOCKED`** pending an applicable independent review of the exact changed head, genuine bounded report availability (Work 1 realtime handoff in particular), and an approved host-capable read path plus separate output root. No source imports, physical reconciliation, persistent deployment, service/task change, merge, or trading action is authorized by this profile.
