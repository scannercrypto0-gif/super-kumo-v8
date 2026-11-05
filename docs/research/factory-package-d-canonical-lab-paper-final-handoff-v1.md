# ATLAS Factory Package D — canonical AAA Lab→isolated Paper handoff

Status: **DRAFT / TEST_ONLY engineering software gate**. Not a G0 approval,
merge authorization, historical PIT certification or trading/Paper activation.

## Frozen parent heads (read-only integration dependencies)

- Factory C base PR #260: `94107e2bbe9e06088caeaf87768796d6b77bee42`
- Core D Draft PR #264: `a86a590a5e2c32c18e03522f52896dbcf50c60ff`
- Scanner D Draft PR #262: `a91e370ae7e5197e9af71f8300eeaff4a7aff022`
- Additional Scanner C/B, Work235, RAW211 and Scanner227 refs pinned in
  `.github/workflows/atlas-factory-d-canonical-consumer.yml`.

No owner branch was modified, and no PR was merged.

## Actual Factory-owned implementation

- `aql_factory_d_canonical_consumer_v1.py`: separately SHA-sealed Factory
  ACK from an actual durable Core D `PENDING_CONSUMER` with verified
  source ACK, Scanner C explicit strategy approval and Core SHA parents.
- `aql_factory_d_lab_paper_v1.py`: AFTER Core persists the external ACK and
  independently verifies its event chain through `strategy_d_snapshot`,
  read Core's actual SQLite source again using `query_local`, verify the
  separate `#245` native price-query SHA and `#253` local query SHA via
  `bind_dual_query_identities`, and verify Scanner D's canonical
  projection/witness and Work235 policy fingerprints.
- Factory Lab invokes **the pre-existing Factory indicator kernels and AST
  rule interpreter** against each *prefix* of the eight Core-owned synthetic
  AAA 15m bars (seven closed-bar decision slots). It also computes observed,
  strictly post-hoc one-bar movements, labeling them diagnostic-only.
  Outputs are SHA-sealed `aql.factory.d.same-source-descriptive-lab.v1`.
- Isolated Paper constructs a native `PaperIntent(..., "declined")` and
  instantiates a native empty `PositionLedger`: it deliberately returns
  `REJECT`, with no broker/order invocation, no fills, no positions or events,
  no operational 15m route. Outputs are SHA-sealed
  `aql.factory.d.isolated-paper-decision.v1`.
- Signed combined receipt `aql.factory.d.canonical-lab-paper-gate.v1`
  binds the actual Core D Secretary ACK, strategy gate, Lab and Paper receipts.
  Factory does not overwrite/alias frozen Work235 config digest and derived
  Scanner C native15m config digest.

## One focused new-D combined gate

The existing Factory D branch workflow runs
`tests/test_aql_factory_d_canonical_consumer_v1.py` under Python
3.11 / 3.12 / 3.13 against the **pinned** Core D and Scanner D heads.
The same file checks ACK→Core durable `ACKED_CONSUMER`→actual Factory
rule evaluation→native isolated Paper; negative/replay covers missing ACK,
expired route, forged approval/ACK/witness, wrong frozen policy,
wrong Core local query/source SHA, parent mismatch and deterministic replay.
Core's canonical Secretary fixture is imported, not silently replaced by
a fake Factory or fake Core ACK.

The positive test prints `ATLAS_FACTORY_D_EVIDENCE_JSON=` with full
Lab, Paper and combined SHA-sealed objects so independent Audit can
recompute seals and compare parent fields from Actions job logs.

## Deliberate limits

- The source is **generated synthetic native-ZIP-format AAA**, never original
  2024 Binance publisher evidence, even if the format says BINANCE.
- Fixture generation happens in each CI job. A job's SHA lineage proves
  its own same-source software test, not cross-job independent market custody.
- Work235 frozen strategy spec is 5m and Scanner C's canonical native
  projection is 15m. Their config SHA domains are **different** and stored
  separately; Lab applies the strategy's existing immutable v1 rule grammar
  to the explicit native15m test cohort, not to an operational 5m/Paper lane.
- The eight synthetic bars cannot support credible performance, alpha,
  real trades, PIT, original market breadth, strategy approval for trading,
  2024 history or holdout inference. Lab returns
  `INSUFFICIENT_EVIDENCE` and no modeled fills.
- Earlier unrelated BTCUSDT ZIP versus Scanner synthetic JSON remains
  `WAIT_SOURCE_PROVENANCE_NOT_CONNECTED`; this D fixture is not a repair.
- B96/Feb-Aug/106 older tests and prior #256 Audit judgments remain unchanged.

## Required independent acceptance

After exactly pinned Factory D GitHub Actions passes, verify the generated
Lab/Paper/combined receipt digests, 8-source-bar/7-decision census,
Core Secretary state and restart/replay, that all negative tests fail closed,
and Paper zero-order invariants. Request **one** new-D read-only Audit #256
review. Never merge or authorize G0/operational trading from this evidence.
