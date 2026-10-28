# Core proof sweep performance check (manual; non-gating)

Run from the repository root after installing the project dependencies:

```bash
PYTHONPATH=src python benchmarks/core_proof_sweep_latency.py
```

The harness measures **journal commit + PERSISTED ACK** latency in milliseconds,
in two counterbalanced sequential pairs: baseline→sweep and sweep→baseline. It prints per-pair p50/p95/p99/max/mean and the with-sweep/baseline latency ratios. It uses
isolated temporary SQLite files and never touches production data.

**Interpretation and limits**
- These results are observational only. They are **not** a G0 acceptance
  criterion, production SLO, or evidence that the hot path is safe.
- Run repeated trials on the same representative storage and hardware; reverse
  trial order in separate runs to expose cache and thermal bias. Capture OS,
  filesystem, Python/SQLite versions, journal size, sample count and load.
- A single small test may be dominated by filesystem cache and scheduling.
  This is not a substitute for sustained multi-symbol load, disk pressure,
  process restart and p99.9 tail-latency tests.
- Proposed **provisional** performance gate for owner/Factory/Audit review:
  no material sustained regression in p95/p99 versus a matched baseline,
  no increase in G1 write errors, and no evidence gaps after full sweep.
  Numeric limits require representative baselines and explicit G0 approval.
- The sweep uses a soft page-boundary time budget; a single page can exceed
  its nominal limit. It must remain outside the live ingest hot path.
- No scheduler or trading mode is activated by this benchmark.

## Owner provisional decision — B (latency AND sweep coverage)

Do not select a lower-duty-cycle setting solely on write p95/p99. Compare
per-arm `sweep_work.slices`, `pages`, `complete_cycles`, `added`, and
`existing` alongside write latency. These are **work counters**, not a
measured maximum late-ACK discovery delay: that requires a separately
controlled injected late-ACK experiment and elapsed-time measurement.
A setting that makes writes faster but leaves full cycles unfinished is
not accepted. Final numerical thresholds remain pending representative
measurements, Factory/Audit review, and G0 approval.
