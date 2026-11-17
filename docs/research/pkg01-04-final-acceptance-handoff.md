# Four-delivery acceptance: exact consumer seam blocked

ACKNOWLEDGED: the executing Integration session and all three lane executors
read owner addendum #271/6768882892. PKG04 independently acknowledged it in
#271/6772808260. Per-package implementation/CI is not final release acceptance.
No independent Audit verdict is claimed.

## Exact candidate and executed result

`tools/atlas_pkg03_final_acceptance.py` assembles one disposable candidate,
with four separately namespaced immutable deliveries and the existing exact
operational source overlay. No Git merge, source rewrite or shared lane edit.
It verifies disjoint changed-path ownership and source bytes after execution.

| Package | Base | Tested delivery |
|---|---|---|
| 01 / PR290 | Core275 `99c27ea2c1a4d41aaae361141301a8a9ea3b33c3` | `612d1444ff36ed08b63fd0a98bb8d4e71f88cd0d` |
| 02 / PR291 | Factory267 `04b63cc9b406b1f3eae2ac7de5d43ebda26dbfdf` | `ea4ffd5ce278d93588338122ab6ac1af8ec4da26` |
| 03 / PR293 | Integration271 `182331b90efdcc31cf04476200fe09b45e16997c` | `3b31fcc697deeab5b9489f20e026ebede1f4cf85` |
| 04 / PR292 | main `90af9794880cbeb00e7e974bfa906ff5e9666183` | `a79b26f300f0e4a35c37d231a9d8f3fc0d97d031` |

The final acceptance harness/CI/report is a subsequent Integration-only delta
on PR293; the pinned bounded-delivery revision above avoids a self-referential
commit hash. Existing native components remain pinned to the original #286,
#287, #288 and #289 heads, with #289 stacked on #286.

Composite source manifest SHA256:
`2849605d237c97851031d59efa32ed82fa178cbb4a6fe35c55f35c861e075f01`.
Local semantic acceptance receipt:
`e1a672037a33a8a82d50bceb230d21657dfdafbe69bbc949b3ccd83cfd2526b0`.
The full file/commit manifest is uploaded by focused Windows/Linux CI.

Actual commands, each from its pinned namespace:

```text
python -B -m tools.core_prospective_readiness_smoke --output <new>/core.json
python -B -m tools.atlas_factory_pkg02_execution_smoke --output-dir <new>/factory
python -B tools/atlas_pkg03_smoke.py --repo <git-object-store> --output <new>/operational
python -B -m tools.research_evidence_gateway.gateway --inputs <native-exports> --manifest-sha256 <retained-anchor> --output <new>/gateway-result.json
```

Core synthetic freeze/replay and Factory 72 modeled/UNKNOWN/nonfill variants
execute; actual G1 finalized journal/readiness -> Scanner causal census -> G2
read-only mature/pending report -> G3 durable process-death/recovery execute.
Recovered native G3 state is exported, not reconstructed. Factory report and
prospective receipt are supplied alongside actual native operational exports,
with independently retained canonical manifest digests. They are NOT relabeled
as one scientific cohort or as a Discoverer/Factory join.

PKG04 rejects the actual current G2 export with exit 2 and
`UNSUPPORTED_MATURE_EVIDENCE_CONTRACT`. Two fresh consumer processes produce
the identical rejection and no output file. Source/input byte hashes remain
unchanged. Mature/missing states are never stripped or downgraded to fit the
older pending-only consumer fixture. PKG04 also explicitly declares its native
Discoverer/Factory research join unavailable; adding a sealed Factory report
does not manufacture that join or a real fill.

**Final status: `BLOCKED_EXACT_PKG04_EVIDENCE_CONSUMER_SEAM`.**
`INTEGRATED_RESEARCH_ENGINEERING_READY` is NOT granted. CI success proves the
protocol executed and reproduced this exact blocker, not that release passed.

## Executed invariant matrix

| Invariant | Executed proof / scope |
|---|---|
| Core rights/version/time/freeze/receipt/source isolation/OOS refusal | PKG01 16 tests; deterministic CLI with 10 rejections; mocked provenance only |
| Gross/net, fee once, partial/nonfill/UNKNOWN, A/B/C chronology | PKG02 40 focused +27 adjacent tests, 58 subtests; 72 rows/18 cells; 9 CLI negative rejections |
| Actual finalized G1 -> actual Scanner -> G2 -> G3 | PKG03 7 tests and native CLI; 24 decisions (21 ENTRY, 3 UNKNOWN); no mock component replacement |
| Source/evaluator/strategy/receipt swaps, future/provisional, skipped/duplicate events | PKG03 10 CLI negatives +5 supplemental authority/pin rejections |
| Process death/restart/idempotency | Actual exit73 after commit before ACK, fresh replay, 3 retries, 2 assumed fills, zero skipped commands/duplicate fills |
| Forbidden ACK/PIT/trading promotion | Actual native contract negatives; no authority granted |
| Changed-path collision/source mutation | Composite manifest disjoint deltas and all extracted source bytes equal after execution; native durable DB/nonempty WAL unchanged |
| PKG02 model -> PKG04 boundary | Actual sealed report supplied; actual_fills null, orders 0, winner null; no unimplemented join or real-fill promotion claimed |
| Actual G2 mature/missing -> PKG04 | FAIL exact `UNSUPPORTED_MATURE_EVIDENCE_CONTRACT`, reproducible twice; no output |
| Discoverer proposal/checkpoint -> Factory actual trial/variant -> PKG04 join | BLOCKED: native persisted parent bundle/consumer adapter not available; no generated assertion or omitted denominator |
| Genuine rights/PIT/OOS/alpha, natural72h, G0/stage/merge/order authority | NOT_GRANTED; synthetic engineering cannot attest these |
| Producer ACK/fill tests in PKG01 | NOT_APPLICABLE: admission guard returns no order/fill/ACK |
| Original March/April and accepted G4 full suite | NOT_RUN, intentionally outside scope; existing acceptance preserved |

Only one corrective handoff: **PKG04 consumer owner via Integration #271**.
Extend the native consumer contract for actual mature/missing G2 parents and
consume a genuine persisted research proposal/attempt/trial/result bundle
from Discoverer/Factory owners. Preserve UNKNOWN, no-peek and modeled-only
boundaries. Do not invent the join or change producers. Rerun only this affected
consumer seam and its focused negative tests; no original or accepted G4 rerun.
Independent material-delta Audit #134 remains pending this handoff.

## Reproduce

```text
python -B tools/atlas_pkg03_final_acceptance.py --fetch --output <new-disposable-directory>
```

`--fetch` retrieves immutable repository Git source objects only. Omit it when
objects already exist. No market-data endpoint is used. The script never opens
the owner-host observer, private E:, original March/April bytes or external DB.
All four OS/Python CI variants upload actual command logs and receipts. Source
manifest is deterministic; platform-sensitive producer source hashes are
identified by their actual receipts rather than silently called identical.
