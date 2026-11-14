# One-bar receipt integration rehearsal

Use a disposable tree of #286 at d072544427d6b08473c88b2e36d5857cfd8581dc.
Copy tools/binance_live_feed/quota.py from #305 at
607f258ce9aa754dca8e1ca8c77a69cf4f498398 into that tree (GitHub blob
can be checked at the pinned commit). Overlay only tools/atlas_single_receipt.py
and tools/test_atlas_single_receipt.py from this change. From the disposable
tree on POSIX:

    PYTHONPATH=.:src python -B -m unittest tools.test_atlas_single_receipt -v

No market data, network transport, G2 database or existing operator state is
used. The adapter persists a bounded frame before using existing G1
commit-return and the #286 as-of Scanner and Factory readback. For non-fixture
readback the receipt digest must be pinned externally and provided by the
caller. Content seals are integrity checks, not signatures. Recovery after
the frame commit retains receive time and uses actual materialization time
for the decision. The first single-bar fixture cannot warm up the strategy.
Factory reports the census; authenticated admission stays WAIT.

Local reservation permits at most one connection attempt for this run and
uses #305 message/stream limits. It reports SHARED_EGRESS_UNVERIFIED. It does
not establish aggregate provider usage. A future runner must own the one-shot
deadline, clock qualification, exact window and endpoint binding, rate-status
handling, approved private custody and verified public egress budget or a
separate explicit residual-risk decision. Do not attach a transport or run a
capture based on this offline package. Strict #301 is outside the lane.
