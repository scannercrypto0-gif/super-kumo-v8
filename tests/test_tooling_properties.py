"""Property tests of real ATLAS archive contracts; no mock implementations."""

from pathlib import Path
import tempfile

import pytest
from hypothesis import given, settings, strategies as st

from aql.archive.contracts import canonical, digest, parse
from aql.archive.local import child


@settings(max_examples=80, deadline=None)
@given(st.recursive(
    st.one_of(st.none(), st.booleans(), st.integers(min_value=-(2**63), max_value=2**63 - 1), st.text(max_size=60)),
    lambda inner: st.one_of(st.lists(inner, max_size=8), st.dictionaries(st.text(min_size=1, max_size=20), inner, max_size=8)),
    max_leaves=20,
))
def test_canonical_roundtrip_preserves_real_archive_digest(value):
    encoded = canonical(value)
    assert parse(encoded) == value
    assert digest(parse(encoded)) == digest(value)


@settings(max_examples=80, deadline=None)
@given(st.sampled_from(["../escape", "a/../escape", "/absolute", "a\\\\escape", "C:drive", "", "a//b", "a/./b"]))
def test_archive_child_rejects_escape_and_ambiguous_paths(name: str):
    with tempfile.TemporaryDirectory() as root:
        with pytest.raises((ValueError, OSError)):
            child(Path(root), name)


@settings(max_examples=80, deadline=None)
@given(st.lists(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=12), min_size=1, max_size=5))
def test_archive_child_stays_inside_root(parts):
    with tempfile.TemporaryDirectory() as root:
        base = Path(root)
        name = "/".join(parts)
        resolved = child(base, name)
        assert resolved.relative_to(base) == Path(*parts)


@settings(max_examples=80, deadline=None)
@given(
    decision_ms=st.integers(min_value=1, max_value=253402300799998),
    future_delta=st.integers(min_value=1, max_value=100000),
)
def test_pit_context_rejects_future_available_feature(decision_ms, future_delta):
    """A real PIT contract must reject evidence first available after decision time."""
    from aql.archive.contracts import FEATURES, decision_context

    unavailable = {"value": None, "source": None, "version": None,
                   "event_ms": None, "receipt_ms": None, "available_ms": None,
                   "freshness_ms": None, "status": "UNAVAILABLE"}
    features = {name: dict(unavailable) for name in FEATURES}
    future_ms = decision_ms + future_delta
    features["btc_regime"] = {
        "value": "UP", "source": "synthetic", "version": "v1",
        "event_ms": decision_ms, "receipt_ms": decision_ms,
        "available_ms": future_ms, "freshness_ms": 0, "status": "AVAILABLE",
    }
    with pytest.raises(ValueError):
        decision_context(context_id="pit-probe", decision_ms=decision_ms,
                         outcome="REJECTED", strategy_version="v1",
                         policy_version="v1", features=features)
