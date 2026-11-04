# Core #253 — bounded incremental original historical warehouse expansion

Owner directives: #253/6630254808 and #253/6630355815. Primary original-source 15m Strategy→Factory/Lab→isolated Paper remains first priority; this is a separate additive, nonblocking lane. No G0, merge, trading, paid infrastructure or new Work dispatch.

## Current inventory (2026-11-04)

Private owner Library inventory visible in this Core session contains `ATLAS_WORK247_ORIGINAL_RETROSPECTIVE_PRIVATE_20261104.zip` with already independently verified BTCUSDT Spot 15m Feb 2024 (2,784 bars, original ZIP SHA `55066890cd3a76c97c05e94213311b17a4146d697f6abe8762b3edae8495b20e`) and Aug 2024 (2,976 bars, ZIP SHA `44e084e916a4c661b2177741d71438916388c0d34554f63cb147973aac13b094`). These **are pinned and excluded from new ingestion**. Another listed item is `BTCUSDT-1m-2024-01-01-4ec2915e610ab4e9a4d5e86a5ada1c15bbf6b5db343cdb385681d6ac97166a4e.zip`, a **daily 1m** object, NOT a third 15m monthly ZIP. It must not be silently relabeled or aggregated into an authentic native 15m source.

**Current new monthly 15m source status: READY_FOR_SOURCE.** No third owner-retained, independently verified BTCUSDT Spot 15m original monthly ZIP+CHECKSUM was identified in the visible Library filename inventory. This is an inventory observation, not proof none exists in other owner environments. No new month downloaded, ingested or queried, and no new original receipt is claimed.

## One-month next step once source is available

1. Choose the smallest newly available native monthly `BTCUSDT-15m-YYYY-MM.zip` plus its original publisher `.CHECKSUM` from owner-authorized retained inventory; independently pin exact filename, source SHA256, CHECKSUM SHA256, native member CSV SHA256 and immutable retention provenance. Verify license/use permission and original bytes privately; do not copy them into GitHub/Actions.
2. Reuse existing #211 `RawVault` immutable SHA-addressed object, Core #226 `admit_local_original` and `query_local`, existing correction ledger and Core #253 owner-authorized transfer validation. Do not create a second warehouse. Each source packet must respect 8MB and 4,096 bars. Verify native monthly 15m UTC grid count (28 days=2,688; 29 days=2,784; 30 days=2,880; 31 days=2,976), no duplicate/missing bars, same symbol/interval and exact start/end, and reject gaps or conflicting source generations.
3. Preserve original bytes and immutable source/version/manifest/packet/custody receipt, derive indexed read-only OHLCV, rerun source SHA and bar checksums on query and restart/replay; record `COMPLETE|PARTIAL|UNKNOWN`, exact missing opens, cutoff, source correction parent and SHA-pinned receipt. Never backdate `historical_known_at_ms` or promote retrospective evidence to PIT.
4. One combined per-month evidence receipt, with original ZIP/CHECKSUM/member SHA, exact bar count, gap/duplicate census, Vault admission/readback, Core query SHA and replay result; avoid repeated Audit micro-gates. Only after the main E2E complete should the final independent Audit gate #256 run.

## Resource planning (estimates, not observed transfer costs)

For native 15m: maximum 31×24×4=2,976 bars/month. The existing two original ZIPs in owner-private Work247 bundle are small enough to fit the existing Core 8MB packet cap. Budget **up to 8MB original ZIP plus 8MB staging and under ~10MB derived/SQLite metadata per month** as a conservative planning envelope (not a guarantee), approximately **up to 26MB local disk/month** plus backups/manifest overhead; SHA/ZIP validation and ~3k bar inserts/query are bounded CPU. A new monthly ZIP and CHECKSUM require **one source transfer/download each**, network bytes unknown until the actual source is selected, no paid resource approved. Validate actual file sizes and available free disk before transfer; if above source cap, stop for owner-reviewed chunk contract. No automatic bulk months, 1m conversion, new symbols or timeframes.

**Smallest real dependency:** one independently pinned, authorized *new* BTCUSDT Spot 15m monthly original ZIP plus matching original CHECKSUM (or owner approval for a bounded new source retrieval after license/network/cost review). This lane is nonblocking for the primary existing Feb/Aug E2E.

## Executable bounded source acquisition preflight (2026-11-04)

New Core-owned module `research_wp_r0/aql_core_bounded_monthly_source_preflight_v1.py`, with 6 negative/determinism tests, **does not duplicate #211 Vault or #226 warehouse**. It provides `month_window`, `source_urls`, `verify_native_month` and an **explicit opt-in** `stage_one_month`. Only new native BTCUSDT Binance Spot 15m months of 2024; February/August are hard-refused. Source is publisher's native monthly ZIP and matching `.CHECKSUM`, never daily 1m resampling. Limits 8MB ZIP, 512B checksum, 16MB decompressed CSV, exact expected 2,688–2,976 12-column native bars, 15m UTC grid, no gaps/duplicates, strict SHA. Creates source bytes only in a **caller-owned private local directory**, create-only, and returns an immutable SHA256 metadata receipt. It never asserts original 2024 issuer signature or historical PIT, never executes Vault admission, never writes raw bytes to GitHub/Actions.

Private runner preflight (no network, safe to run anywhere):

```bash
python -m research_wp_r0.aql_core_bounded_monthly_source_preflight_v1 --month 2024-03 --private-dir /private/aql/historical
```

This prints **READY_FOR_SOURCE** with the precise publisher URLs and 8MB cap, without network. To authorize one **actual** bounded transfer in a separate permitted private network runner, an operator must explicitly run:

```bash
python -m research_wp_r0.aql_core_bounded_monthly_source_preflight_v1 --month 2024-03 --private-dir /private/aql/historical --allow-network
```

This second command is documented but **has not been executed in this session**: this environment's DNS cannot resolve `data.binance.vision` and no additional owner-retained native monthly ZIP/CHECKSUM is visible. It is not a Work dispatch, automated bulk fetch, or authorization to copy source to CI. Expected network <=8,000,000 ZIP bytes +512 checksum bytes, not including protocol overhead; expected private disk up to ~26MB/month for ZIP, staging and derived SQLite planning envelope. Before running, verify actual free disk and rights/terms. Successful preflight must be followed by actual Core `admit_local_original` with #211 RawVault, `query_local` and immutable replay/coverage receipt in **same private runner**; the preflight receipt alone does NOT prove ingest.

**Latest status: READY_FOR_SOURCE, ONE NEW MONTH NOT INGESTED.** Primary Feb/Aug original E2E has since been reported complete by Factory #254/6631294940; independent Audit #256 evidence-access gate remains separate.
