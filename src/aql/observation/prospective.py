"""Research-only G1 → Scanner → durable G2 on a dedicated observation ledger."""
from bisect import bisect_left
from contextlib import closing
from pathlib import Path
from time import time_ns

from aql.g1_integrity import content, fingerprint
from aql.observation.contracts import HORIZONS_MS, digest
from aql.observation.durable_bridge_v1 import DurableG2Bridge, require

STEP = 900_000
CLOCK_MS = 5_000
MAX_BARS = 7 * 96
SYMBOL = "BTCUSDT"
INTERVAL = "15m"
DECISIONS = {"ENTRY_SIGNAL", "EXIT_SIGNAL", "NO_SIGNAL", "REJECTED", "UNKNOWN"}


class ProspectiveObserver(DurableG2Bridge):
    """Reuse G2's append/seal/transaction primitives without accepting TEST_ONLY events."""

    def __init__(self, db, journal, store, fixture, *, synthetic, read_only=False):
        from tools.scanner_strategy_f import research_strategy_plugin as scanner

        self.journal, self.store = journal, store
        spec = fixture["payload"]
        plugin = scanner.register_strategy_plugin(
            spec["definition"], config_digest=spec["config_digest"],
            source_spec_receipt=fixture,
        )
        self.definition = scanner._definition(spec["definition"])
        self.identity = {
            "strategy_id": spec["strategy_id"], "strategy_version": spec["strategy_version"],
            "definition_sha256": spec["definition"]["digest"],
            "config_sha256": spec["config_digest"],
            "evaluator_sha256": plugin["payload"]["evaluator_code_sha256"],
            "strategy_fixture_sha256": fixture["sha256"],
            "evidence_mode": "SYNTHETIC_TESTED" if synthetic else "PUBLIC_WS_OBSERVATION",
            "journal_instance": journal.instance_id,
        }
        self.read_only = read_only
        if read_only:
            self.db = Path(db)
        else:
            super().__init__(db)

    def _replay(self, con, *, prospective=None):
        decisions, outcomes = {}, {}

        def ingest(kind, identity, data):
            require(data["run"] == self.identity and data["trading_authority"] == "NONE",
                    "PROSPECTIVE_IDENTITY_DRIFT")
            if kind == "prospective_decision":
                require(identity == data["parent"]["key"] and identity not in decisions
                        and data["state"] in DECISIONS
                        and data["parent"]["close_ms"] < data["parent"]["ingested_ms"]
                        <= data["parent"]["commit_ms"] <= data["cutoff_ms"]
                        and data["opportunity_id"] == self._opportunity(data),
                        "PROSPECTIVE_DECISION_DRIFT")
                decisions[identity] = data
            else:
                decision = decisions.get(data["decision_key"])
                require(kind == "prospective_horizon" and decision is not None
                        and decision["opportunity_id"] is not None
                        and data["opportunity_id"] == decision["opportunity_id"]
                        and data["horizon_ms"] in HORIZONS_MS
                        and data["due_ms"] == decision["cutoff_ms"] + data["horizon_ms"]
                        and data["due_ms"] <= data["parent"]["close_ms"] < data["parent"]["ingested_ms"]
                        <= data["parent"]["commit_ms"] <= data["recorded_ms"]
                        and identity == f'{decision["opportunity_id"]}:{data["horizon_ms"]}'
                        and identity not in outcomes
                        and data["state"] == self._horizon_status(data["due_ms"], data["parent"]),
                        "PROSPECTIVE_OUTCOME_DRIFT")
                outcomes[identity] = data

        legacy, legacy_outcomes, tail = super()._replay(con, prospective=ingest)
        require(not legacy and not legacy_outcomes, "PROSPECTIVE_DB_REQUIRES_ISOLATION")
        return decisions, outcomes, tail

    @staticmethod
    def _opportunity(decision):
        if decision["state"] not in {"ENTRY_SIGNAL", "EXIT_SIGNAL"}:
            return None
        return digest({k: v for k, v in decision.items() if k != "opportunity_id"})

    @staticmethod
    def _horizon_status(due, parent):
        if parent["close_ms"] >= due + STEP:
            return "missing"
        if parent["commit_ms"] > parent["close_ms"] + CLOCK_MS:
            return "late"
        return "mature"

    def _parents(self, as_of_ms):
        bars = self.journal.replay(SYMBOL, INTERVAL, limit=MAX_BARS + 1)
        require(len(bars) <= MAX_BARS, "PROSPECTIVE_STORAGE_WINDOW_LIMIT")
        with closing(self.store._connect()) as store_conn:
            for bar in bars:
                key = bar.stable_key()
                receipt = self.journal.commit_receipt(key)
                committed = receipt["commit_return_observed_at_ms"]
                expected = fingerprint(content(bar))
                if (bar.source != "binance_ws" or bar.bar_open % STEP
                        or bar.bar_close != bar.bar_open + STEP - 1
                        or receipt["status"] != "SQLITE_COMMIT_RETURN_OBSERVED"
                        or receipt["content_digest"] != expected
                        or not bar.bar_close < bar.ingested_at <= committed <= as_of_ms):
                    continue
                self.store.require_eligible(key)
                stored = self.store._original_bar(store_conn, key)
                if stored is not None and fingerprint(content(stored)) == expected:
                    yield bar, {
                        "key": key, "open_ms": bar.bar_open, "close_ms": bar.bar_close,
                        "ingested_ms": bar.ingested_at, "commit_ms": committed,
                        "bar_checksum": bar.checksum, "content_sha256": expected,
                        "g1_receipt_sha256": digest(receipt),
                    }

    def tick(self):
        """Capture a real cutoff; resume from durable receipts after interruption."""
        require(not self.read_only, "PROSPECTIVE_READ_ONLY")
        from tools.scanner_strategy_f.research_e2e_diagnostic import _eval_strategy

        now = time_ns() // 1_000_000
        parents = list(self._parents(now))
        closes = [bar.bar_close for bar, _ in parents]
        active_keys = {proof["key"] for _, proof in parents}
        with closing(self._connect()) as con, con:
            con.execute("BEGIN IMMEDIATE")
            decisions, outcomes, tail = self._replay(con)
            for i, (bar, parent) in enumerate(parents):
                key = parent["key"]
                if key in decisions:
                    require(decisions[key]["parent"] == parent, "PROSPECTIVE_G1_PARENT_DRIFT")
                    continue
                state, reason, window = "UNKNOWN", "STALE_OR_RESTARTED_BEFORE_DECISION", []
                if now - parent["commit_ms"] <= CLOCK_MS and now - bar.bar_close <= CLOCK_MS:
                    window = [(bar, parent)]
                    for prior, proof in reversed(parents[max(0, i - 63):i]):
                        if (prior.bar_open != window[-1][0].bar_open - STEP
                                or proof["commit_ms"] > parent["commit_ms"]):
                            break
                        window.append((prior, proof))
                    window.reverse()
                    try:
                        signal_rows = [
                            {**content(item), "bar_open_ms": item.bar_open, "bar_close_ms": item.bar_close}
                            for item, _ in window
                        ]
                        state = _eval_strategy(self.definition, signal_rows)[-1][1]
                        reason = "WARMUP_OR_GAP" if state == "UNKNOWN" else None
                    except (ValueError, ArithmeticError):
                        state, reason = "REJECTED", "EVALUATOR_REJECTED_INPUT"
                decision = {
                    "run": self.identity, "parent": parent, "cutoff_ms": now,
                    "state": state, "reason": reason,
                    "inputs": [{k: p[k] for k in ("key", "g1_receipt_sha256")} for _, p in window],
                    "trading_authority": "NONE",
                }
                decision["opportunity_id"] = self._opportunity(decision)
                tail = self._append(con, "prospective_decision", key, decision, tail)
                decisions[key] = decision

            for key, decision in decisions.items():
                opportunity = decision["opportunity_id"]
                if opportunity is None or key not in active_keys:
                    continue
                for horizon in HORIZONS_MS:
                    due = decision["cutoff_ms"] + horizon
                    identity = f"{opportunity}:{horizon}"
                    index = bisect_left(closes, due)
                    if identity in outcomes or index == len(parents):
                        continue
                    # Use only finalized evidence already committed as of this tick.
                    bar, parent = parents[index]
                    state = self._horizon_status(due, parent)
                    result = {
                        "run": self.identity, "decision_key": key, "opportunity_id": opportunity,
                        "horizon_ms": horizon, "due_ms": due, "recorded_ms": now,
                        "parent": parent, "state": state,
                        "value": str(bar.close) if state == "mature" else None,
                        "trading_authority": "NONE",
                    }
                    tail = self._append(con, "prospective_horizon", identity, result, tail)

    def verified_read(self, *, as_of_ms):
        """Read only; event visibility depends on recorded UTC, including after restart."""
        require(type(as_of_ms) is int and as_of_ms >= 0, "PROSPECTIVE_READ_TIME")
        with closing(self._connect_readonly()) as con:
            decisions, outcomes, _ = self._replay(con)
        eligible = {parent["key"]: parent for _, parent in self._parents(as_of_ms)}
        visible = []
        for item in decisions.values():
            if item["cutoff_ms"] > as_of_ms:
                continue
            parent = item["parent"]
            source_valid = eligible.get(parent["key"]) == parent and all(
                eligible.get(proof["key"], {}).get("g1_receipt_sha256") == proof["g1_receipt_sha256"]
                for proof in item["inputs"]
            )
            horizons = []
            if item["opportunity_id"]:
                for horizon in HORIZONS_MS:
                    due = item["cutoff_ms"] + horizon
                    result = outcomes.get(f'{item["opportunity_id"]}:{horizon}')
                    state = "pending" if as_of_ms < due else "UNKNOWN"
                    evidence = None
                    if source_valid and result and result["recorded_ms"] <= as_of_ms:
                        observed = result["parent"]
                        if eligible.get(observed["key"]) == observed:
                            evidence, state = result, result["state"]
                    horizons.append({"horizon_ms": horizon, "due_ms": due,
                                     "state": state, "evidence": evidence})
            visible.append({"decision": item, "decision_sha256": digest(item),
                            "source_valid": source_valid, "horizons": horizons})
        body = {"schema": "aql.g2.prospective-verified-read.v1", "run": self.identity,
                "as_of_ms": as_of_ms, "rows": visible, "visible_sha256": digest(visible),
                "trading_authority": "NONE"}
        return {**body, "sha256": digest(body)}
