# Issue294 — initial intake record (superseded by actual market cycle)

**Current execution and reproduction: see [MARKET_CYCLE.md](MARKET_CYCLE.md).**
The source-access blocker recorded below was resolved by explicit owner read
permission and discovery of actual May/June2024 archives. The old assessment
is retained as history, not the final package status. Use `market_cycle.py`
with `market-plan.json` for the executed cycle; `cycle.py` remains intake-only.

**BLOCKED_EXACT_DATA_RUNTIME_DEPENDENCY.** This is an executable intake and
native-plan commitment seam, not an executed market research cycle. It has no
PASS_FIRST_RESEARCH_ENGINEERING_CYCLE path. Never confuse passing its focused
tests/CI with running F1–F5 or accepting a real-market cycle.

## Frozen boundary and reuse

Base main `90af9794880cbeb00e7e974bfa906ff5e9666183`. Exclusive ownership:
`tools/first_research_cycle/**` and its dedicated new workflow only. Parallel
Issue295 owns capacity scheduling/benchmarks/resume; this package edits none of
those engines or existing four-lane paths. No scheduler, registry, backtester,
cost engine, observer, downloader, DB writer or automatic promotion is added.

Read PM OS #205/6721828613, /6721846844, /6741235513, #202, #134, #271,
owner execution/exit decision #205/6760348084 and Issues294/295 at intake.
Four refreshed open/draft/unmerged heads:

| PR | HEAD | Base |
| --- | --- | --- |
| 290 | `612d1444ff36ed08b63fd0a98bb8d4e71f88cd0d` | `99c27ea2c1a4d41aaae361141301a8a9ea3b33c3` |
| 291 | `ea4ffd5ce278d93588338122ab6ac1af8ec4da26` | `04b63cc9b406b1f3eae2ac7de5d43ebda26dbfdf` |
| 292 | `ccd906ac6d770e1364889623cd79bb215f7b5c63` | main above |
| 293 | `c01f526e762a014e5ed84ca3cf695b9d77502ab3` | `182331b90efdcc31cf04476200fe09b45e16997c` |

Independent Audit #134/6775950476 already accepted the fresh four-lane
**offline synthetic** composite at `51c9d54215094f34d41eeded10cab8ae660fa839`,
[Windows/Ubuntu CI42875786658](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/42875786658).
Its 65-test receipt, 24 Scanner decisions, three Discoverer attempts, one Factory
trial, ten H variants and separately 72 execution-model rows are REUSED EVIDENCE,
not rerun, not new market populations. Previous PKG04 missing research/mature-G2
blockers were corrected at current292; do not repeat the obsolete diagnoses.

The accepted candidate definition digest in `design.json` comes from retained
synthetic G4 proposal; it is a proposed hypothesis, not authority to run a real
strategy or proof of alpha. Baseline digest commits the proposed independent
null method only; it does not impersonate a generated baseline artifact.
One candidate budget, seed294, at most8192 bars, one chronological split with >=72h embargo,
all A/B/C variants when supportable, no winner selection or post-holdout tuning,
explicit UNKNOWN and zero trading are committed before any market result read.
**F0 remains PARTIAL** until exact permitted source, dates and split can be
bound. A local design hash is not an external prefreeze timestamp witness.

## Executable use

Python>=3.11. From repo root set PYTHONPATH to repo root and `src`:

```powershell
$env:PYTHONPATH = '.;src'
python -B -m tools.first_research_cycle.cycle --output cycle-new.json
python -B -m pytest tools/first_research_cycle -q --basetemp=.cycle-tests
```

```sh
PYTHONPATH=.:src python -B -m tools.first_research_cycle.cycle --output cycle-new.json
PYTHONPATH=.:src python -B -m pytest tools/first_research_cycle -q --basetemp=.cycle-tests
```

No source supplied produces deterministic blocked F0–F5 JSON, not an invented
actual-market cycle. CLI exit0 means the assessment executed; inspect its
status. Invalid/tampered inputs exit2, FAIL_MATERIAL_GATE, no output. Output
must be new; never overwrite a committed receipt. Two fresh processes must
yield byte-identical blocked reports. A retry after a committed output cannot
replace it; there is no partially persisted trial or mutable ACK here.

Optional `--source <explicit-fixed-export-dir> --source-sha256 <retained-digest>`
checks native MarketBar JSON and builds/verifies the existing native
`research-plan-1` contract. Directory holds `source.json`, `bars.json`,
`terms.txt`. Consumer dossier schema is `aql.first-cycle.source-export.v1`;
exact field shape is demonstrated in the clearly labeled **SIMULATED INTAKE
TEST**, not a market fixture (`test_cycle.py::simulated_input`). Terms byte
digest and owner-supplied use-rights reference are checked; neither establishes
legal/provider authority independently. No private path or raw prices are
exported in the report. Only an explicitly supplied export is opened; no DB,
observer, private drive discovery, market API or original archive is touched.

Source checks: separately retained source digest, immutable terms/bars digests,
bounded native grid/population, native checksum, final bars and finite OHLCV,
source/symbol/interval identity, close/ingest/as-of chronology, no missing or
duplicate slots, design anchor, frozen-before-evaluation assertion and split
embargo. March/April2024 overlap requires the explicit latest owner override,
checked by UTC range as well as cohort label. Current design records that
override and supersedes design hash
`152160b2c699c04293134baa42e77d5c8fcefbc4754341d70110cb2abac83a84`
before any market outcomes were read. It permits a distinct historical cycle
on existing March/April if a different2024 partition cannot be located;
old accepted suites and scientific promotion remain excluded.
Changed-source corrections must use a separately pinned population; this gate
never silently replaces or discards duplicates. Retrospective prefreeze-after-
historical-data is exposed, never converted into witnessed prospective OOS.

Even structurally valid exports remain unauthenticated and **BLOCKED** at
`ACTUAL_MARKET_RUNTIME_ADAPTER_NOT_YET_PROVED`. Current291 validates only
`source_class=SYNTHETIC_FIXTURE_ONLY`; current290 seals only mock-source
readiness. No one may relabel real bars as synthetic to force those APIs.
Native historical projection is reusable but has its own frozen 53-trial
contract; no fabricated attempts are added to satisfy it. Actual candidate,
population and evaluation adapter compatibility must be proved on the supplied
authorized source, not claimed ready from simulated intake tests.

## F0–F5 current gate matrix

| Phase | Actual status | Evidence / remaining requirement |
| --- | --- | --- |
| F0 | PARTIAL_DESIGN_FROZEN_SOURCE_BINDING_PENDING | exact reuse/ownership matrix; design digest; source/dates still absent |
| F1 | BLOCKED_INPUT | no authorized new actual-market bytes, identity/terms/usage bundle supplied |
| F2 | NOT_RUN | no cohort-bound discovery/attempt/trial ledger; no fabricated rejected candidates |
| F3 | NOT_RUN | no market run or gross/net/exit/risk comparison; accepted synthetic model reused only as reference |
| F4 | NOT_RUN | no actual paired baseline/SHADOW results; no scientific verdict or winner |
| F5 | BLOCKED | new intake tests and report replay do not establish actual end-to-end execution |

Actual populations stay null, not zero. Synthetic accepted populations do not
fill those nulls. Science is separately `REAL_PIT_OOS_BLOCKED`: genuine forward
cohort, rights/known-at/custody and externally witnessed prefreeze absent.
Historical2024 may support NON_PIT engineering when explicitly supplied and
authorized, never contemporaneous PIT or genuinely untouched prospective OOS.

Latest independently inspected owner-copy handoff #271/6773219946 contains
43 decisions /30 ENTRY /13 UNKNOWN and 12 mature+1 missing4h; only copied event
bytes/chain were inspected then, not source-parent continuity or24/72h maturity.
It is REUSED documentary evidence; no observer host probe was performed here.
Current owner says2024 data exists and directs local search, with March/April
fallback. Non-private filename search found March-named files in Downloads;
both are89-byte checksum text, not archives. Historical sample CSVs elsewhere
start in2026 and do not establish2024 source identity/use rights. No market
outcome was used. Private historical storage access was denied by automatic
approval review under the prior private-data prohibition; explicit permission
for those paths is pending. No bypass or original DB open was attempted.

## Focused test scope

Tests use actual native MarketBar and frozen-plan APIs, with SIMULATED input
only to test new intake safety. Positive structural acceptance **still returns
BLOCKED**, no fabricated evaluation. Negatives cover tamper, source/strategy
changes, duplicate/missing/provisional/future bars, plan-after-evaluation,
split leakage, accepted-period replay, rights terms mismatch, fake fill/ACK,
PIT/OOS/trading promotion, corruption and nonfinite JSON. Immutable inputs,
two-process deterministic output and retry-after-commit are checked.
Full producer crash/recovery, no-double-cost, mature-G2 and G4 lineage suites
are ALREADY_COVERED_SYNTHETIC at the Audit pins, not rerun here. Actual-market
execution/cost/recovery/ledger tests remain NOT_RUN until their inputs exist.
This is the exact boundary, not a waiver of Issue294 acceptance.
