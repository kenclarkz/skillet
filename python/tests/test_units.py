"""Unit resolution and conversion — port of src/lib/grocery/units.test.ts."""

import pytest

from skillet.units import family_of, from_base, resolve_unit, to_base


def test_resolve_known_unit():
    u = resolve_unit("cups")
    assert u["canonical"] == "cup"
    assert u["family"] == "volume"


def test_resolve_case_and_dot_insensitive():
    assert resolve_unit("Tbsp.")["canonical"] == "tbsp"
    assert resolve_unit("OUNCE")["canonical"] == "oz"


def test_resolve_empty_is_count():
    u = resolve_unit(None)
    assert u["family"] == "count"
    assert u["factor"] == 1


def test_resolve_unknown_family():
    u = resolve_unit("glugs")
    assert u["family"] == "unknown"
    assert u["canonical"] == "glugs"


def test_volume_conversion_cup_to_ml():
    base = to_base(1, "cup")["base"]
    assert base == pytest.approx(236.588, rel=1e-4)


def test_weight_conversion_lb_to_g():
    assert to_base(1, "lb")["base"] == pytest.approx(453.592, rel=1e-4)


def test_round_trip():
    base = to_base(2.5, "tbsp")["base"]
    assert from_base(base, "tbsp") == pytest.approx(2.5)


def test_cross_unit_within_family():
    base = to_base(1, "cup")["base"]
    assert from_base(base, "ml") == pytest.approx(236.588, rel=1e-4)


def test_family_of():
    assert family_of("kg") == "weight"
    assert family_of("gallon") == "volume"
    assert family_of("cloves") == "count"
