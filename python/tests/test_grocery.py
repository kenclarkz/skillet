"""Grocery aggregation, formatting, and pantry behavior."""

import pytest

from skillet.grocery import aggregate_groceries, format_number, format_quantity


def ing(name, qty=None, unit=None, recipe_id="r1", title="Recipe One", scale=1):
    return {
        "qty": qty, "unit": unit, "name": name, "note": None,
        "recipeId": recipe_id, "recipeTitle": title, "scale": scale,
    }


def test_merges_same_ingredient_across_recipes():
    items = aggregate_groceries([
        ing("flour", "2", "cups", "r1", "Bread"),
        ing("flour", "1", "cup", "r2", "Pizza"),
    ])
    assert len(items) == 1
    assert items[0]["qty"] == pytest.approx(3)
    assert items[0]["unit"] == "cup"
    assert {r["id"] for r in items[0]["recipes"]} == {"r1", "r2"}


def test_converts_across_compatible_units():
    # More votes pick the display unit: ml wins 2-1 over cup.
    items = aggregate_groceries([
        ing("milk", "1", "cup", "r1"),
        ing("milk", "250", "ml", "r2"),
        ing("milk", "100", "ml", "r3"),
    ])
    assert len(items) == 1
    assert items[0]["unit"] == "ml"
    assert items[0]["qty"] == pytest.approx(586.588, abs=0.01)


def test_does_not_merge_across_families():
    items = aggregate_groceries([
        ing("flour", "2", "cups"),
        ing("flour", "100", "g"),
    ])
    assert len(items) == 2


def test_does_not_merge_unknown_unit_variants():
    items = aggregate_groceries([
        ing("glugs olive oil", "1", "glugs"),
        ing("glugs olive oil", "2", "splashes"),
    ])
    assert len(items) == 2


def test_respects_scale():
    items = aggregate_groceries([ing("sugar", "1", "cup", scale=2)])
    assert items[0]["qty"] == pytest.approx(2)


def test_pantry_staples_sink_to_bottom_and_flag():
    items = aggregate_groceries([
        ing("salt", "1", "tsp"),
        ing("chicken", "2", "lb"),
    ], pantry={"salt"})
    assert items[-1]["normalized_name"] == "salt"
    assert items[-1]["in_pantry"] is True
    assert items[0]["in_pantry"] is False


def test_non_numeric_qty_marks_missing():
    items = aggregate_groceries([ing("black pepper", "to taste", None)])
    assert items[0]["qty"] is None
    assert items[0]["missing_qty"] is True


def test_partial_quantity_split_note():
    items = aggregate_groceries([
        ing("herbs", "2", "tbsp"),
        ing("herbs", None, "tbsp"),
    ])
    assert items[0]["split_note"] == "partial quantity"
    assert items[0]["qty"] == pytest.approx(2)


def test_format_quantity_pluralizes():
    assert format_quantity({"qty": 2, "unit": "cup", "missing_qty": False}) == "2 cups"
    assert format_quantity({"qty": 1, "unit": "cup", "missing_qty": False}) == "1 cup"
    assert format_quantity({"qty": 1.5, "unit": "lb", "missing_qty": False}) == "1 1/2 lb"


def test_format_quantity_to_taste():
    assert format_quantity({"qty": None, "unit": "", "missing_qty": True}) == "to taste"


def test_format_number_fractions():
    assert format_number(1.5) == "1 1/2"
    assert format_number(0.25) == "1/4"
    assert format_number(3) == "3"
    assert format_number(1 / 3) == "1/3"
