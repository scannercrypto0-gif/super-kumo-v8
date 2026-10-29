"""Synthetic-only B0 candidate adapter. This module cannot authorize a study."""
from dataclasses import dataclass
from research_wp_r0.historical_dev_exits_v1 import Config, replay, verify_receipt

ENGINE_PIN = "20928693f30b1730f0693a293bbf4a1f8ab21c88"
POLICY_ID = "DEV-B0-SYNTHETIC-CANDIDATE-1"

class ExecutionDenied(PermissionError):
    pass

@dataclass(frozen=True)
class Candidate:
    policy_id: str
    engine_pin: str
    receipt: dict

def build_synthetic_candidate(bars, source, *, config=None):
    """Build a hypothetical receipt from explicitly synthetic inputs only.

    The caller must supply a source tagged as synthetic; never admit real files
    or interpret a GitHub comment, flag, or hash as study authorization.
    """
    if not isinstance(source, dict) or source.get("version") != "synthetic-b0":
        raise ExecutionDenied("SYNTHETIC_SOURCE_ONLY")
    if config is None:
        config = Config(warmup_bars=252)
    if not isinstance(config, Config) or config.warmup_bars != 252:
        raise ExecutionDenied("EXPLICIT_252_WARMUP_REQUIRED")
    if not isinstance(bars, list) or not all(isinstance(b, dict) and b.get("modeled_quote") is True for b in bars):
        raise ExecutionDenied("SYNTHETIC_QUOTE_REQUIRED")
    receipt = replay(bars, source=source, config=config)
    if not verify_receipt(receipt):
        raise ExecutionDenied("RECEIPT_VERIFICATION_FAILED")
    return Candidate(POLICY_ID, ENGINE_PIN, receipt)

def run_study(*args, **kwargs):
    raise ExecutionDenied("STUDY_RUN_REQUIRES_SEPARATE_AUTHENTICATED_ADMISSION")
