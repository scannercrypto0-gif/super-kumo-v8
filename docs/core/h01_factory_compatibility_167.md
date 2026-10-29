# H01: versioned Factory143 compatibility, synthetic-only

Owner #167, 2026-10-29. Separate branch stacked on exact Draft164
`a5657c6ff8cdf9a0a76946e3ba73c59566d2e639`, itself stacked on unmerged155
`752d7cd6d652860134918a35727853b5ba52f876`. No merge/cherry-pick, Factory-owned
edit, parser change, Guardian operation or real-source admission.

## Continuity / no overlap

Read actual deliveries159/6471660781, latest owner Work161 after156, Work160,
Factory harness77/6488960044 and Audit134/6488970077, AIARC093/6488713936 and
AIARC094/6488975262. Open PR/issue/ref inventory and167 comments checked before
edits: no equivalent active/delivered H01 patch found in accessible records.
Work168 is separate read-only reporting inventory; no duplicate harness/report
project or LIMIT-DEC-01 implementation. No unseen-chat coverage claimed.

| Dependency | Exact pin / role |
|---|---|
| Core155 |752d7cd6d652860134918a35727853b5ba52f876, unchanged importer inherited by164|
| Core164 parent |a5657c6ff8cdf9a0a76946e3ba73c59566d2e639, previous binder blob3a4a381bfbfab202b057308593e6bf363c5f4b55|
| Factory143 old |dee0f088d70122d143118df2e0a0549a564f2380, engine blobbbeae9d7f16f4d2b0738072ec35ea4dd9345639b; unsupported by new mapping|
| Factory143 current |eacb5e50150c6e6c64c8a41b8eaa410aebd71532, engine blob3a8560f97473f5ec8e5133e575fab94e4297f8da|
| Factory162 |9251d5f31ed06ecf87abf53ea604cf1d975923eb, static receipt source blob2315f8cfb51533386ce383d84bca5eeedd65ee52|
| Factory163 |b8e4c3e9fece8f66f0614041637640c9849e02b3, injected-byte quality; not a replacement for162 inspector|

All remain separate unmerged drafts, not accepted main functionality.

## Source compatibility, not just a constant

The old→current Factory engine diff adds a comment and calls
`unknown(t,status)` in UNKNOWN_ENTRY_QUOTE. `_validate`, Config, digest,
source/row schema, `_signals`, replay and verify_receipt API are unchanged.
Behavior changes intentionally: unknown entry now latches factual policy
uncertainty, blocks later candidates, and masks whole-policy totals while
retaining labeled known conditional cash/known_realized_pnl. AIARC093 is scoped
source acceptance, not full execution/PIT/whole-PR certification; AIARC094's
downstream export inventory remains outside this patch.

Mapping schema is now **core-factory-dev-map-2**, exact Factory pin current
eacb5e50, explicit profile **factory148-u160-whole-policy-null-1** included in the
mapping commitment. Row normalization, raw/issued-receipt/normalized7/dictionary
hash domains, model parameters and approval references are unchanged. The new
schema/profile intentionally changes mapping/source version hashes, not raw data
hashes or issuer vintage. No automatic migration of old candidates.

Exact-pin guard still rejects old dee0f088 and arbitrary/extended SHAs.
verify_candidate additionally refuses unsupported schema/core/factory/profile
even when a caller correctly recomputes its unsigned mapping hash. It remains
an integrity check, not independent authentication or hostile-admin protection.
REAL_SOURCE unconditionally refused; no model lag/quote/cost defaults added.

## Changed coverage only / actual results

Reuse existing23PASS harness report, original164 65-case/280 combined local
evidence and CI40705736985; no rerun of those unchanged suites. Reuse existing
test fixture helpers and isolated source loaders, updating only the engine blob
assertion for the newly supported target. New targeted file17 cases:
- current target acceptance and actual engine validation/dictionary digest;
- stale/arbitrary SHA rejection and rehashed old schema/target/profile refusal;
- source/issued bytes and static receipt tamper rejection;
- bound current UNKNOWN_ENTRY_QUOTE policy-null vs known conditional cash across
  all3paths, blocked next opportunity and denominator2;
- bound current simultaneous target/stop separation and receipt-tamper refusal;
- changed seam cutoff/lag/prefix availability consistency;
- one complete **synthetic five-node traversal**: inherited155 import →162 static
  receipt plus163 independent raw quality inspection → new binder → actual143
  replay and deterministic receipt validation.163 receipt is not silently used
  as162 and is not promoted into a binder admission token.

Fixture uses30 handcrafted constant OHLCV bars at1704067200000,1m, O10/H12/L9/C11/V2,
SYNTHETIC origin, fixture-only lag17ms/quoteFalse and explicit fixture policy refs;
not a real-study approval or private archive. Real replay path uses its actual
EMA API; the separate short execution-contract tests use existing fixture API to
exercise unknown entries and scenario divergence. No real-source strategy/PnL.
This demonstrates local synthetic compatibility, not a deployed five-node E2E,
all-case integration certification, accepted study or authenticated policy/ACK.

First local invocation: collection ERROR, shared test-helper import path absent;
no tests ran. Added this test directory to sys.path; unchanged implementation then
**17PASS/0FAIL/0SKIP,3.62s**, Windows/Python3.12.10. Initial error JUnit retained
outside repository, no red evidence suppressed. No broad test campaign.

Reproduce with clean exact dependency checkouts:
```
FACTORY148_ROOT=<clean143 at eacb5e50>
FACTORY157_ROOT=<clean162 at9251d5f>
FACTORY150_ROOT=<clean163 at b8e4c3e>
python -B -m pytest tests/test_core_factory_h01.py -q --tb=short
```
Native workflow pins those three checkouts, runs only the new17-case delta and
publishes JUnit. Existing old suites remain available unchanged; no skips/xfails,
threshold relaxation, monkeypatch of guards or substitution of old engine.

## Next bounded Work handoff / gates

H01 contract delta ready for independent Council S/R on new exact SHA; no blanket
acceptance from source pin update or prior green tests. Work168 may reuse these
results and continue its own downstream nullable-metric inventory; do not rerun
the old23 tests or create another harness. Independent reviewer should challenge
the explicit profile, fail-closed old-version behavior and current unknown-entry
aggregate/conditional distinction, then owner decides next acceptance.

BLOCKS_REAL_DEV: actual recipient two-file ZIP+issued-receipt measured ACK,
explicit owner lag/quote/cost model decisions, accepted interface/relevant exact
S/R and separate study/integration authority. Owner Library Work153 readback is
not this recipient's ACK. No private data accessed, fetched or claimed here.
BLOCKS_PIT_LATER: issuer per-version first-known/correction chronology, bounded
UTC and independent immutable custody. Guardian165 remains separate HOLD.
LIMIT consultation166, empirical study, OOS/PAPER/LIVE/G0 and merges remain closed.
