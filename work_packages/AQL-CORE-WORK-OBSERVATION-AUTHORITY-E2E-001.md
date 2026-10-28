# Observation authority E2E execution

Direct owner request 2026-10-28 authorizes completing #144, bounded public
market capture, existing Drive vault upload/download verification and optional
Windows2 Guardian. No merge, trading, OOS or final G0 approval.

Starting head 6cb17079b71e7aaa33de756b60ad59686b260aad, main dbc191df72f4b4d1ebb7d490926dcad4325dac12.
Core #142/#137 and #144 are unmerged stacks, not accepted main.
Acceptance frozen before implementation:
- CLI capture automatically snapshots to local outbox without remote I/O;
  export failure is visible and next checkpoint/restart can recover durable ledger.
- Session-bound UTC diagnostics retain measurement, validity and uncertainty;
  reject stale/restart/wall step/unsynchronized/over-threshold samples.
- Separate Guardian verifies bundle and upload download bytes; digest mismatch,
  outage and replay never grant custody/PIT. No remote dependency in Core.
- Existing pinned Factory bridge denies real PIT; existing tamper/reversion/
  process-exit proofs reused. New integration tests cover changed call paths.
- Real Drive proof and real public capture reported separately from fixtures;
  owner Windows runs NOT EXECUTED unless actual access exists.

Continuity: HANDOFF_REGISTER's last explicitly owner-confirmed cross-chat
submitted baseline is AQL-HO-20261021-002/#14, not a newly invented submission.
Latest code delivery in current scope is #144/6465387750 at starting head;
UTC option B owner checkpoint #144/6465335332 and implementation
#134/6465367240 supersede prior not-implemented note. #128 through6463127686,
#134 through6465410783 reviewed. Historical D1/D2/D3 and Factory work are
already documented in those records, not reimplemented here. All accessible
post-baseline comments are retained in continuity.json; unavailable chats remain
COVERAGE GAP, not exhaustive reconciliation. Current direct request supplies
execution authority for this scope despite old documentation-only limits.
