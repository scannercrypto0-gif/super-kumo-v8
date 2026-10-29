# Core159 bounded DEV binder

Engineering candidate only. `CANDIDATE_NOT_ADMITTED`; real integration remains
**BLOCKED**, not READY. No real source bytes were supplied/read here. No engine
or parser changes, empirical study, source download, Guardian operation, merge,
G0/OOS/PAPER/LIVE, or independent self-acceptance.

## Continuity and ancestry

Owner explicitly authorized issue159 execution in this Codex chat. At pre-edit
review, last completed Core owner Work was [156 result6471001876](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/156#issuecomment-6471001876),
after [153 result6470810545](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/153#issuecomment-6470810545).
Also reviewed [154 result6470946878](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/154#issuecomment-6470946878).
156's initial missing154 snapshot and159's queued156 snapshot are superseded.
157 started at6471083242 and supersedes unfinished150; no installed inspector
contract existed at implementation start. During implementation161 completed
at6471195346, becoming the latest completed owner Work. It preserves model/ACK/
independent-review gates and INT01–14 synthetic acceptance specs.157 subsequently
delivered Draft162 `9251d5f31ed06ecf87abf53ea604cf1d975923eb` (6471269620),
which is now inspected and tested below. No new Work command is issued by159.

Recent accessible CORE MANAGER messages and AUDIT chat metadata were read. Some
AUDIT responses were content-reference placeholders, not retrievable message
text; no review of their full contents or inaccessible chats is claimed.

Branch `core/159-dev-factory-binder` starts **exactly** at unmerged155
`752d7cd6d652860134918a35727853b5ba52f876`, whose parent/main is
`dbc191df72f4b4d1ebb7d490926dcad4325dac12`. Draft159 targets155's branch,
not main. Do not merge independently or assume155 accepted. No cherry-pick,
silent merge, or modification of155 paths. Factory143 is read in an isolated
detached checkout at `eacb5e50150c6e6c64c8a41b8eaa410aebd71532` (H01 U160-01 upgrade from `dee0f088`), never imported
as Git ancestry.143/144/155 were OPEN/unmerged when checked.144 remains
`3fc035b7ae70693e952976e2dcb2fe165a7e1826`. Their independent S/R is separate.

## Public boundary and deliberate stop

`aql.historical.dev_factory_binder.bind_dev` requires exact Core149 envelope,
raw bytes plus `ArtifactPin`, opaque issued receipt bytes plus separate pin,
`RecipientAck`, explicit consumer task/environment, separate `LagPolicy` and
`QuotePolicy`, cutoff and mode. No numerical policy defaults. Existing Core149
`import_bytes` alone parses and validates bars; a caller-constructed history is
never trusted. No duplicate CSV/ZIP parser is introduced.

`measure_readback` hashes the actual two byte objects. Caller labels identify
the recipient; they are **not authenticated identity or independent custody**.
`bind_dev` remeasures both objects and requires the ACK's task/environment and
both exact-version pins to agree. An owner153 ACK cannot be reused implicitly.
This generic measurement API does not assert actual private-file access here.

`REAL_SOURCE` unconditionally refuses with `FACTORY_INSPECTOR_PENDING` after
byte/identity/ACK/policy checks.157 is delivered but its independent acceptance/
signed interface and remaining real integration gates are still absent. Even
the actual157 static receipt cannot unlock it. A future separately reviewed
delta must accept the interface, issued receipt content contract, recipient
evidence and independent exact-head S/R. Current receipt
bytes are committed **opaquely**; their publisher semantics/signature are not
validated. Neither policy reference strings nor a self-generated ACK prove
approval/access. These limitations cannot lead to real admission.

Optional `inspector_decision={code_sha,payload}` binds the actual157 canonical
static SourceReview bytes at exact9251d5f. Its Core source_id, envelope digest,
Core import receipt digest, normalized7 digest, count/range and all UNKNOWN/false
claims must match precisely. Extra fields, altered consumer/execution claims,
wrong code version and noncanonical bytes refuse. The receipt SHA/size and full
static receipt are included in the mapping commitment. This checks consistency,
not authenticity or Council acceptance. Missing inspector is allowed **only**
in synthetic mapping-only fixtures; all real admission remains closed.

`SYNTHETIC_CONTRACT_TEST` accepts only origin SYNTHETIC plus checksum provenance
SYNTHETIC_FIXTURE. Its package is an immutable byte snapshot with detached
accessor copies. All fixture policy/approval references are clearly fictional;
they approve no owner numerical lag, quote model or study. No actual historical
envelope can enter merely by selecting this mode. It returns candidate rows and
source dictionaries compatible with the pinned148 validator, **not an execution
permission**. An unchanged low-level Factory API is not an authorization system;
the caller must preserve candidate status/sidecar. This module never calls it.

## Exact mapping

| Core149 validated seven-field bar | Factory148 dictionary | Rule |
|---|---|---|
| bar_open (tuple0 / Binance col1) | open_ms | integer UTC ms, unchanged |
| bar_close (tuple1 / Binance col7) | close_ms | inclusive end, unchanged |
| open (tuple2 / col2) | open | finite positive float |
| high (tuple3 / col3) | high | unchanged |
| low (tuple4 / col4) | low | unchanged |
| close (tuple5 / col5) | close | unchanged |
| volume (tuple6 / col6) | volume | nonnegative base volume, not executable liquidity |
| separate approved retrospective lag | available_ms | close_ms + 1 + lag_ms |
| separate hypothetical quote policy | modeled_quote | explicit bool; false preserves unavailable quote behavior |

No discarded Binance columns become bid/ask, liquidity, first-known timing or
correction history. Core interval/range/grid preserved. The actual Factory148
validator requires prices >=1e-12; Core accepts >0. Binder therefore refuses
the narrower incompatible price domain instead of silently emitting rejected
Factory inputs. Non-1m inputs require the matching explicitly chosen Factory
Config.interval_ms later; binder chooses no engine config/default study.

Lag schema `retrospective-close-plus-lag-1` supports an explicitly approved
constant integer lag >=0 only. Quote schema `hypothetical-ohlcv-quote-1` needs
its own version, approval flag and owner/Council references. Unsupported schemas,
bool-as-int, negative/nonfinite/overflow lag, absent approval and missing quote
choice fail closed. References are commitments to purported decisions, not
verification of those decisions. No per-bar arbitrary timing/model is guessed.

Full requested range must be closed **and modeled available** at cutoff. Future
bars cause refusal, never silent prefix truncation. Available==cutoff is allowed;
available>cutoff fails. Integer arithmetic stays <=2^53-1. Existing Factory148
prefix-max signal availability and ceil((ready+latency)/interval) scheduling
remain unchanged: readiness exactly on an open can execute there with latency0;
positive latency moves to the next eligible grid open. This is modeled causality,
not proof of historical issuer availability or correction-free features.

## Digest domains and composite identity

| Domain | Exact committed bytes | Version/size/reference |
|---|---|---|
| raw archive SHA256 | supplied original bytes | raw ArtifactPin, linked to Core envelope |
| issued receipt SHA256 | supplied issued bytes, no reserialization | separate receipt ArtifactPin |
| normalized seven-field SHA256 | Core seven-element list rows, compact sorted JSON, ASCII escapes, UTF8, allow_nan=False | normalization, measured JSON size, Core envelope source_id |
| Factory rows_sha256 | full dict-list including available_ms + modeled_quote, same canonical JSON settings | factory148-dictionary-json-ascii-1, measured JSON size, pinned Factory SHA |

Hashes are recomputed in each domain; no substitution/equality inference.
Actual real-source Work152 normalized equality is UNVERIFIED. Raw/receipt pins
include explicit version and opaque reference, neither automatically fetched.
The entire canonical mapping body (envelope, rows, all pins, ACK labels, both
policies, cutoff, code SHAs and false claims) has a separate mapping_sha256.
Factory source.version=`core-factory-dev-map-1:<mapping_sha256>` is a mapping
version, **not** publisher source_version. source.reference points at exact raw
pin, source.archive_sha256 remains raw SHA and source.rows_sha256 hashes full
rows. correction_evidence=PINNED_VERSION_ONLY means pinned payload only.

Important correction to156 prose: actual Factory148 `digest` at blob
`3a8560f97473f5ec8e5133e575fab94e4297f8da` uses default **ensure_ascii=True**,
not False. Non-ASCII reference regression checks actual code compatibility.
Core149 source_id and legacy manifest digests remain distinct/unchanged.

`verify_candidate` detects content/source commitment tampering and canonical
serialization changes. It does not authenticate an issuer, verify approvals,
or turn recomputable hashes into signatures/admission authority.

source_version, correction_status, issuer_first_available_at, availability,
bounded_UTC and independent_custody remain UNKNOWN. Factory correction flag is
PINNED_VERSION_ONLY, never PINNED_LINEAGE. All real-source/PIT/actual-quote/
actual-fill/empirical/execution eligibility claims are false.

## Focused verification

Only fabricated CSV/receipt bytes, approvals and candles. Tests cover exact
field mapping, four digest domains/size, Unicode serializer, immutable replay,
raw/receipt tamper and missingness, recipient/environment/version mismatch,
unsupported code/schema/policy, invalid grid/OHLCV, incompatible price floor,
cutoff equality/+1/overflow, quote false, stable policy recommitment, candidate
tamper, future/PIT refusal and unchanged legacy CustodyAccessor/bridge gates.

The optional `FACTORY148_ROOT` checkout is pinned by HEAD and actual blob ID;
tests import it under a separate package name. They run only synthetic validator,
signal-prefix and handcrafted scheduling/receipt fixtures, not market data or
strategy performance. No engine file is copied/changed. Without this explicit
checkout those eight compatibility cases skip. `FACTORY157_ROOT` supplies a
separate exact9251d5f checkout for one additional actual-inspector join/conflict
test. Both checkouts must have clean research_wp_r0 sources. Focused CI supplies
both on Windows and Ubuntu. Existing green Factory CI is reused, never manually rerun.

Reproduce from repository root with pytest/pytest-timeout installed:

```powershell
$env:FACTORY148_ROOT = (Resolve-Path ../core159_factory_compat).Path
$env:FACTORY157_ROOT = (Resolve-Path ../core159_inspector_compat).Path
python -B -m pytest tests/test_core_dev_factory_binder.py tests/test_core_dev_source.py tests/test_sf_data_01.py tests/test_sf_research_int_01.py -q --tb=short
```

Local pre-inspector Windows Python3.12.10 result: **279 passed / 0 failed / 0 skipped**,
12.73 seconds; JUnit has279 tests/0errors/0failures/0skips. Includes64 new binder
cases (eight exact-Factory compatibility cases) and215 unchanged Core149/library/
bridge cases. First candidate run:273pass/3fail, due to a test reading scheduled_ms
from the input signal instead of the per-path opportunities. Second candidate:
278pass/1fail, stale fixture accidentally beyond final modeled open. Both test
expectations/fixtures corrected; engine and binder unchanged. Initial and second
JUnit retained locally outside the checkout. No failures hidden or engine behavior
changed to match tests. Final inspector-inclusive Windows Python3.12.10 run:
**280 PASS /0FAIL /0SKIP,9.39s** (65 new binder cases including nine actual pinned
Factory/inspector compatibility cases,215 unchanged Core/library/bridge cases).
Exact SHA is in the159 delivery/PR.
New focused workflow checks exact PR head and the pinned external
Factory source; broad existing workflows are not manually dispatched.

## Remaining dependencies / independent review request

BLOCKS_DEV_NOW: actual private ZIP+issued receipt in each recipient environment
with measured task-specific two-file ACK; independent acceptance of delivered157
inspector contract and signed interface;
explicit owner numerical lag/sensitivity policy and separate hypothetical quote
model; independent Council S/R on relevant exact Core/Factory/binder heads and
the actual integration delta. Owner153 readback alone solves none of these.

New160 source-only finding U160-01 (134/6471209219) concerns unqualified whole-
policy metrics after UNKNOWN_ENTRY_QUOTE. No arithmetic/conservation defect is
asserted by this binder, and no148-owned engine/reporting patch is included.
Quote-false compatibility tests preserve null opportunity scores/denominators;
they do not certify flat cash trajectory as complete policy evidence. Council/
Factory must resolve the conditional reporting interpretation before study use.
Concurrent150 also delivered distinct Draft163 b8e4c3e9fece8f66f0614041637640c9849e02b3
per134/6471390094, despite the earlier consolidation plan. Not imported or used;
no claim that150/157 overlap has independently been adjudicated. This binder's
optional inspector port is pinned specifically to157/162, not either by number.

BLOCKS_PIT_LATER: authenticated per-vintage original/corrected availability and
ancestry, bounded independent UTC and immutable external custody remain absent.
DEFERRED: Guardian151 operations/continuous HOLD, strategy study, broad E2E,
OOS/PAPER/LIVE. Do not change these scopes to finish this engineering ticket.

S requested: ancestry/isolation, importer reuse, digest domains, explicit policy
and receiver evidence, real-mode unconditional refusal, synthetic compatibility
and unchanged confirmed gates. R requested: hypothetical lag/quote meaning,
UNKNOWN provenance, no first-known/observed fill/PIT/empirical claims; a
synthetic scheduling fixture is not an economic result. No self-issued approval.
