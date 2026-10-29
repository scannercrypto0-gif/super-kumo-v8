# CORE-DEV-02: bounded Core → Factory research DATA ONLY

Owner174 explicitly authorizes this new seam, no real strategy/backtest/order/
fill/PnL/model choices. Baseline17322d03f4d3434fbce149c4d66349b33149789613a,
stacked1700ee2254→164→155; new branch/Draft targets173, no prior PR edit/merge.
Start rechecked173,170 and143eacb5e50 OPEN/DRAFT/unmerged at expected pins.
Read AIARC099/6491281268: accepted173 input inspection, NOT study admission or
permission to treat its metadata report as a capability. No unseen chats claimed.

## Architecture / why one small Factory adapter is needed

Existing HistoricalLibrary supports retrospective values; CustodyAccessor and
historical_evaluation_bridge.prepare_inputs require recorded confirmed timing
and strategy definition/evaluation bindings. Factory143's runnable replay needs
available_ms/modeled_quote/execution assumptions. Neither is an honest data-only
consumer for unknown historical availability. No existing gate is weakened.

New files only:
- Core `aql.historical.research_handoff`: fresh handoff orchestration.
- Factory `research_wp_r0.realdev_research_data`: new narrowly identified
  `factory-realdev-research-data-1` consumer, data-only validation/receipt.
- One changed-seam synthetic test file, this document and isolated focused CI.
No existing parser, binder, strategy/feature/engine/Guardian file is changed.

Core public API:
```
handoff_local_pair(raw_path,receipt_path,*,checkout,capability=None,request=None)
replay_handoff(report,*,expected_digest,**same_invocation)
```
Only request DEV_RESEARCH_DATA_ONLY with explicit ResearchCapability: exact
experiment AQL-CORE-REALDEV-001, owner174 scope, consumer ID, runtime/current HEAD,
separate original173 IntegrationCapability and chronological prefix/cutoff/input
warmup. Same-machine new checkout identity must be explicitly selected; no old
171 ACK is impersonated. Actual loaded-code origin/clean HEAD verified through
existing observe_runtime, plus173 ancestry and an end-of-handoff runtime check.

Every invocation runs actual173 inspect_local_pair under its original explicit
DEV_INTEGRATION_ONLY permission. Its metadata cannot substitute for byte access.
Then the exact snapshot supplying rows is freshly read again against fixed
original raw+issued-receipt SHA/size, receipt binding rechecked and actual155
import_bytes reused. A replacement between inspection and row read cannot bypass
the exact pins. No second CSV/ZIP parser or cached-report admission endpoint.

Full-source quality inspection may read/validate the entire pinned archive, but
**only the requested closed-bar prefix** is returned to Factory. The data-only
prefix must start at source start, be contiguous, end within the source extent,
and close no later than the explicit research cutoff. Full-source hash is a
version commitment, not exported future prices or future feature values. No
feature computation, signal or actual historical as-of availability is implied.
Structural input floor22 is NOT scientific study warmup/EMA seed approval.

Factory public API:
```
accept_prefix(normalized7,*,metadata,expected,permit=None,request=None)
ResearchData.rows                 # immutable tuple of seven-field tuples
ResearchData.spec                 # detached JSON value
ResearchData.request(scope=None)  # independently denies every other scope
```
ResearchPermit identifies exact experiment/owner174/consumer/code/runtime digest.
Factory independently checks scope **before inspecting data**, versions/profile,
symbol BTCUSDT,1m/UTC integer grid, prefix/count/cutoff/warmup, separately retained
hash commitments and legacy finite/logical OHLCV validation. Input lists/dicts
are snapshotted before validation and serialization. No sorting/dedup/fill.

Request EXECUTE/STRATEGY/ORDER/FILL/PNL/PIT/OOS/PAPER/LIVE/GUARDIAN/REAL_SOURCE or
missing permission is refused independently by Core AND Factory; the returned
data object also refuses these requests. No engine import, callable or automatic
downstream invocation exists. Rows are normalized7 tuples, **not** execution
dictionaries with available_ms/modeled_quote. Manual copying outside this API
cannot be technically prevented by any data export and is NOT authorized here;
any future runnable engine still needs its own independently reviewed gate.

## Receipt / commitment domains and trust boundary

core-factory-research-prefix-1 metadata binds exact new actual code SHA/runtime,
base173 pin, contextual Factory143 SHA, mapping2/profile, source/receipt SHA+size,
retained archive version0, fresh173 report SHA, full normalized7 SHA and separate
prefix SHA, explicit source/issued-receipt IDs, consumer/experiment, UTC
source/prefix/cutoff/input-count parameters.
Factory143 is the compatibility-context pin, not a claim its runnable engine was
called. New consumer code is part of the new actual HEAD, explicitly in metadata.

Factory result factory-research-data-only-1 includes immutable normalized7 and
metadata, own deterministic receipt hash, always DEV_ONLY/NOT_PIT/
NOT_EMPIRICALLY_VALIDATED=true, actual_fill/timing/PIT/empirical/execution
eligibility=false. Issuer availability/corrections/custody/UTC UNKNOWN. No
execution assumptions selected: lag/delay/quote/spread/slippage/fees/sizing/LIMIT/
TP-SL/intrabar priority/sensitivity NOT_CONFIGURED. No hypothetical or actual
execution was performed. Historical unknowns and existing UNKNOWN_ENTRY_QUOTE/
whole-policy-null semantics stay unchanged, not evaluated by this API.

Owner instruction and capability are cooperative operator trust boundaries from
AIARC099, not cryptographic signatures, hostile-Python isolation or immutable
custody. Factory validates an injected snapshot against Core-retained commitments;
it does not independently fetch/hash ZIPs or authenticate publishers. Therefore
only the public fresh Core handoff, not a forged report or directly constructed
data class, can support this task's original-pair evidence. A report/hash alone
is not an execution capability. Normalized/raw/prefix/metadata/receipt digests
are distinct domains; replay freshly recomputes the handoff and requires byte
equality against separately retained result digest.

## Tests / private local evidence

`python -B -m pytest tests/test_research_handoff_174.py -q --tb=short`
New synthetic suite only: first47PASS0.86s, then caller-snapshot isolation
added during source review and47PASS/0FAIL/0SKIP0.97s WindowsPython3.12.10.
Final source explicitly retains source/issued-receipt IDs, with two additional
identity refusal cases (49 total); final execution evidence is reported on174.
No red failures hidden. Native Ubuntu/Windows focused CI contains synthetic
fixtures only; no private source files or rows are uploaded. Existing48/17/66
tests are reused, not rerun. New tests cover two independent scope denials,
immutable deterministic bounded prefix, invalid source/schema/profile/runtime/
HEAD/pins, cutoff/warmup, missing/tampered files at the NEW read boundary even if
prior metadata check is forged, malformed/gap/order/future-tail/invalid OHLCV and
replay commitments. Adversarial boundary unit tests explicitly stub prior
inspection/runtime; they are not original-byte or clean-HEAD verification claims.

Actual local positive on final clean HEAD is separately recorded on174: original
files read-only from owner Downloads/recipient171, fresh source check/import,
bounded60-bar prefix, deterministic repeat/replay and independent execution
denials. No experiment, indicator or strategy run. Private handoff payload
contains normalized rows: store only outside Git, publish its local path/hash
and observation summary, NEVER upload its contents/raw ZIP/issued receipt.

Outcome only if these scoped checks pass:
RESEARCH_DATA_HANDOFF_IMPLEMENTED_PENDING_AUDIT. This is not source PIT,
empirical validation, model-policy freeze, full REAL_SOURCE entitlement or study
approval. Independent exact-head AIARC S/R on NEW seam still required. All prior
drafts remain unmerged; no Work task, G0/OOS/PAPER/LIVE/Guardian/merge authorized.
