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
