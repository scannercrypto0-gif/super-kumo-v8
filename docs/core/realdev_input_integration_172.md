# AQL-CORE-REALDEV-001 — integration/ingestion inspection only

Authority: owner Issue172, after AIARC098 conditional design review and actual
local recipient ACK171/6490554462. A new branch starts from canonical170 exact
`0ee2254568479ee5cbcfcca3846716a84404db3c`, stacked164→155; no old PR modified.
H01, importer, static inspectors, Factory engine and Guardian stay unchanged.

## What the new seam permits

`inspect_local_pair(raw_path,receipt_path,*,checkout,capability=None,request="REAL_SOURCE")`
defaults DENY. Only explicit DEV_INTEGRATION_ONLY for AQL-CORE-REALDEV-001 and
the exact owner172 authorization reference can return a provenance report.
No factory dictionary rows, features, signals, quotes, orders, fills, cash, PnL,
study callable or operational activation is returned or invoked. Existing binder
REAL_SOURCE denial is untouched. A quality pass cannot reach an execution path.

Required IntegrationCapability explicitly commits experiment/scope/owner ref,
RuntimePin(host/account/Python/version/checkout/actual HEAD), fixed original
archive+receipt digests, map2/current143/profile, full chronological source prefix,
closed-bar decision cutoff and minimum input warmup count. No approved=True,
execution-policy numbers, generic scope wildcard or implicit ID. Caller must
select this exact request; every other scope refuses before file reading.

**Authorization trust boundary:** permission comes from the actual human owner
instruction172, reviewed by the authorized local operator. The object constrains
that instruction; it is NOT a cryptographic owner-signature/issuer authentication
service. The module cannot establish arbitrary callers' real identity or treat a
hash/ref as a signature. In-process objects and owner GitHub references are
caller-supplied commitments; hostile Python/OS administrators are not isolated.
This implementation is pending independent audit and grants no study permission.
No standalone JSON receipt or caller approved flag can enable execution here.

## Fresh input and code checks

Observe actual loaded module origin, exact checkout/root, clean Git state and
HEAD; require canonical170 ancestry. Reject stale RuntimePin/HEAD. At invocation
freshly open BOTH originals read-only, bounded by exact expected sizes, check
SHA256 and stable size/mtime during reads. Do not use the old171 ACK as a cached
substitute. The current code/clean state is checked again after validation.

Source:68923bytes/SHA4ec2915e610ab4e9a4d5e86a5ada1c15bbf6b5db343cdb385681d6ac97166a4e.
Original issued receipt:4203bytes/SHAffce2bbe7890414d84360be80a0ac478795ae8d1a28085f8bb34075faca83386.
Receipt schema/source/payload/archive identity/size/hash and explicit retained
raw artifact version0 are verified; recorded normalization count/interval/day
bounds and UNKNOWN correction/issuer/UTC/custody flags must agree. Receipt's own
version0 is separately pinned by Work152 record, not invented from its filename
or hash and not an issuer historical-original vintage assertion.

Actual155 import_bytes revalidates exact ZIP bytes, expected single member,
complete positional UTC-ms day grid, order/duplicates, close boundaries, finite
and logical OHLCV. Existing range_query enforces full prefix at closed-bar cutoff.
Normalized7 digest must equal the original receipt's recorded normalization.
No second ZIP parser, sorting, deduplication, filling or source overwrite.

Warmup field checks **input prefix count only** (minimum22 is the existing
EMA8/21 interface's structural floor), not a frozen study warmup/seed/convergence
decision. No indicator or feature is computed. Closed-bar lower-bound chronology
does not prove issuer arrival/as-of/correction timing or independently bounded UTC.
Actual study prefix/seed/lag/cutoff decisions remain separately approval-gated.

## Evidence and replay

Immutable IntegrationReport contains canonical metadata only: experiment,
actual HEAD/runtime, request commitment, measured file paths/sizes/hashes,
source/receipt identity, validation outcomes, normalized7/manifest commitments,
exact interface pins and explicit limitations. `report.digest` is SHA256 of
canonical report bytes; no clock/PID enters that deterministic domain.
External observation logs can record process/time separately without presenting
the local clock as trusted UTC. `replay_local_report(...,expected_digest=...,**invocation)`
freshly remeasures the files and recomputes equal bytes, not trust an ACK JSON.
Digest integrity is not independent custody or owner/issuer authentication.

All flags: DEV_ONLY=true, NOT_PIT=true, NOT_EMPIRICALLY_VALIDATED=true,
actual_fill=false, timing/PIT/empirical/factory-execution eligibility false.
Strategy execution is BLOCKED_NOT_AUTHORIZED. Source lag, execution delay,
quote convention, spread/slippage/fees/sizing/limit-expiry/TP-SL/intrabar priority
and sensitivity are each NOT_CONFIGURED. No B0 or LIMIT consultation defaults.
No modeling occurred, so no hypothetical-execution output is emitted; any later
approved modeling metadata must be explicitly HYPOTHETICAL_EXECUTION and needs
a different reviewed contract. UNKNOWN_ENTRY_QUOTE and whole-policy-null/unknown
denominators are unchanged, not evaluated/recomputed by this source inspector.

## Reproducibility and limits

Public synthetic tests:
`python -B -m pytest tests/test_realdev_integration_172.py -q --tb=short`
New48cases only, WindowsPython3.12.10:48PASS/0FAIL/0SKIP0.59s. Initial collection
error used pytest-reserved request parameter; renamed test parameter, then all
passed. Initial error retained outside repository, no production issue hidden.
Tests cover opt-in/default denial, ID/scope/profile/code/runtime/source pins,
missing warmup/prefix/cutoff, original bytes integrity, receipt chronology/version
and provenance rejection, missing policy not creating execution, original binder
denial retained, and report commitment refusal. Synthetic receipt fixtures are
never labeled as original Work152 or used as real ACKs.

Native targeted CI contains only these new synthetic tests. No private ZIP,
receipt, runtime capability or real paths are uploaded to CI. Prior17017+17,
16966+66 and Work171 evidence reused, not rerun. Actual positive original-pair
integration and deterministic fresh replay are local-only on final clean HEAD;
result/evidence path published separately on172, not assumed from unit tests.

The intended local input paths remain owner-provided Downloads/recipient171.
Use repo root+src on process PYTHONPATH, CPython3.12.10 in atlas-review-126-venv.
Operator supplies capability with independently selected current HEAD/runtime and
exact request; no endpoint, global config, existing guard, private file or frozen
manifest changes. New runtime checkout identity must be explicitly selected again.

Outcome if all scoped checks pass:
DEV_INTEGRATION_CONTRACT_IMPLEMENTED_PENDING_AUDIT.
This is an engineering handoff, not full REAL_SOURCE admission/study/PIT approval.
Failure→BLOCKED with concrete reason; do not use policy defaults to work around it.
Independent Council S/R must assess exact new source/authority boundaries and
local evidence. Owner separately freezes model/study choices and authorizes any
future integration/execution delta. No PR merge/G0/OOS/PAPER/LIVE/Guardian.
