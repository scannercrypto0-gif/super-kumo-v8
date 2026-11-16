# Saved operator report

This read-only release slice consumes a previously sealed strategy report,
its detached successful batch checkpoint, exported Windows runtime health
and the Phase 5 preflight. Existing producers remain on their owner drafts.
The runtime uses the exact #297 Git object and the existing Factory store.

Fetch `dd3e149afe73d9d04c9892ad35005b04fb675fff` and run
`python -B tools/atlas_operator_stage.py <new-runtime-directory>` in this
checkout. Run from the staged directory with its root and `src` on
`PYTHONPATH`. Supply separately retained pins and an explicit as-of time.

```powershell
python -B -m tools.atlas_operator_report --strategy $report --strategy-sha256 $reportPin --batch-checkpoint $savedBatch --health $health --health-sha256 $healthFilePin --preflight $preflight --preflight-sha256 $preflightPin --checkpoint $operationsStore --output $operatorReport --as-of-ms $asOfMs
```

The saved batch is verified on a disposable copy. Writes go only to the
separate Operations checkpoint and sealed report destination. Runtime
health is reported as captured and aged to the supplied as-of time. The
operator tool never starts a scheduler or connects to a market. The
cross-platform check uses generated fixtures and reads no private payloads.
