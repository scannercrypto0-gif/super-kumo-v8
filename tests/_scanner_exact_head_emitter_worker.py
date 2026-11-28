"""Isolated pinned Scanner producer; synthetic fixture only, no network/trades."""
import json
import os
import sys
from pathlib import Path

root = os.environ.get("AQL_PINNED_SCANNER_ROOT")
if not root or not (Path(root)/"tools/scanner_strategy_f/g1_g2_explicit_opportunity.py").is_file():
    raise RuntimeError("EXACT_SCANNER_SOURCE_REQUIRED")
sys.path.insert(0,str(Path(root).resolve()))

from src.aql.models.bar import MarketBar
from src.aql.journal.durable_journal import DurableJournal
from src.aql.storage.operational_store import OperationalStore
from tools.scanner_strategy_f.g1_g2_explicit_opportunity import (
    emit_explicit_opportunity, explicit_test_decision, test_only_policy,
    verify_opportunity,
)
req=json.loads(sys.stdin.read())
bar=MarketBar.from_dict(req["bar"])
journal=DurableJournal(req["journal"])
store=OperationalStore(req["store"])
decision=explicit_test_decision(
    symbol=bar.symbol,interval=bar.interval,bar_close_ms=bar.bar_close,
    decision_cutoff_ms=req["decision_ms"],strategy_id="explicit_real_scanner_test",
    strategy_version="1",strategy_definition_sha256="a"*64,
    strategy_config_sha256="b"*64,strategy_evaluator_sha256="c"*64,
    decision_state="ENTRY_SIGNAL",
)
event=emit_explicit_opportunity(
    bar=bar,journal=journal,store=store,decision=decision,
    policy=test_only_policy(),decision_ms=req["decision_ms"],
)
verify_opportunity(event)
sys.stdout.write(json.dumps(event,sort_keys=True))
