"""Pure deterministic reducer plus existing fsync/replay journal integration.

The native PositionEvent stream represents a SIMULATION AGGREGATE, including
WATCH before any exposure. It is isolated and must not be consumed as an actual
position stream. No new database or broker/order event engine is introduced.
"""
from dataclasses import asdict
from decimal import Decimal as D, localcontext
import json
from pathlib import Path
from .contracts import Policy, bar, canonical, dec, digest, ms, need, signal
from ..observation.positions import PositionEvent
from ..observation.position_journal import DurablePositionJournal

TERMINAL = {"CLOSED", "CANCELLED", "EXPIRED", "NO_FILL", "UNKNOWN", "REJECTED"}
SOURCE = "OFFLINE_SIMULATION_AGGREGATE_NOT_VENUE_POSITION_V1"


def code_identity():
    return digest({p.name:digest(p.read_text(encoding="utf-8"))
                   for p in sorted(Path(__file__).parent.glob("*.py"))})


def _amount(s, key):
    return D(s[key])


def _unknown(s, reason):
    s.update(phase="UNKNOWN", reason=reason, net_pnl=None)


def _fill(s, *, qty, price, maker, side, when):
    policy = s["policy"]
    notional = qty * price
    fee = notional * D(policy["maker_fee_bps"] if maker else policy["taker_fee_bps"]) / 10000
    adverse = notional * D(policy["maker_adverse_bps"]) / 10000 if maker else D(0)
    if side == "buy":
        need(qty <= _amount(s,"entry_remaining"), "ENTRY_OVERFILL")
        need(_amount(s,"entry_notional") + notional <= D(policy["max_notional"]), "MAX_NOTIONAL")
        need(_amount(s,"cash") >= notional + fee + adverse, "CASH_INSUFFICIENT")
        s["cash"] = str(_amount(s,"cash") - notional - fee - adverse)
        s["filled"] = str(_amount(s,"filled") + qty)
        s["entry_remaining"] = str(_amount(s,"entry_remaining") - qty)
        s["entry_notional"] = str(_amount(s,"entry_notional") + notional)
        s["phase"] = "TRIGGERED"
    else:
        need(qty <= _amount(s,"filled") - _amount(s,"exited"), "EXIT_OVERFILL")
        s["cash"] = str(_amount(s,"cash") + notional - fee)
        s["exited"] = str(_amount(s,"exited") + qty)
        s["exit_notional"] = str(_amount(s,"exit_notional") + notional)
    s["fees"] = str(_amount(s,"fees") + fee)
    s["adverse_cost"] = str(_amount(s,"adverse_cost") + adverse)
    s["fills"].append(dict(side=side, qty=str(qty), price=str(price), fee=str(fee),
                           adverse_cost=str(adverse), liquidity="ASSUMED_MAKER" if maker else "ASSUMED_TAKER",
                           execution_ms=None if maker else when,
                           assumed_execution_window=[when,s["last_bar"]] if maker else [when,when],
                           received_ms=s["updated_ms"]))
    if side == "sell" and _amount(s,"filled") == _amount(s,"exited"):
        s.update(phase="CLOSED", entry_remaining="0")
        s["net_pnl"] = str(_amount(s,"cash") - D(policy["capital"]))
        need(_amount(s,"net_pnl") == _amount(s,"exit_notional") - _amount(s,"entry_notional")
             - _amount(s,"fees") - _amount(s,"adverse_cost"), "CASH_CONSERVATION")


def _on_bar(s, b):
    need(b["symbol"] == s["signal"]["symbol"], "BAR_SYMBOL_MISMATCH")
    start, end = b["open_ms"], b["close_ms"]
    span = s["signal"]["interval_ms"]
    need(end-start+1 == span, "MIXED_INTERVAL")
    if s["last_bar"] is not None:
        need(start == s["last_bar"] + 1, "BAR_GAP_OR_REVISION")
    else:
        # No hidden execution interval may be skipped after the signal.
        need(start == (s["signal"]["decision_ms"] // span + 1) * span, "FIRST_BAR_GAP")
    need(start > s["signal"]["decision_ms"], "SAME_OR_PREDECISION_BAR")
    s["last_bar"] = end
    p = s["policy"]
    spread_slip = (D(p["half_spread_bps"]) + D(p["slippage_bps"])) / 10000
    o, h, l = (D(b[k]) for k in ("open","high","low"))
    capacity = None if b["taker_qty"] is None else D(b["taker_qty"])
    had_position = _amount(s,"filled") > _amount(s,"exited")
    maker_entry = False
    if _amount(s,"entry_remaining") > 0 and start > s["entry_decision_ms"] and start <= s["expiry_ms"]:
        maker_entry = s["mode"] == "maker"
        if maker_entry:
            limit = _amount(s,"limit")
            if o <= limit:
                _unknown(s,"POST_ONLY_MARKETABLE_OR_GAP"); return
            if l == limit:
                _unknown(s,"TOUCH_DOES_NOT_PROVE_QUEUE_FILL"); return
            if l < limit:
                if b["maker_volume"] is None:
                    _unknown(s,"MAKER_QUEUE_VOLUME_UNAVAILABLE"); return
                volume = D(b["maker_volume"])
                ahead = _amount(s,"queue_ahead")
                s["queue_ahead"] = str(max(D(0),ahead-volume))
                qty = min(_amount(s,"entry_remaining"),max(D(0),volume-ahead))
                if qty:
                    _fill(s,qty=qty,price=limit,maker=True,side="buy",when=start)
        else:
            if capacity is None:
                _unknown(s,"TAKER_DEPTH_UNAVAILABLE"); return
            qty = min(_amount(s,"entry_remaining"),capacity)
            price = o*(1+spread_slip)
            if not _amount(s,"stop") < price < _amount(s,"target"):
                _unknown(s,"ENTRY_PRICE_OUTSIDE_FROZEN_RISK"); return
            if qty:
                _fill(s,qty=qty,price=price,maker=False,side="buy",when=start)
                capacity -= qty
    exposed = _amount(s,"filled") - _amount(s,"exited")
    if not exposed:
        return
    stop, target = _amount(s,"stop"), _amount(s,"target")
    stop_hit, target_hit = l <= stop, h >= target
    # A maker fill is intrabar; even one exit threshold cannot establish which
    # occurred first relative to that entry. Preserve UNKNOWN, never optimistic PnL.
    if maker_entry and len(s["fills"]) and s["fills"][-1]["received_ms"] == s["updated_ms"] and (stop_hit or target_hit):
        _unknown(s,"MAKER_ENTRY_EXIT_ORDER_UNKNOWN"); return
    exit_price = None
    if s["exit_due_ms"] is not None and start > s["exit_due_ms"]:
        exit_price = o
        s["reason"] = "REQUESTED_EXIT"
    elif had_position and o <= stop:
        exit_price = o
        s["reason"] = "STOP_GAP"
    elif had_position and o >= target:
        exit_price = target  # conservative capped modeled target, not venue proof
        s["reason"] = "TARGET_GAP_ASSUMED_CAP"
    elif stop_hit and target_hit:
        _unknown(s,"SAME_BAR_STOP_TARGET_UNKNOWN"); return
    elif stop_hit or target_hit:
        exit_price = stop if stop_hit else target
        s["reason"] = "ASSUMED_STOP" if stop_hit else "ASSUMED_TARGET"
    if exit_price is not None:
        s["entry_remaining"] = "0"
        if capacity is None:
            _unknown(s,"EXIT_DEPTH_UNAVAILABLE"); return
        qty = min(exposed,capacity)
        # Once an exit threshold has fired, an unfilled remainder remains an
        # explicit market-exit request, not a silently disappearing position.
        if s["exit_due_ms"] is None:
            s["exit_due_ms"] = end
        if qty:
            _fill(s,qty=qty,price=exit_price*(1-spread_slip),maker=False,side="sell",when=start)


def reduce_state(prior, command):
    """Validate entirely before journal append. One frozen command -> one state."""
    need(type(command) is dict and type(command.get("op")) is str, "COMMAND")
    t = ms(command.get("at_ms"))
    with localcontext() as ctx:
        ctx.prec = 160
        if prior is None:
            need(set(command)=={"op","at_ms","signal","policy","instance"} and command["op"]=="watch", "WATCH_FIRST")
            sig = signal(command["signal"])
            policy = Policy(**command["policy"])
            need(type(command["instance"]) is str and 0 < len(command["instance"]) <= 128, "INSTANCE")
            need(t == sig["decision_ms"], "WATCH_TIME")
            return dict(schema="aql.paper-sim.state.v1", engine_sha256=code_identity(), phase="WATCH", signal=sig,
                        policy=asdict(policy), instance=command["instance"], updated_ms=t,
                        filled="0",exited="0",entry_remaining="0",entry_notional="0",exit_notional="0",
                        fees="0",adverse_cost="0",cash=policy.capital,net_pnl=None,fills=[],
                        last_bar=None,exit_due_ms=None,reason=None,
                        trading_authority="NONE",evidence_grade="SYNTHETIC_TESTED")
        s = json.loads(canonical(prior))
        need(t >= s["updated_ms"] and s["phase"] not in TERMINAL, "TERMINAL_OR_TIME_REGRESSION")
        s["updated_ms"] = t
        op = command["op"]
        if op == "arm":
            need(s["phase"]=="WATCH" and set(command)=={"op","at_ms","mode","qty","limit","stop","target","expiry_ms","queue_ahead"}, "ARM_FIELDS_STATE")
            need(command["mode"] in {"maker","taker"}, "ENTRY_MODE")
            qty,limit,stop,target = [dec(command[k]) for k in ("qty","limit","stop","target")]
            dec(command["queue_ahead"],zero=True)
            need(stop < limit < target and qty*limit <= D(s["policy"]["max_notional"]), "ENTRY_RISK")
            need(ms(command["expiry_ms"]) > t and (command["expiry_ms"]+1)%s["signal"]["interval_ms"]==0, "EXPIRY")
            s.update(phase="ARMED",mode=command["mode"],entry_remaining=command["qty"],
                     requested_qty=command["qty"],limit=command["limit"],stop=command["stop"],target=command["target"],
                     expiry_ms=command["expiry_ms"],queue_ahead=command["queue_ahead"],entry_decision_ms=t)
        elif op == "bar":
            need(s["phase"] in {"ARMED","TRIGGERED"} and set(command)=={"op","at_ms","bar"}, "BAR_STATE_FIELDS")
            _on_bar(s,bar(command["bar"],as_of_ms=t))
        elif op == "exit":
            need(s["phase"]=="TRIGGERED" and set(command)=={"op","at_ms"}, "EXIT_STATE_FIELDS")
            s.update(exit_due_ms=t,entry_remaining="0")
        elif op == "fallback":
            need(set(command)=={"op","at_ms","expiry_ms"} and s["phase"] in {"ARMED","TRIGGERED"}
                 and s["mode"]=="maker" and s["policy"]["allow_fallback"] is True
                 and _amount(s,"entry_remaining") > 0 and t > s["expiry_ms"]
                 and s["last_bar"] is not None and s["last_bar"] >= s["expiry_ms"], "FALLBACK_NOT_ELIGIBLE")
            need(ms(command["expiry_ms"]) > t and (command["expiry_ms"]+1)%s["signal"]["interval_ms"]==0, "FALLBACK_EXPIRY")
            s.update(mode="taker",entry_decision_ms=t,expiry_ms=command["expiry_ms"])
        elif op in {"cancel","expire"}:
            need(set(command)=={"op","at_ms"}, "CANCEL_FIELDS")
            need(s["phase"] in {"WATCH","ARMED","TRIGGERED"}, "CANCEL_STATE")
            if op == "expire":
                need(s["phase"] != "WATCH" and t > s["expiry_ms"], "EXPIRY_NOT_DUE")
                if s["last_bar"] is None or s["last_bar"] < s["expiry_ms"]:
                    _unknown(s,"EXPIRY_COVERAGE_UNAVAILABLE"); return s
            s["entry_remaining"] = "0"
            if _amount(s,"filled") == 0:
                s.update(phase="CANCELLED" if op=="cancel" else "NO_FILL",reason=op.upper())
            else:
                s["reason"] = "ENTRY_REMAINDER_CANCELLED_EXPOSURE_RETAINED"
        else:
            raise ValueError("PAPER_SIM_UNKNOWN_COMMAND")
        return s


class PaperSimulator:
    """Single-writer isolated assumed simulation, persisted by existing journal.

    Journal checksums are integrity evidence, not independent custody. Existing
    stale-writer/orphan-lock/torn-record guards remain mandatory. Reopen after
    process interruption. post_commit is a fault-injection hook for tests only.
    """
    def __init__(self, path, *, post_commit=None, max_events=2048):
        need(type(max_events) is int and 1 <= max_events <= 10000, "EVENT_BOUND")
        need(not Path(path).exists() or Path(path).stat().st_size <= max_events*8192, "JOURNAL_SIZE_BOUND")
        self.journal=DurablePositionJournal(path)
        self._states={};self._commands={};self.max_events=max_events
        self.post_commit=post_commit
        for event in self.journal.ledger.events.values():
            need(event.source==SOURCE and event.price is None, "JOURNAL_SCOPE")
            payload=json.loads(event.reason)
            need(set(payload)=={"command","state_sha256"}, "EVENT_FIELDS")
            if event.position_id not in self._states:
                need(event.position_id==self.identity(payload["command"]), "REPLAY_AGGREGATE_IDENTITY")
            state=reduce_state(self._states.get(event.position_id),payload["command"])
            need(digest(state)==payload["state_sha256"] and state["updated_ms"]==event.event_ms==event.received_ms,
                 "REPLAY_STATE_DRIFT")
            self._states[event.position_id]=state
            self._commands[(event.position_id,event.event_id)]=payload["command"]
        need(len(self._commands)<=max_events, "REPLAY_EVENT_BOUND")

    @property
    def states(self):
        return json.loads(canonical(self._states))

    @staticmethod
    def identity(watch_command):
        return "sim:"+digest(watch_command)

    def apply(self, simulation_id, command_id, command):
        need(type(simulation_id) is str and simulation_id.startswith("sim:") and len(simulation_id)<=256, "SIM_ID")
        need(type(command_id) is str and 0 < len(command_id)<=128, "COMMAND_ID")
        key=(simulation_id,command_id)
        frozen=json.loads(canonical(command))
        need(len(canonical(frozen).encode())<=4096, "COMMAND_SIZE_BOUND")
        if key in self._commands:
            need(self._commands[key]==frozen, "COMMAND_CONFLICT")
            return json.loads(canonical(self._states[simulation_id]))
        need(len(self._commands)<self.max_events, "EVENT_CAPACITY")
        prior=self._states.get(simulation_id)
        if prior is None:
            need(simulation_id==self.identity(frozen), "AGGREGATE_IDENTITY")
        state=reduce_state(prior,frozen)
        payload=canonical(dict(command=frozen,state_sha256=digest(state)))
        event=PositionEvent(simulation_id,command_id,
                            "opened" if prior is None else "closed" if state["phase"] in TERMINAL else "quote",
                            state["updated_ms"],state["updated_ms"],SOURCE,reason=payload)
        self.journal.append(event)  # fsync return BEFORE exposing new state
        if self.post_commit:
            self.post_commit()
        self._commands[key]=frozen
        self._states[simulation_id]=state
        return json.loads(canonical(state))
