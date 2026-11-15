# Saved strategy outcome report

Use retained, authorized snapshots only for readback.
The command uses #267's native saved Lab reader and #309's native independent
modeled-accounting and ordered Scanner verifier. It does not run a strategy on original prices,
open holdout data, or start a Paper service. The legacy verifier's SQLite
sidecars are confined to a disposable copy.

Stage the same isolated #286 runtime used by the saved disposition guide.
Overlay `tools/first_research_cycle` from exact #309
`35972ffe115cbc1fcde5655d56f1484b19452ca0` and the saved Lab reader and
Factory research store from exact #267
`831fe426ea55f6b30fbbb86ddfe01a7ed194eba2`. Copy
`tools/atlas_saved_strategy_report.py`,
`tools/atlas_saved_research_disposition.py` and its Factory admission import
from this #271 checkout into the staged runtime. Use a verified quiescent
copy containing market-plan.json, result.json and factory.sqlite with
no SQLite sidecars. If result.json pins an ordered Scanner receipt, also
include scanner-census.json, candidate.json, native-plan.json and
discoverer-ledger.json from that run. Legacy snapshots, including the #300
snapshot, retain their original receipt and limitations.

```powershell
$env:PYTHONPATH = "$tree/src;$tree"
& $python -B -m tools.atlas_saved_strategy_report --saved $snapshot --plan-sha256 $planPin --result-file-sha256 $resultFilePin --store-file-sha256 $storePin --strategy-sha256 $strategyPin --saved-only --output $report
```

The JSON seals the original lineage, split, strategy, cost assumptions,
accounting verifier, counts and per-cell known-subset totals. Unknowns stay
in the denominator. No absolute equity, portfolio return or actionable price
is inferred. Re-run with the same pins to verify an unchanged report.

## Single-job saved batch

Stage `tools/research_capacity_scale` and its Factory runtime from #297
`dd3e149afe73d9d04c9892ad35005b04fb675fff` and the bridge tools from #300
`403e247a807b165bc1d6c63991981ce10bc7f6c7` in the same disposable
runtime. Keep the explicitly staged #267 saved readers and #309 verifier.
The archive-dispatch entry point in #300 is for its source-enabled workflow.

```powershell
& $python -B -m tools.atlas_saved_strategy_batch --saved $snapshot --plan-sha256 $planPin --result-file-sha256 $resultFilePin --store-file-sha256 $storePin --strategy-sha256 $strategyPin --report-sha256 $previouslyAcceptedReportPin --saved-only --output $report --checkpoint $batchStore
```

Use a dedicated checkpoint outside the snapshot for each job. The native
store seals one scope and one terminal result. On restart an accepted,
externally pinned report is published from that checkpoint without another
accounting pass. Rejected and failed terminal states stay in the checkpoint.
The output is the same sealed JSON as the standalone reader. Dashboard
consumers can read the evidence grade, source and split, cost assumptions,
opportunity and outcome counts, and cells grouped by partition, cohort,
scenario and exit policy. Only the report output is intended for consumption.
