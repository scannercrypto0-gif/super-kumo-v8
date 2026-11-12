# Actual retained-market research cycle — Issue294

**Local: PASS_FIRST_RESEARCH_ENGINEERING_CYCLE. Science: REAL_PIT_OOS_BLOCKED.**
Exact-head CI and consolidated receipts are reported on PR296/Issue294.
CI simulation is not substituted for actual private-data execution.

## Frozen design and reuse

Owner explicitly authorized read-only historical archives. Located actual
May/June2024 BTCUSDT Spot15m ZIPs; March/April and G2 observer were not used.
`market-plan.json`/`.sha256` bind source hashes,5856 grid slots, one SMA3>SMA8
candidate, seed294, risk1%, sixteen-bar modeled holding, A/B/C targets and
allocations, taker/passive/stress costs and a separate fixed periodic null
independent of signals/outcomes. No tuning or winner selection. Initial freeze
preceded first market outcome read. Recorded compatibility amendments added
native Scanner import dependencies and train/validation reporting; no strategy,
cohort, cost, exit or selection parameter changed. A2026 freeze is not a2024
contemporaneous independent witness.

UTC splits, end exclusive: TRAIN May1–20; VALIDATION May20–June1;
EMBARGO June1–4; HOLDOUT June4–July1. All source rows admitted for integrity;
only TRAIN/VALIDATION enter evaluator kernels. Holdout is not evaluated, but
cannot be certified genuinely untouched independent prospective OOS.

Actual reused interfaces (unmodified producer source):

- Scanner277 `_eval_strategy`, native indicator/AST kernels and prefix replay.
- Discoverer276 `DiscovererLedger`/`DiscoveryCandidatePackageV1`, one native
  registered→pending→complete attempt and immutable candidate/restart read.
- Native `research-plan-1` commitment and verification.
- Factory291 immutable experiment registration/readback, v2 store and
  `_store_package`; `_path`/`_summarize`/`_modeled_trade` Decimal kernels.

The HIGH-LEVEL synthetic-only PKG02 packet API is not relabeled or used to
admit real data. This new adapter validates retained actual archives, then
uses lower-level hypothetical execution kernels on actual prices, preserving
`SYNTHETIC_ASSUMPTION_NOT_ATTESTED` execution labels and actual source class.
It does not rebuild an engine/registry/scheduler.

Main90af9794880cbeb00e7e974bfa906ff5e9666183;
Core290612d1444ff36ed08b63fd0a98bb8d4e71f88cd0d;
Factory291ea4ffd5ce278d93588338122ab6ac1af8ec4da26;
Discoverer276c568e3b281795f9eef2165c0e6f571b87157a23c;
Scanner277ccf57ad3db7e71290a8321840e800136567e3af4;
Work2356acbcc7fc243b132f58170df4c6469bbf7f4eff8;
ScannerB30c37ae56851488b882998c7fa0085ec51dbfc92.
Exact imported source-byte digests are retained in the plan.
Current292ccd906ac6d770e1364889623cd79bb215f7b5c63 and
293c01f526e762a014e5ed84ca3cf695b9d77502ab3 are accepted reference contracts,
not rerun. Audit134/6775950476 accepted the old four-lane synthetic composite
at51c9d54215094f34d41eeded10cab8ae660fa839; reuse its evidence, not execution.

## Reproduction

From repo root (first command fetches Git source only):

```text
python -B tools/first_research_cycle/stage_dependencies.py --fetch --output <new-deps>
python -B tools/first_research_cycle/market_cycle.py --source <authorized-historical-export> --deps <deps> --output <new-run>
```

Omit `--fetch` for already-retained Git objects. Market runtime is fully offline,
reads only two named ZIPs/CHECKSUMs, opens no upstream database/observer/broker,
and writes only its isolated run directory. No market acquisition or raw upload.
Retry is immutable/idempotent; changed source/plan/candidate cannot overwrite.

Crash/recovery: add `--crash-after-commit` on a new run, expect exit73, then rerun
the same command without that flag against the same directory. The native
Factory COMMIT occurs before caller ACK/ledger completion. Recovery must match
fresh output bytes, with no duplicate attempt/trial/cost/outcomes. Corrupt or
missing ledger against an existing store fails closed. Native observational
ledger clocks remain separate; its own content digest excludes wall-clock ns.
No canonical-result normalization is applied.

Focused joined tests, PowerShell:

```powershell
$env:PYTHONPATH='.;src'
$env:CYCLE_DEPS='<staged-deps>'
python -B -m pytest tools/first_research_cycle -q --basetemp=.cycle-tests
```

POSIX: `PYTHONPATH=.:src CYCLE_DEPS=<deps> python -B -m pytest tools/first_research_cycle -q --basetemp=.cycle-tests`.
CI uses explicitly SIMULATED_ADAPTER_TEST archives, never private actual data,
and reports PASS_ADAPTER_SIMULATION_ONLY. It exercises native joined interfaces,
two fresh processes, exit73/restart/idempotency, corruption, wrong source and
candidate, missing populations, fake PnL/fill/ACK/authority, false PIT/OOS,
holdout and temporal violations. No accepted G4/old producer suite rerun.

## Phase receipts and honest limits

| Phase | Executed engineering proof | Scientific limit |
| --- | --- | --- |
| F0 | exact two-month freeze, one candidate/null, disjoint ownership | retrospective local freeze, no external witness |
| F1 |5856 source slots/grid/hashes/checksum; all-slot census| no publisher signature or decision-time availability |
| F2 |native candidate, one closed attempt, immutable Factory trial| no broad search or promotion claim |
| F3 |18 cells,15282 cost rows, cost-once/fraction conservation| actual prices, assumed execution; passive UNKNOWN |
| F4 |all unknowns retained; separate TRAIN/VALIDATION/null diagnostics| no winner, alpha or regime generalization |
| F5 |actual Windows two-process equality and exit73 recovery; focused cross-OS CI| actual private-data Linux replay NOT_RUN |

Census:7 UNKNOWN,1457 EXIT_SIGNAL,1512 ENTRY_SIGNAL,288 EMBARGO,
2592 SEALED_HOLDOUT=5856. Separate1 Discoverer attempt,1 Factory trial,
1512 candidate entries,186 null entries,18 policy/scenario/cohort cells.
Unknowns are never zero/favorable fills. Full-population aggregates remain null
when unknown. Known-subset gross/net diagnostics explicitly exclude unknowns
and are not expected return/alpha. Independent overlapping per-entry models
are not a capitalized portfolio. Ledger/checkpoint/store remain audit-ready
inside the local new run directory; no raw/price-level results are published.

Passive queue/nonfill/partial/adverse-selection/cancel/reprice and market-impact
timing are unsupported from OHLC; passive fill remains UNKNOWN. C is staged
targets with next-bar breakeven, not continuous trailing. Intrabar stop+target
is UNKNOWN. No real fills, source ACK, orders, G0/stage/merge/trading authority.

Attribution: **Binance Vision public market data**. Current [dataset terms](https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md)
version1.0/2026-08-26 describe non-commercial research under CC BY-NC-SA4.0;
the repository's MIT code label is not substituted for dataset terms.
Owner authorized local historical research. Acquisition-time rights, independent
custody/known-at/PIT remain NOT_ATTESTED. No raw redistribution; redistributed
derived analysis is attributed to Binance Vision under **CC BY-NC-SA4.0**.

Only `tools/first_research_cycle/**` and its dedicated new workflow change.
Parallel Issue295 capacity files, existing engines/source stores and G2 are
unchanged. Initial private-access automatic rejection was not bypassed; owner
subsequently explicitly authorized the three named historical archive paths.

### Ordered Scanner receipt (forward only)

New runs publish `scanner-census.json` before the final `result.json`.
The versioned canonical receipt contains the ordered decision rows, source and
configuration digests, Discoverer and Factory IDs, and the source rights grade.
Its zero-based list position is the native index used in `entry<N>`. The
result seals the receipt and Factory retains the independent census digest.
The output directory must support same-volume hard links (for example NTFS
or ext4). The writer fsyncs file data before publishing and syncs the directory
on POSIX. A completed retry verifies existing evidence and preserves its bytes.

On a detached copy of the completed directory, run:

```sh
python -B -m tools.first_research_cycle.verify_run --run completed-run --output verification.json --entry-id entry20
```

Replace `entry20` with a candidate entry from that run. Keep the result SHA-256
independently to authenticate the packet. The verifier reports the native row
and its canonical digest after verifying ordered census membership and the
Discoverer/Factory linkage. Known-at remains UNKNOWN. The ZIP adapter has a
source-row digest and retained archive proof, with no authenticated Core
receipt ID. The verifier therefore reports `SOURCE_BLOCKED` for that part of
the link.

Existing accounting-only readback retains its original shape for legacy
results. A membership request against a legacy result fails closed. Existing
outputs cannot be backfilled by rerunning this writer. New result digests
include the receipt SHA; #300's existing pinned adapter and reference results
remain on their original contract.
