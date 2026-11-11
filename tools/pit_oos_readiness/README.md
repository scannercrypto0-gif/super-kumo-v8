# #299 prospective scientific readiness

This offline rehearsal joins Core #290's native presample seal and journal admission
to Factory #291's cost and exit evaluator and immutable result store. The PR is
stacked on the exact, unmerged Factory head. Core's two required modules are staged
from their exact Git objects in a private checkout overlay. Package #298 owns
`tools/actual_research_batch_bridge/`. This PR owns this directory and its workflow.

## Reproduce

From a disposable checkout, set PYTHONPATH to `src;.` on Windows or `src:.` on
Ubuntu. With Python 3.13 and pytest 9.0.2:

```text
python -B -m tools.pit_oos_readiness.dependencies --fetch
python -B -m pytest tools/pit_oos_readiness/test_readiness.py -q --junitxml=pit-tests.xml
python -B -m tools.pit_oos_readiness.readiness pit-evidence
python -B -m tools.pit_oos_readiness.manifest pit-evidence
```

The dependency step fetches only Git source objects. The runner has no networking,
provider client, credential read, real activation or holdout release path.
The mock root is dedicated to this run. Repeating it reconciles identical receipts.
The two-process test adds a hard exit after one verified ACK and verifies that a
separate process resumes to the same canonical decision. A native commit without
its observed ACK fails closed. Local bytes remain subject to the custodian's
authority. An independently retained manifest pin is needed to detect replacement
of an entire local evidence set.

## Scope of the joined gates

| Gate | New evidence |
|---|---|
| P0 | Pins and boundaries for rights, clock, source, custody and execution observability. #294/#295 were accepted separately. Historical and operational G2 evidence cannot supply scientific OOS. |
| P1 | Canonical native plan, fixed features and signal schedule, attempts and budgets, split and embargo, cost and exit parameters, baseline and mock witness. Immutable files and externally retainable digests. |
| P2 | Publisher release 1 and mock witness bound to the rights hash, source identity, freeze, stable key and content. Final UTC slot, publication, first known, receive, ingest and commit-return are distinct fields. Foreign/corrected/late evidence cannot replace a stored first release. |
| P3 | Two train slots and 48 validation slots, with 72h embargo before validation and OOS. A separate two-slot OOS reservation has zero prices and no reader. Metadata check refuses foreign/OOS rows in the training journal before native replay. All 50 opportunity slots are reconciled. |
| P4 | One selected modeled trial, one failed and one unscanned, all preserved. Factory produces all 72 outcome rows and 18 cells from five candidate and three independent fixture placebo entries. Bonferroni denominator reserves all 54 cells across three attempts. Unknown fill and intrabar cases retain no return. Costs and leg sizing reconcile for modeled fills. Regime labels are fixed diagnostic fixture tags. No statistical inference. |
| P5 | Exact-head Windows and Ubuntu CI, fresh process parity, hard crash and resume, source and result attacks, file manifest and pending owner envelope. |

The mock clock and HMAC keys are public deterministic fixtures. They demonstrate
binding, ordering and rejection behavior. They provide no independent timestamp
or publisher signature. Passive fill fractions here are fixture assumptions.
Real queue position, adverse selection, latency and market impact require
separately licensed and observed evidence. There is no empirical fill or alpha claim.

The separate `proof` command verifies detached Ed25519 signatures from five
distinct public key pins using OpenSSL. It checks the owner plan, source and
rights bindings, UTC budget and splits, witness before first open, initial
publisher release, independently signed receipt time and immutable custody ACK.
The trust-map hash must be retained independently of the bundle. Distinct keys
prove key separation, while institutional independence and issuer authority
require Audit evidence. The command reads signed metadata and plan bytes only.

```text
python -B -m tools.pit_oos_readiness.proof bundle.json trust.json TRUST_SHA256 plan.json
```

Each signed object contains `role`, `payload` and a base64 `signature`. Sign
the canonical UTF-8 bytes of `{"role":role,"payload":payload}` using that role's
Ed25519 key. The trust file maps owner, witness, publisher, receiver and
custodian to their public PEM keys. Tests generate ephemeral signers. Published
evidence contains no private signer keys.

## Future real-data acceptance playbook

1. Complete the single [owner decision envelope](owner-envelope.json) in private
   custody. The Coinbase Exchange BTC-USD Spot 15m proposal has a zero spend ceiling,
   at most 4,096 slots and 16 MB of isolated local custody. Verify actual capacity,
   exact endpoint and rate budget before authorizing. The [provider's published
   terms](https://www.coinbase.com/legal/market_data) are a reference. Obtain the
   terms applicable to the owner, permission for intended research and retention,
   and any consent needed for independent reviewers or sharing derived work.
2. Before any eligible source release, freeze the actual protocol, feature
   availability, strategy and null, costs, exits, opportunity and trial universe,
   purge, UTC windows, stopping rule and release authority. A trusted independent
   issuer must sign and timestamp the exact canonical protocol and custody
   binding. Retain the receipt outside the collector's and analyst's authority.
3. In an authorized future phase, verify the actual issuer and provider evidence
   before enabling a collector. Capture initial publication/version and separately
   observed receive, ingest and durable commit ACK. Require first-known-at proof,
   retain holes and quarantine conflicts and revisions. A candle close, a
   retrospective file checksum or a later response is insufficient.
4. Keep OOS bytes in separately authorized storage under a different custodian
   identity. Grant analysts only the commitment and coverage counts until the
   release authority confirms all gates. Keep G2 forward maturity separate.
5. Independent Audit checks genuine issuer authority, trusted clocks and exact
   source bytes, then reviews the one-shot evaluation path if evidence warrants
   it. The signed-proof verifier checks the common evidence contract offline.
   Publisher and custodian availability, trust anchors and a separately
   authorized real-cohort admission and evaluation run are external gates.
   The holdout remains locked meanwhile.

The genuine cohort status is REAL_PIT_OOS_BLOCKED. The engineering receipt
describes the bounded rehearsal with collection NOT_ACTIVATED.
