# Saved research disposition

This command reads one owner-permitted saved retrospective cycle. It reopens
the native Core local query and a detached, checkpointed Factory store,
checks the pinned plan, original result, same-cohort Scanner/Factory receipts
and supplied UTC as-of, and calls the existing scientific research intake
gate. The gate reports insufficient evidence. No Lab calculation or
Secretary dispatch is performed. No source ZIP is opened.

Use an isolated copy of the pinned periodic runtime (Core #286 and Factory
reader #267, as staged by the [Windows operator guide](recurring-research-windows.md)).
Copy `tools/atlas_saved_research_disposition.py` and
`research_wp_r0/aql_factory_authentic_research_admission.py` from this #271
checkout into their matching paths in that isolated runtime. Run from the
staged runtime with its root and src on PYTHONPATH, and supply the originally
recorded plan and result pins. Use only quiescent, checkpointed saved state.

```powershell
$env:PYTHONPATH = "$tree/src;$tree"
& $python -B -m tools.atlas_saved_research_disposition --saved $savedWindow --plan $originalPlan --plan-sha256 $planPin --result-sha256 $resultPin --as-of-ms $asOfUtcMs --saved-only --output $reportPath
```

Choose an as-of at or after the recorded historical processing cutoff.
A clean-process replay with the same inputs returns the same SHA and
keeps the sealed report unchanged. A different report cannot overwrite
that path. Output carries trace ID, both Core pins, Scanner and Factory
pins, scientific refusal, Lab ineligibility and Secretary WAIT with null
dispatch. The Core245 receipt is preserved by its existing parent pin;
the saved readback invokes Core253. Historical entries remain NO_CURRENT_ENTRY.
