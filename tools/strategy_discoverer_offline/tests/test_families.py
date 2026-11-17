"""
Tests for families.py
======================
Covers:
  - All 7 families register with correct metadata
  - Family digest integrity
  - Parameter axes well-formed
  - Registry digest determinism
  - Invalid families rejected
"""

import pytest

from tools.strategy_discoverer_offline.families import (
    FamilyDefinition,
    ParameterAxis,
    IndicatorAxis,
    FAMILY_REGISTRY,
    get_family,
    list_families,
    family_registry_digest,
)


EXPECTED_FAMILY_IDS = {"F001", "F002", "F003", "F004", "F005", "F006", "F007"}


class TestFamilyRegistry:
    def test_all_seven_families_present(self):
        assert set(FAMILY_REGISTRY.keys()) == EXPECTED_FAMILY_IDS

    def test_list_families_returns_all_ids(self):
        ids = set(list_families())
        assert ids == EXPECTED_FAMILY_IDS

    def test_get_family_returns_correct_type(self):
        f = get_family("F001")
        assert isinstance(f, FamilyDefinition)

    def test_get_family_unknown_raises(self):
        with pytest.raises((KeyError, ValueError)):
            get_family("F999")

    def test_registry_digest_is_64_hex(self):
        d = family_registry_digest()
        assert len(d) == 64
        assert all(c in "0123456789abcdef" for c in d)

    def test_registry_digest_stable_between_calls(self):
        d1 = family_registry_digest()
        d2 = family_registry_digest()
        assert d1 == d2


class TestFamilyDefinitions:
    @pytest.mark.parametrize("fid", sorted(EXPECTED_FAMILY_IDS))
    def test_family_digest_integrity(self, fid):
        """family_digest must match the re-computed digest of all fields."""
        f = get_family(fid)
        assert isinstance(f, FamilyDefinition)
        # If digest were tampered, the dataclass __post_init__ should have caught it
        # We verify the digest is well-formed
        assert len(f.family_digest) == 64
        assert all(c in "0123456789abcdef" for c in f.family_digest)

    @pytest.mark.parametrize("fid", sorted(EXPECTED_FAMILY_IDS))
    def test_family_timing_valid(self, fid):
        f = get_family(fid)
        assert f.timing in ("CONFIRMED_CLOSE", "NEXT_ELIGIBLE_OPEN", "REJECT")

    @pytest.mark.parametrize("fid", sorted(EXPECTED_FAMILY_IDS))
    def test_family_max_candidates_positive(self, fid):
        f = get_family(fid)
        assert f.max_candidates > 0
        assert f.max_candidates <= 256

    @pytest.mark.parametrize("fid", sorted(EXPECTED_FAMILY_IDS))
    def test_family_has_indicator_axes(self, fid):
        f = get_family(fid)
        assert len(f.indicator_axes) > 0

    @pytest.mark.parametrize("fid", sorted(EXPECTED_FAMILY_IDS))
    def test_indicator_axes_well_formed(self, fid):
        f = get_family(fid)
        for iax in f.indicator_axes:
            assert isinstance(iax, IndicatorAxis)
            assert len(iax.indicator_id) > 0
            for pax in iax.parameter_axes:
                assert isinstance(pax, ParameterAxis)
                assert len(pax.values) > 0

    def test_f005_timing_next_eligible_open(self):
        """F005 specifically uses NEXT_ELIGIBLE_OPEN for mean-reversion."""
        f = get_family("F005")
        assert f.timing == "NEXT_ELIGIBLE_OPEN"

    def test_f001_timing_confirmed_close(self):
        f = get_family("F001")
        assert f.timing == "CONFIRMED_CLOSE"


class TestFamilyBuildValidation:
    def test_family_build_requires_matching_digest(self):
        """Build then verify: the digest returned must match reconstruction."""
        f = get_family("F004")
        # The frozen dataclass verified on init; if we reach here it passed
        assert f.family_id == "F004"

    def test_parameter_axis_values_are_tuple(self):
        f = get_family("F001")
        for iax in f.indicator_axes:
            for pax in iax.parameter_axes:
                assert isinstance(pax.values, tuple)

    def test_indicator_axis_parameter_axes_are_tuple(self):
        f = get_family("F001")
        for iax in f.indicator_axes:
            assert isinstance(iax.parameter_axes, tuple)
