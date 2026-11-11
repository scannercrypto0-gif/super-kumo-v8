# Core follow-up C3–C6 (#273)

The original C1–C3 evidence and accepted tests in #308 are retained. The new
Core adapter uses the existing source view and caller-pinned revision chains.
It provides a fixture snapshot and context response for the exact #276 reader,
and a separate Core evidence envelope preserving original publication, receipt,
commit and known-at clocks, rights/retention, revision parents and a typed
feature definition. The fixture adapter's local availability clock is explicitly
synthetic. Production evidence never enters the existing TEST_ONLY reader.

## Core and consumer contract

An inventory pins mode, venue/market, effective-dated members and per-subject
feature series. Each series carries its own source market, normalized vintages,
per-version pins, rights receipts, retention ceiling and integer unit/scale.
A cross-asset input keeps its actual source identity. Read from authorized Core
custody only and verify the caller's independently retained inventory digest.
An event context request supplies a pinned outcome identity and an exclusive
pre-onset cutoff. Only versions whose clocks and effective window fit the request
are visible, and correction history preserves earlier versions and their parent
hashes. Missing source, rights, revision, stale membership or unknown evidence
never becomes zero. New membership epochs have distinct inventory identities.

To adopt production, Discoverer owns a new consumer of
`aql.core.discoverer-context-evidence.v1` and a corresponding authorized outcome
schema. It must validate the query/subject and exact inventory pins, use the
original witnessed known-at and commit clocks, preserve grades and unavailable
reasons, and keep TEST_ONLY and prospective/retrospective populations separate.
The fixture reader remains unchanged.

Scanner's read-only monitor projection admits a complete, final-only candle
grid or returns UNKNOWN without a partial indicator window. Tests execute
the exact #277 diagnostic function body with the existing native indicator
kernel. Full Scanner startup requires its unmerged policy dependencies.
Factory receives `aql.core.factory-precursor-input.v1` with the GE predicate,
direction, source and candidate pins, exclusive cutoff and admitted typed
vintages. This is input evidence, and the exact #267 registry rejects it as an
experiment. The existing Lab requires a Factory ledger and rejects Core's
monitor packet. Factory must own executable feature translation, trial freeze,
matched baseline, full opportunity/attempt accounting, execution costs,
scientific evaluation and immutable PASS/FAIL/UNKNOWN feedback. Integration owns
deployment and combined release-tree testing. Core creates no trial or signal.

## Poll and source admission

The fixture SQLite fence shares one local transactional reservation authority.
Reserve at most half the configured weight in a rolling window, allow one
outstanding request, and retain attempts and ACKs across restart. A lost ACK
blocks the lane until explicit reconciliation after timeout and does not refund
weight. Retries need a distinct request identity. 429 with missing, non-finite
or negative Retry-After falls back to at least 60s. 418 latches the ban. 5xx and
connection failures use capped exponential cooldown and deterministic jitter.
No unbounded queue or automatic catch-up traffic. The caller provides a trusted
monotonic dispatch clock and a reader that honors the requested timeout. Local
wall/CPU checks and serialized payload size are measured; hard process limits
and multi-host shared-egress proof remain Operations/Integration work. The
existing #305 provider-specific offline limits and #286 observer are unchanged.

The provider-neutral vintage registry checks exact terms/rights pins, source,
clock, retention and finality before a record is available. It does not invent
publisher evidence or start collection. The machine-readable
[coverage decisions](source-coverage-v1.json) retain the accepted historical
BTC scope and explicit owner/source choices. No new licensed news, macro, gold,
bond, PAXG or sector bytes were supplied, so positive ingestion is BLOCKED_SOURCE.

## Evidence and reproduction

The new test suite stages pinned Git source only: #276 `9b60eb00`, #277
`ccf57ad3` and #267 `04b63cc9`. No other owner's branch is edited. It checks the
actual Discoverer watch and quiet search, up/down precursors, late news,
revision timing, custody and rights denial, a 12-slot bounded Core↔Discoverer
poll, two contenders sharing one quota, and a hard subprocess lost ACK.
The prior Core and Discoverer suites are reused at their previous evidence
scope. Use Python 3.13, pytest 9.0.2 and PYTHONPATH containing src and checkout
root, then run `python -B -m pytest tests/test_core_discoverer_followup.py -q`.
