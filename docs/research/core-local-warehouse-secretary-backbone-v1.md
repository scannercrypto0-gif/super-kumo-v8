# Core #253 — Local RAW warehouse, indexed historical query, strategy/Secretary distribution

**Scope:** Owner provisionally authorized coherent implementation batch B (2026-11-04), Draft PR #226 only; unmerged. This is offline, non-production research architecture. It does not certify 2024 PIT, approve a paper strategy, activate exchange/paper/live, imply full-market coverage, open holdout or G0. Factory owner #254 implements the Lab/consumer/paper-model E2E; this Core delivery does not modify Factory or Work files.

## Reuse instead of rebuild

Exact frozen dependencies:
- Core #226 prior ZIP/CSV/CHECKSUM/source custody at `7a2631325e70e70e5df25abc5f507cab53f4399e`. Actual ZIP export and stage, corrections, HistoricalLibrary query/price projection are REUSED rather than rewritten.
- RAW Vault #211 original HEAD `7d97b09c0c6ee2650a61d523acb8d8c771a99c46`, OPEN/DRAFT/UNMERGED, has existing `tools.raw_vault_offline.vault.RawVault` and `tools.raw_vault_offline.corrections.CorrectionLedger`; Core calls their public APIs only through an injected, owner-authorized `vault` object, never copies/edit their files. Isolated CI checks out this exact commit into a separate path.
- Scanner #227 original `AQL-SCANNER-V1` nomination shape and `RETROSPECTIVE_NON_PIT` are reused as a **data envelope**, not a duplicated Scanner engine.
- Factory #241 (current #250) and Work #242 scientific research contracts remain separate. The 106 preexisting original retrospective reports and the independent Audit #248 artifact checks must not be rerun.
- The owner's full-market capability map is #202/#205, not a synonym for a profitable signal engine.

## Core local source warehouse

API `research_wp_r0.aql_core_backbone_local_v1`:
```python
from pathlib import Path
from tools.raw_vault_offline.vault import RawVault  # pinned #211 checkout
from research_wp_r0.aql_core_backbone_local_v1 import (
    admit_local_original, query_local
)
root = Path("/approved/offline/core253")
vault = RawVault(Path("/approved/offline/raw-originals"))
receipt = admit_local_original(
    root, original_zip_bytes, original_checksum_file_bytes,
    externally_pinned_source_pin, exact_original_core_spec,
    decision_cutoff_ms=decision_cutoff_ms, vault=vault,
)
prices = query_local(
    root, receipt["dataset_id"], receipt["version"],
    exact_original_core_spec["start_ms"],
    exact_original_core_spec["end_exclusive_ms"], decision_cutoff_ms,
    required_source_sha256=receipt["source_zip_sha256"],
    require_complete=True,
)
```

Existing source pin must have original ZIP/member/CHECKSUM SHA and native scope in the existing Core #245 schema. Original ZIP bytes pass the verified native 12-column parser and are **kept byte-for-byte** as immutable RAW objects. The existing #211 Vault stores objects at content SHA locations with fsync, atomic create-only mutation and verified readback; its optional `CorrectionLedger` is invoked for generation>0 with a stable base-family identity, explicit version identity per Vault object, Core correction parent and declared reason. No earlier bytes or ledger entries are rewritten. Existing Bridge `OfflineBridgeStager` independently stages source/packet checkpoint+committed receipt and replays to the in-memory HistoricalLibrary when restarting. The separate Core SQLite WAL+FULL-sync indexed **derived** price partitions store one immutable dataset/version/sha with exact per-bar checksums and lower-bound availability; range queries verify source against the original Bridge packet before returning any prices. There is no new duplicate bar parser or evaluator.

**Storage status distinction matters:** if the caller omits the pinned `vault`, Core still has its existing durable original-byte Bridge stage and derived SQLite, but returns `OFFLINE_LOCAL_STAGE_ONLY` / `vault=NOT_CONNECTED_CORE_STAGE_ONLY`. This is NOT a complete combined #211 RAW Vault integration. Only with actual injected #211 Vault and verified `admit/read` does Core return `OFFLINE_LOCAL_WAREHOUSE_COMMITTED`. The optional adapter NEVER claims external source provenance or power-loss-proof offsite custody. The 2024 historical known-at remains NULL and `RETROSPECTIVE_NON_PIT` at both storage and query level.

SQLite `generations` maps `dataset_id,version,source_sha,manifest_sha,packet_sha,custody_receipt_sha,correction_parent_sha,coverage,evidence_class` and a sealed original admission. `price_bars` holds derived OHLCV keyed `dataset,version,bar_open`, exact original bar checksums and observation lower-bound. Both tables deny conflicting generation/bar rewrites. Source check is performed AGAIN against original Core staged bytes on query, not inferred from SQLite index. Query `aql.core.local-history-query.v1`: bounded half-open UTC ms, exact source SHA/version/cutoff, `COMPLETE/PARTIAL/UNKNOWN`, precise missing grid, full OHLCV, nullable historical known-at and `historical_pit=NOT_ATTESTED`. Strict consumers require `require_complete=True`; gaps or not-yet-retrospectively-visible bars fail closed.

**Source limit:** native Core #245 accepts at most 4096 bars / original ZIP <=8MB *per immutable source*. A whole 30-day 1-minute monthly ZIP (~43,200 rows) is NOT accepted as one packet. For genuine 1-minute backfill this pilot requires independently pinned daily original packages or a separate, owner-reviewed chunk/index contract with original-byte lineage; never silently truncate a monthly archive. At this handoff, authentic Work-retained originals known to exist are Feb and Aug 2024 BTCUSDT Spot 15m (2,784 / 2,976), not the proposed three-symbol Spot 1m/30-day pilot. **This Core session does not have the retained private bytes**, so current CI uses synthetic original-format ZIPs only, and no Core-local genuine-source smoke is claimed.

## Strategy-addressed Scanner to Secretary distribution

API `research_wp_r0.aql_core_secretary_routing_v1`:
```python
from research_wp_r0.aql_core_secretary_routing_v1 import (
    enqueue_nomination, poll_nomination,
    acknowledge_nomination, retry_or_quarantine, route_trace
)
queue_receipt = enqueue_nomination(
    root, scanner_v1_as_dict, strategy_id="RESEARCH_ID",
    strategy_version="v1", warehouse_receipt=receipt,
    lane="FAST", idempotency_key="SOURCE_AND_STRATEGY_EVENT_ID",
)
item = poll_nomination(root, now_ms=offline_clock_ms, lane="FAST")
# The caller explicitly hands it to an isolated research consumer,
# not a broker or exchange. Caller is responsible for actual delivery.
ack = acknowledge_nomination(
    root, message_id=item["message_id"],
    payload_sha256=item["envelope"]["payload_sha256"],
    acknowledgement_sha256=consumer_evidence_sha256,
)
```

The Core routing envelope `aql.core.scanner-secretary-offline-route.v1` is strictly tied to strategy_id/version and a scanner v1 nomination, actual Core warehouse receipt SHA and original ZIP/manifest SHA, with `strategy_authority=OFFLINE_RESEARCH_ONLY_NOT_APPROVED_PAPER`, `scanner_strategy_decision=NOT_PERFORMED`, `discoverer_dependency=OPTIONAL`. The Scanner engine owns screening; Core does **not** decide trades, invent indicators or certify a Paper-approved strategy registry. Scanner inputs with `publishable=true`, `delivery_authorized=true`, `LIVE_PIT` on this retrospective path, mismatched source SHA or missing provenance are rejected. Scanner->Discoverer is not mandatory. Real Scanner #227 full engine invocation is a **separate unmerged dependency**, not implied by accepting an envelope-shaped dict.

Secretary `FAST/SLOW` routing is SQLite outbox only: deterministic queue priority, create-once message idempotency, collision denial, bounded exponential retry, terminal quarantine, caller-supplied ACK, append-only hash-linked event trace, on-read corruption check and reopen/recovery. `route_trace` checks that every event and the final outbox state agree. `poll_nomination` is read-only; no network dispatch or broker call. Delivery semantics are *at least once with idempotent message keys*, not globally exactly once. An ACK is a **caller-reported research consumer receipt**, not observed external delivery or trading order confirmation.

## Factory #254 exact joint interface

The pinned factory worker needs the resulting:
- `aql.core.local-history-warehouse.v1` receipt: source ZIP/member/CHECKSUM SHA, original manifest/packet/receipt hashes, dataset/version/parent, original quote metadata, `vault` status and coverage.
- `aql.core.local-history-query.v1`: contiguous price-bearing historical rows with exact per-bar SHA, source/version/cutoff and no fake known-at; `UNKNOWN/PARTIAL` must block eligible consumer scoring.
- `aql.core.scanner-secretary-offline-route.v1`: strategy/version, scanner nomination/source pins, Secretary lane, message key, acknowledged trace; Factory may bind a **research-only simulated decision/position/result** after independent evaluation. It must never infer a Paper authorization or real fill from Core queue ACK, and must preserve research- and paper-lane isolation.

Core doesn't implement Factory rule projection, Lab ledger or Paper-model fill: #254 owns them. A genuine joint E2E is **NOT_CONNECTED** until Factory supplies an exact schema and an authorized original source is available in the same offline runner. The 74-test Core + 3-test pinned Vault regression does not constitute a complete Factory integration.

## Source terms and evidence limitation

Binance's current `binance-public-data/TERMS_AND_CONDITIONS.md` updated 2026-08-26 separately governs the datasets under a **CC BY-NC-SA 4.0 non-commercial grant**. It expressly allows only personal, nonproduction research/backtesting among permitted uses and restricts commercial/live trading/signal distribution. This is stricter than the repository's code MIT label. The owner must confirm license eligibility and attribution/use scope before any new download or subsequent redistribution/commercial use. **No new public archive was downloaded or source acquired in this execution**; official endpoints were researched only. No rights to commercial use were assumed. This legal constraint is separate from provenance and historical PIT (still NOT_ATTESTED).

## Exact validation boundary

Dedicated `tests/test_aql_core_backbone_local_v1.py` covers original ZIP→stage→SQLite→read/restart, source/cutoff/UNKNOWN, corrected source/version, forged price index, fake source, strategy-specific routing and Secretary ACK/idempotency/backoff/quarantine/trace tampering. `tests/test_aql_core_raw_vault_pin_v1.py` uses actual pinned #211 RawVault from a read-only checkout (rather than a fake stand-in), tests immutable original SHA readback, repeated admission, correct append-only correction ledger and conflicts. Both run from **one existing consolidated Core-focused workflow** `.github/workflows/aql-core-research-vertical-slice-focused.yml`, reusing 65 prior focused negative tests. No private source files are present in GitHub Actions or the codebase. Full independent Audit review must be one final limited delta against exact heads, without reopening prior accepted Work #247 106 reports.

**Honest status:** built/TEST_ONLY integration with actual pinned RAW Vault; authentic-source Core runner access NOT_CONNECTED; full Scanner engine/Factory/Lab/paper-model E2E NOT_CONNECTED; 2024 known-at/universe NOT_ATTESTED. No PR merge, G0, holdout, exchange API calls, paper/live or trading.
