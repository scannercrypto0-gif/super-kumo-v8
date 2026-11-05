# Discoverer E → Factory #265 handoff contract (proposal; no consumer execution claimed)

**Discoverer PR:** #268 stacked on #258 HEAD f165fae48373ac739a0253554d9b51de055ad114. **Factory owner:** #265, combined gate #266. Discoverer generated research path is **independent** of Scanner operational path.

## Interface, inputs and identity

Factory should consume `ResearchHandoffDecisionV1`, `DiscovererResearchIntakeV1`, `VerifiedLedgerMembershipV1`, immutable `DiscoveryCandidatePackageV1`, `FactoryLabReceiptV1`, `NominationEvidenceV1`, and an independently custodized `DiscovererLedger.to_dict_list()` snapshot.

Only `decision.status == ELIGIBLE_FOR_FACTORY_RESEARCH` plus *Factory's own independent re-verification* of snapshot SHA chain/checkpoint/attempt mapping may enter Factory Lab. Match candidate ID, package/strategy/nomination digests, family/search-plan, receipt digest, ledger checkpoint, source ID/version, cutoff/known-at and policy. Reject/quarantine incomplete proof, source/PIT mismatch, duplicate experiment, mutated manifest or sealed holdout. Source attestation required independently by Core; do not upgrade synthetic fixtures to historical.

`VerifiedLedgerMembershipV1` verifies a complete canonical snapshot and that the attempt at `package.attempt_ledger_head` was PENDING for that exact candidate/strategy/family/nomination/search-plan. A later COMPLETE entry is permissible. Its digest is SHA of its fields: ledger_reference, checkpoint_head, ledger_root, entry_index, entry_digest, attempt_id, candidate_id, package_digest. It is **not a signature**, not independent custody by itself, and cannot prove the source was uncontaminated. Factory must fetch the ledger snapshot through an independently trusted channel, not blindly accept the calling Discoverer's JSON.

Existing proposed `DiscovererResearchIntakeV1` **still says** `ledger_membership_status=NOT_VERIFIED`, `factory_consumer_connected=FACTORY_CONSUMER_NOT_CONNECTED`, `evaluation_status=NOT_EVALUATED`. This is intentional to prevent self-promotion by `LedgerMembershipProofV1.build()`, whose self-hash is not independent attestation. Factory's own result/ACK (if any) must be separate, with source, exact input, evaluation/code/config/experiment/receipt SHA and no authority to trade.

## Boundaries and gates

Discoverer owns generation, ledger membership verifier, intake admission, quarantine/duplicate records and fixtures. Factory owns Lab consumer, store, ACK, results and Package E G2/G4/G6/G8/G9/G10 combined integration proof. Known gap: `DiscovererLedger` is in-memory and `LabAttemptLogV1` is in-memory; exporting/reloading verified records is not a durable crash-safe queue. Factory must test durable intake/readback/restarts. No edits to other owners' branches. No holdout, G0, production paper, trade or PR merge.
