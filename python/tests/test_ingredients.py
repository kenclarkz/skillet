"""Ingredient line parsing — port of the src/lib/ingredients.test.ts suite."""

from skillet.ingredients import (
    normalize_ingredient_name,
    normalize_qty,
    parse_ingredient_line,
    parse_ingredient_text,
    qty_to_number,
)


def test_parses_qty_unit_name():
    assert parse_ingredient_line("2 cups flour") == {
        "qty": "2", "unit": "cups", "name": "flour", "note": None,
    }


def test_parses_fraction():
    ing = parse_ingredient_line("1/2 cup sugar")
    assert ing["qty"] == "0.5"
    assert ing["unit"] == "cup"
    assert ing["name"] == "sugar"


def test_parses_mixed_fraction():
    ing = parse_ingredient_line("1 1/2 cups milk")
    assert ing["qty"] == "1.5"
    assert ing["unit"] == "cups"
    assert ing["name"] == "milk"


def test_parses_decimal_qty():
    ing = parse_ingredient_line("1.5 tsp salt")
    assert ing["qty"] == "1.5"
    assert ing["unit"] == "tsp"
    assert ing["name"] == "salt"


def test_parses_prep_note_after_comma():
    ing = parse_ingredient_line("1 onion, diced")
    assert ing["qty"] == "1"
    assert ing["name"] == "onion"
    assert ing["note"] == "diced"


def test_parses_canned_goods_with_size():
    ing = parse_ingredient_line("1 (14 oz) can diced tomatoes")
    assert ing["qty"] == "1"
    assert ing["unit"] == "can"
    assert "(14 oz)" in (ing["note"] or "")
    assert "tomatoes" in ing["name"]


def test_parses_two_word_fluid_oz():
    ing = parse_ingredient_line("2 fl oz vanilla extract")
    assert ing["unit"] == "fl oz"
    assert ing["name"] == "vanilla extract"


def test_name_only_line():
    ing = parse_ingredient_line("Salt and pepper to taste")
    assert ing["qty"] is None
    assert ing["unit"] is None
    assert ing["name"] == "Salt and pepper to taste"


def test_drops_trailing_size_descriptor_from_name():
    ing = parse_ingredient_line("1 lb chicken thighs (or as needed)")
    assert ing["name"] == "chicken thighs"
    assert "(or as needed)" not in ing["name"]


def test_parse_text_splits_lines_and_skips_blank():
    parsed = parse_ingredient_text("2 cups flour\n\n1 tsp salt\n")
    assert [p["name"] for p in parsed] == ["flour", "salt"]


def test_normalize_qty():
    assert normalize_qty("1 1/4") == "1.25"
    assert normalize_qty("3/4") == "0.75"
    assert normalize_qty("2") == "2"


def test_normalize_name_singularizes():
    assert normalize_ingredient_name("Diced Tomatoes") == "diced tomato"
    assert normalize_ingredient_name("baby spinach") == "baby spinach"
    assert normalize_ingredient_name("chickpeas!") == "chickpea"


def test_qty_to_number():
    assert qty_to_number("1.5") == 1.5
    assert qty_to_number("fresh") is None
    assert qty_to_number(None) is None
