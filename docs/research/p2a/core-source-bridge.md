# Work -> Core read-only source bridge

Owner integration scope #77/6599410585; actual Core handoff #180/6599477099.
This adds an executable source constructor/validation command to existing Draft
#223. It does not redo intake, source acquisition, P0/P1, Core scheduling or
Factory outcomes. Only new Work-owned files; no cross-branch copy/merge.

Retained input manifest SHA9b34e972e05002a7d6b11152e72164af825960b60e36c65ccf8049ce411eb4ff,
handoff SHA4031aea0b421d3749441cf40a09699d8bb0b27cee9320b848b3d1fd1345101bc,
index SHA0988fda2d3fa04d3ec99b135e549aa08a684a2c9d77157811d6b882af757cc17.
Existing original source/manifest/index bytes remain unchanged.

Core #221 advanced from9823f68221cc31e4b12dc11d5713513df22c69fb to
0842fc0a753ec6a3327c00c24e74908e8f6ca39c; source types/validate_bars are unchanged.
Actual diff adds only the explicit TEST_ONLY schedule flag. The retained handoff
correctly keeps its original declared9823 pin; it is NOT regenerated/relabeled.
Runtime uses0842 and records both pins. Exact Core producer file byte SHA256:
1162adc7bf755ae3fd7fe4a365c6f9c9409cf8fb74900fa40567456bfffe929d.
Import is refused if that file pin differs. Place the external Core checkout in
an isolated read-only runtime; do not copy its producer into Work/Factory code.

```sh
export AQL_P2_CORE_MODULE=/isolated/core-0842/research_wp_r0/aql_p2_core_producer.py
python -m unittest -v tests.test_aql_p2a_core_source_bridge
python -m research_wp_r0.aql_p2a_core_source_bridge \
 --intake-directory /private/EXISTING-p2a-development-delivery \
 --core-module "$AQL_P2_CORE_MODULE" \
 --adapter-code-sha FULL_NEW_WORK_HEAD \
 --receipt /private/NEW-core-source-bridge-receipt.json
```

The pinned Core file may be obtained through a detached checkout of exactly0842;
no source-data downloads occur. Missing private directory is a genuine runtime
access blocker, not grounds to ask for old January files or regenerate inputs.
Existing receipt paths fail closed; original input is never written.

The bridge calls HistoricalSourceV1, HistoricalBarV1 and validate_bars ONCE PER
DATASET: February2784 bars and August2976 separately. It validates exact source,
per-dataset normalized-index and manifest hash domains, every mapped bar field,
null historical availability and archived-closed finality. Concatenating disjoint
months into one native contiguous source is forbidden. Hashes are Work canonical
bar records, not silently relabeled vendor CSV hashes or historical PIT proofs.

Result COMPATIBLE_SOURCE_MAPPING_ONLY reports the two data validations and pins.
It does NOT call schedule_pair, construct opportunities/trials/BASE/SHADOW,
invoke Factory build_lab or evaluate any candidate/holdout. Missing actual real
opportunities/hypothesis/preregistration/arms remains NOT_EVALUABLE. Factory owns
the distinct TEST_ONLY producer->paired-consumer handshake on its own branch.
No synthetic source result is presented as actual data. Basic new integration
tests are required; broad scientific Audit remains postponed.

Retained P2 raw/index data stay private. Publish only code, TEST_ONLY fixtures,
counts/status/digests. No merge/main/other branch changes, G0, orders/Paper/Live.
