# Discoverer research to review vertical

[Owner dispatch](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/276#issuecomment-6818900562). Base is #268 `149ca90c09b96abb45d3bc2839b657711c9826ac`, prior #276 `9b60eb00aa890ecbd7e617925896e02963c1b5e3`. The new paths are owned by Discoverer. Stage Core #308 `84649a323613bf4415c7abc41e774381aa379428`, Factory #267 `203289f7cac191dca92df2f4d8fa84ec9cf369cc`, Promotion #288 `3e7afd10497365dbbfb2a0760bf5f6d0a4591fd1` in separate checkouts. No dependency content is merged or copied into this branch. Current main at preflight `90af9794880cbeb00e7e974bfa906ff5e9666183`. #277, #271 and #307 stay pinned at the owner assignment SHAs and are separate evidence.

## P0 seam inventory and fixture

| Seam | Disposition |
| --- | --- |
| Core typed as-of, membership, rights and original vintage | ALREADY_COVERED by #308 [CI](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/43052553949). Reuse `DiscovererView.snapshot/context`, existing fixture and `factory_inputs`. Smoke verified native imports, up/down/unknown and rejected a foreign schema. |
| Discoverer watch, prereg, gain/loss control, durable ACK | ALREADY_COVERED by #276 [D1–D6 CI](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/43031928957). Reuse the original Loop, candidate/plan/validation schemas and checkpoint. |
| D6 hypothesis → E registry | GENUINELY_MISSING. #308 reproduced native `SCHEMA_OR_PROMOTION` if the typed evidence packet is sent as an experiment. Use existing E builder, register and readback as a blocked research record, with null executable strategy and native query refs. No fake dual Core pins, no claim of independent Factory trials. |
| Existing dashboard → searchable Discoverer section/export | GENUINELY_MISSING. #288's dashboard is a Python read model. Compose a `discoverer` section onto its actual payload. Test after reopening persisted review. No separate dashboard process, UI framework, endpoint, database, notification sender or existing owner-file change. |

G0-GOV-01 continuity used [PM OS](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-6721828613), [close-first](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-6741235513), [owner decisions and latest accessible handoff summary](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-6818820367), [owner host readback](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/271#issuecomment-6817605647) (206 decisions, 72h pending then), [Core delivery](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/273#issuecomment-6800531232), [Integration](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/271#issuecomment-6818217282) and [independent Audit](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/134#issuecomment-6818717509). The latter accepts an earlier Scanner-to-Promotion slice with [CI 43177927719](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/43177927719). No private evidence was inspected and those suites were not explicitly rerun.

Frozen synthetic fixture reuses #308 inventory. BTC, ALT and PAXG are literal fixture subjects on Spot. PAXG is distinct from physical gold. Origin 200 ms, four 100 ms slots, including one injected outage at slot 400. The gain and loss occur before matched no-event controls with active precursor; late news and corrections at/after the exclusive cutoff cannot be input. Core's TEST_ONLY commit clock projects availability; original known-at remains null. Expected 12 watch rows, two UP, two DOWN, four NO_EVENT, one UNKNOWN and three MISSED. Eight complete context searches, four unavailable. Two candidate-generation attempts, two pending and zero independent Factory trials. Priority alert previews are deterministic research records and never sent.

## Contracts and reproduction

Native E admission builds one experiment per candidate with the complete generation census and stable parent seal covering candidate, Discoverer tick and typed pre-onset Core inputs. Existing transactional idempotency and readback are exercised. Independent evaluation is `EVALUATION_PENDING`: a non-executable precursor and independently unattested PIT/OOS. No executable D4 rule, strategy authorship, Paper, LIVE, Telegram or fills. A simulated crash after commit before ACK leaves exactly one native record; repeat advances to two without duplication. A conflicting replay rejects.

`aql.discoverer.weekly-review.v1` is a bounded, SHA-sealed read artifact with UTC Monday-based interval, separate attempt/watch/trial counts, provenance and revisions, candidate and Factory receipts, and preview links. Read with an independently supplied pin. Dashboard filtering and freshness use the reopened read artifact. Scope is an offline section in the existing dashboard **read model**. There is no deployed browser UI or network service in this package. JSON/CSV share the same seal. CSV columns kind/id/state/direction/hash/canonical JSON make all nested and null facts round-trip exactly; reorder, forgery or duplicate rows reject. The report lists UTC boundaries, counts and alert lineage. Human Strategy Author review remains owner-gated; there is no importer that authors strategy code.

Set `DISCOVERER_REVIEW_STAGE` to the directory containing exact `core`, `factory`, and `paper` checkouts, and `PYTHONPATH` to the Core checkout's `src` and this checkout's root with the platform separator. Install pytest 8.4.2 and run:

```text
python -B -m pytest tools/strategy_discoverer_offline/tests/test_review_vertical.py -q -p no:cacheprovider --basetemp <isolated-test-temp>
python -B tools/strategy_discoverer_offline/tests/test_review_vertical.py <first-empty-root>
python -B tools/strategy_discoverer_offline/tests/test_review_vertical.py <first-empty-root>
python -B tools/strategy_discoverer_offline/tests/test_review_vertical.py <second-empty-root>
```

The command prints the joined digest and persists review JSON, CSV, Markdown and actual dashboard payload under the given disposable root. Verify repeated hashes and byte-identical projections. The dedicated workflow checks all exact heads, compares fresh stores/reopen and retains the files.

External owners: Core/Operations for lawful sources, current rights, deployed timing and witnessed 24/7. Factory/Lab for independently frozen scientific protocol and genuine PIT/OOS, plus a human-authored executable strategy where applicable. Integration for authenticated deployed handoff and dashboard hosting. No original/private data, provider traffic, #286 modification, production activation, merge, G0 or authorization.
