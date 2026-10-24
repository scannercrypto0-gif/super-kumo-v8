# G2 Core offline PIT contracts — Draft

Only a deterministic non-trading schema and volatile replay fixture. Not an integrated Scanner, Secretariat, Paper Trader, production capture or durable journal. Eight market-context slots must be supplied or explicitly missing, with actual source/availability timestamps; future/stale context fails closed. Snapshot SHA-256 identifies canonical content, not independently anchored tamper-proof custody.

Opportunity dispositions: observed/rejected/expired/no_fill. Identical replays are idempotent; conflicting updates are rejected. Late context and corrected observations require a separately reviewed append-only correction-event contract; no silent overwrite is allowed. 4h/24h/72h observations require actual documented receipt; pending/missing are not successful evaluations. The ledger is in-memory only; no restart durability or real observation evidence is claimed.

PaperIntent is an interface only; no fills, orders, broker, trading, background queues, cloud, Factory or holdout integration. OD-02/03/05 and activation remain owner-gated.

Focused test: `python -m unittest discover -s tests -p test_g2_observation_contracts.py -v`. CI on the Draft PR is required before acceptance.
