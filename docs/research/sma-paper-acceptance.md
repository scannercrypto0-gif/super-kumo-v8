# SMA3/12 isolated Paper acceptance

The frozen candidate is `first_cycle_sma3_12` v1, SHA-256
`79c6f9ff291b14bf55434367ef039c61f8899f63c351fe47a85d647dc33a9f58`.
The staged runtime derives it with the #300 variant function from the #309
baseline plan and checks the digest against the prior saved strategy report.
Its 15,381 retrospective cost rows are prior modeled evidence. They contribute
zero decisions or fills to this acceptance.

| Component | Tested pin and ownership |
| --- | --- |
| Main reference | `90af9794880cbeb00e7e974bfa906ff5e9666183` |
| Integration #271 | Parent `a3c1952de7ebae979b098360e8a899817be2ced6` plus this commit |
| SMA variant and native Scanner evaluator #300 | `403e247a807b165bc1d6c63991981ce10bc7f6c7` |
| Historical Scanner census #309 | `35972ffe115cbc1fcde5655d56f1484b19452ca0`; baseline plan only at runtime |
| Paper G3 #288 | `3e7afd10497365dbbfb2a0760bf5f6d0a4591fd1`; native adapter, reducer, position journal and ledger |
| Saved Factory operator staging #297 | `dd3e149afe73d9d04c9892ad35005b04fb675fff`; existing kernels, operator report dependencies |
| Factory E #267 | `1df72b3cdc3dd551fd6d42ec2b83d4925c4b7cdd`; includes #310/#311 on the Factory branch |
| Factory D #265 / C #260 | `a695e262da6787f752a13820f02dd00eef8ef1cd` / `94107e2bbe9e06088caeaf87768796d6b77bee42`; Secretary/Lab authority boundary |
| Daily report draft #312 | `73d677852725a4af51868c6906b23fc2825db6f0`; standing daily scheduling separate |

#288 and #300 descend from the current main pin. #309 is stacked on #296
`eb49308d61ffdfc24ed5032df2cb541f37c48bfe`. Factory E is stacked on D and C.
The solution keeps the cross-draft adapter in existing integration #271. A
full merge of #288 into #271 has overlapping Factory code. The reproducible
test runtime extracts the named files from exact Git objects into a disposable
tree. This staging is test composition. No source branches are merged.

## Fixture and execution

The only producer generates 19 BTCUSDT-labeled 15-minute fixture bars with a
declared one-second availability delay. Each decision is recomputed against
its own closed prefix and paired with the simulated source, commit, strategy
and Scanner hashes. The G3 adapter consumes a synthetic prospective-shaped
receipt. A #309 retrospective census with UNKNOWN availability is rejected.
Every decision has a deterministic proposed or declined PaperIntent. The
run and instance identities are derived from the sealed decision lineage.

Execution is long-only with one active position, one synthetic unit per entry,
two eligible bars before expiry, a 1% stop and a 3% target anchored at the
decision close, and a 16-bar holding limit. With one-second delay, the immediate
next grid open has already passed. G3 uses the first strictly later grid open.
Known assumed capacity is two units at the fill/target slot and zero at the
expiry slots. The taker fee is 10 bps per side, half-spread 1 bp and slippage
2 bps. G3 resolves stop-and-target ambiguity as UNKNOWN. The fixture exercises
a target close and a fully observed no-fill. Prices in the durable journal
are generated fixture literals. No live prices or WebSocket frames feed this
adapter. Future prospective operation needs independent review, separate owner
approval for operation, and explicit custody/retention scope for modeled
transaction records and any additional price input needed for replay.

## Reproduce

From #271 with the four draft objects fetched, stage to a fresh directory.

```sh
git fetch --no-tags origin refs/pull/297/head refs/pull/288/head refs/pull/300/head refs/pull/309/head
python -B tools/atlas_sma_paper_stage.py /path/to/stage
cd /path/to/stage
PYTHONPATH=src python -B -m tools.atlas_sma_paper run acceptance
PYTHONPATH=src python -B -m tools.atlas_sma_paper replay acceptance --pin <acceptance-sha>
```

On Windows use `$env:PYTHONPATH='src'` in PowerShell. Replay verifies the
external acceptance pin, Scanner receipt and exact journal bytes before
native readback. The workflow compares two separate process reads and tests
journal tampering. The producer checks idempotency, conflicting duplicates,
foreign strategy, retrospective source, receipt and source-parent tampering
and a failed clock indicator. The error reasons are in the saved report.

For the standing Windows service, run the staged
`tools/atlas_live_operator_windows.ps1` with `-LiveRoot`, the activation's
known `-ConfigSha256`, and a new `-Output` path. It uses the existing native
saved receipt verifier and Factory E operator path. The report bounds reads
to 16 recent receipts, three segment logs and 80 recent supervisor entries.
Use the same command on demand or for a daily readout. It changes no scheduler
definitions and has no GitHub publisher.
