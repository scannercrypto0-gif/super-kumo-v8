"""
AQL Health Package — G1-WP03
Public API for the operational health snapshot.
"""
from .snapshot import HealthSnapshot, take_snapshot, DEFAULT_LAG_WARN_S, DEFAULT_LAG_CRIT_S

__all__ = [
    "HealthSnapshot",
    "take_snapshot",
    "DEFAULT_LAG_WARN_S",
    "DEFAULT_LAG_CRIT_S",
]
