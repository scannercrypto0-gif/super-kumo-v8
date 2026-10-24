# G2 Core open-ended position tracking — offline contract

Owner decision: 4h/24h/72h are opportunity observation checkpoints, not automatic exit/expiry. A paper position remains open indefinitely until an explicit validated close event. HorizonPolicy is versioned, configurable, and separate from position state. No strategy, exit rules, order submission, live prices, portfolio accounting or real paper activation is implemented.

PositionLedger is an **in-memory test fixture**, not durable append-only custody. It supports duplicate replay, conflict rejection, strict chronological events and explicit closure. Missing quotes are not fabricated; there is no computed P&L or realized/unrealized result without validated pricing, quantity and cost evidence. This implementation does not yet satisfy operational restart persistence or Core Run isolation; both remain follow-on acceptance gates.

Run focused tests: `python -m unittest discover -s tests -p test_g2_position_lifecycle.py -v`. No integration or trading activation without separate owner gate.
