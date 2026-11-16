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

## Stage 3 disposition and preview

Append `--stage2-evidence $stage2Evidence --stage2-evidence-sha256 $stage2Pin`
and use a fresh output path. Supply the separately retained canonical seal
of the Stage 2 disposition. Its plan, strategy and report pins must match
the saved strategy report. Supply the Stage 1 health export and file pin.
The report keeps the last success, latest failure and as-of freshness.
A `TEST_ONLY` export describes the fixture runtime. Continuous service is
unattested.

The nonactionable Telegram preview references the existing immutable
Strategy Operations preview receipt. Replay keeps one local record. For
future delivery, obtain separate owner approval for recipient, channel,
message and sending window. Qualify a separate delivery adapter with
secrets kept outside reports and logs and a delivery key derived from the
preview receipt. This report command stays in preview mode.
