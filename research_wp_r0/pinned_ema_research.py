"""P0 bounded archive-to-development replay entry point.

Requires a separately pinned archive digest and a frozen plan. The source is
retrospective, NOT confirmed PIT custody. Never opens reserved OOS.
"""
import hashlib
import json

from .ema_first_backtest import frozen_ema_plan
from .ema_development_replay import replay_ema_development
from .retrospective_kline_intake import inspect_binance_spot_zip


def run_pinned_ema_development(path, *, archive_sha256, source_reference,
                               split_cutoff_ms, expected_plan_sha256, fee_bps=10, slippage_bps=5):
    plan, plan_digest = frozen_ema_plan(
        archive_sha256=archive_sha256, source_reference=source_reference,
        split_cutoff_ms=split_cutoff_ms, fee_bps=fee_bps,
        slippage_bps=slippage_bps)
    if plan_digest != expected_plan_sha256:
        raise ValueError("Frozen plan commitment mismatch")
    receipt, bars = inspect_binance_spot_zip(path,
                                             expected_sha256=archive_sha256)
    if receipt.symbol != "BTCUSDT" or receipt.interval_ms != 60000:
        raise ValueError("Unexpected archive market")
    if receipt.gap_count:
        raise ValueError("Archive has gaps: refuse execution")
    if not (receipt.first_open_ms < split_cutoff_ms <=
            receipt.last_open_ms + receipt.interval_ms):
        raise ValueError("Split must be inside or immediately after archive")
    report = replay_ema_development(bars, split_cutoff_ms=split_cutoff_ms,
                                    fee_bps=fee_bps, slippage_bps=slippage_bps)
    # Bind snapshots to the frozen input/config identity; serialized bytes and
    # retained report digests are tamper evidence, not external custody.
    for event in report["opportunities"]:
        snapshot = event["decision_snapshot"]
        snapshot["plan_sha256"] = plan_digest
        snapshot["archive_sha256"] = archive_sha256
        snapshot["source_reference"] = source_reference
        event.pop("snapshot_sha256")
        event["snapshot_sha256"] = hashlib.sha256(json.dumps(snapshot, sort_keys=True,
            separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    report.pop("report_sha256")
    report["report_sha256"] = hashlib.sha256(json.dumps(report, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    payload = {
        "schema_version": "sf-ema-pinned-development-1",
        "plan": plan,
        "plan_sha256": plan_digest,
        "archive_receipt": vars(receipt),
        "development_report": report,
        "oos": "LOCKED_NOT_EVALUATED",
        "independent_custody": "NOT_VERIFIED",
    }
    payload["replay_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"),
                   allow_nan=False).encode()).hexdigest()
    return payload
