"""Property tests of real ATLAS archive contracts; no mock implementations."""

from pathlib import Path

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
def test_archive_child_rejects_escape_and_ambiguous_paths(tmp_path: Path, name: str):
    with pytest.raises((ValueError, OSError)):
        child(tmp_path, name)


@settings(max_examples=80, deadline=None)
@given(st.lists(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=12), min_size=1, max_size=5))
def test_archive_child_stays_inside_root(tmp_path: Path, parts):
    name = "/".join(parts)
    resolved = child(tmp_path, name)
    assert resolved.relative_to(tmp_path) == Path(*parts)
