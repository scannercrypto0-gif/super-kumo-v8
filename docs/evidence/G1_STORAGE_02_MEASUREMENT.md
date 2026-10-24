# Phase1 local Windows measurement — Issue #71

Synthetic512 final bars,8 symbols, no live traffic. Python3.14.3 / Windows11. Exact source SHA256 values and raw measurements are in [JSON](g1_storage02_windows.json). Input fixture has no compression. Measured on2026-10-24T10:06Z; concurrent local test activity affects timings.

| Item | Actual measurement |
|---|---:|
| Archive JSONL | 558,728 B |
|8 manifests |16,929 B |
|SQLite catalog (including fixed allocation)|135,168 B |
|Archive total / row|1,388.330 B |
|Journal snapshot|344,064 B |
|Archive8 batches|2.814s |
|Verified coherent backup|2.750s |
|Verified restore|2.984s |
|Core commit median / p95 in initial sample|49.566 /138.526 ms |
|20 core commits while archive worker blocked: median/p95/max|33.358 /59.975 /96.687 ms |

Exact512 archived rows/keys/full hashes and512 source rows restored;18 inventoried files,1,054,889 B (inventory itself excluded), caller-retained digest a1943762590dcafd6c15981f2a6b00ffcc9ef5b326409d9ee4a89b7be0235ab3. Disposable copies were deleted by temporary-directory cleanup after the drill; this digest is evidence of that drill, not an available offsite backup. No independent device or RPO guarantee.

## Projection using measured small-sample archive B/row

Rate=symbols×1,440/day; bytes=rate×days×1,388.330078125. Decimal GB. These are extrapolations, not measured large archives; fixed catalog pages, actual payload entropy/index growth and partitioning can change B/row.

|Symbols scenario from #67|30d GB|90d GB|365d GB|
|---|---:|---:|---:|
|10 low|0.5998|1.7993|7.2971|
|100 base|5.9976|17.9928|72.9706|
|500 high|29.9879|89.9638|364.8531|

These archive totals EXCLUDE original journal, hot SQLite, PIT context, raw research artifacts, WAL, partial/quarantine directories and every backup copy. #67's separate measured journal+hot extrapolation at500 symbols was257.27 GB/year; adding this archive gives roughly622.12 GB primary/year before context/research/WAL. One extra full copy of that combined primary approaches1.24 TB aggregate; three copies approach1.87 TB across devices, before richer context data (high PIT assumption alone1.168 TB/year). This is not a current disk-budget authorization or a claim1 TB is sufficient. Local capture horizon and independent backup media must be budgeted before production. Measured fallback is intentionally redundant/inspectable; versioned Parquet/compression and incremental backup inventories remain cost-reduction follow-ups requiring independent measurement.

Default64 rows/batch amortizesfsync within8 segments in thisfixture; no per-symbol partition. Sparse scheduled invocations can still produce tiny segments; no in-place compaction/pruning implemented. Latency observations show this fixture's core commits did not await the blocked archive; different loads were not controlled enough for a relative performance/speedup claim, and they are not host-isolation or deadline guarantees.

Default10 GB archive reserve,8192 backup files/2 GB/60s budgets are protective implementation defaults, not tested capacity guarantees. Proposed hourlyjournal RPO/nightlyarchive RPO and4h RTO require an authorized independent destination and repeated realistic restore drills. Windows directory fsync is explicitly unsupported; no power-loss certification.

Measurement source hashes identify initial PR73 commit efe1f5fe48e134858b14383ce4840868d5a51ddb. Subsequent source-only formatting removes trailing blank lines; implementation semantics and recorded measurement remain unchanged. Final-head CI separately verifies the published review tree.
