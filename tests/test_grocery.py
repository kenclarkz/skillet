"""Grocery aggregation unit tests (port of the original TS suite)."""
from app.lib.ingredients import (
    normalize_ingredient_name,
    parse_ingredient_line,
    parse_ingredient_text,
    qty_to_number,
)
from app.lib.grocery import aggregate, format_number, format_quantity, resolve_unit


def test_parse_mixed_number_with_unit():
    ing = parse_ingredient_line('1 1/2 cups all-purpose flour')
    assert ing['qty'] == '1.5'
    assert ing['unit'] == 'cups'
    assert ing['name'] == 'all-purpose flour'


def test_parse_fraction_and_trailing_note():
    ing = parse_ingredient_line('1/2 cup onion, diced')
    assert ing['qty'] == '0.5'
    assert ing['unit'] == 'cup'
    assert ing['name'] == 'onion'
    assert ing['note'] == 'diced'


def test_parse_count_with_adjective_no_unit():
    ing = parse_ingredient_line('2 large eggs')
    assert ing['qty'] == '2'
    assert ing['unit'] is None
    assert ing['name'] == 'large eggs'


def test_parse_no_quantity():
    ing = parse_ingredient_line('salt and pepper to taste')
    assert ing['qty'] is None
    assert ing['unit'] is None
    assert ing['name'] == 'salt and pepper to taste'


def test_parse_parenthetical_size():
    ing = parse_ingredient_line('1 (14 oz) can diced tomatoes')
    assert ing['qty'] == '1'
    assert ing['unit'] == 'can'
    assert ing['name'] == 'diced tomatoes'
    assert ing['note'] == '(14 oz)'


def test_parse_two_word_fluid_ounce():
    ing = parse_ingredient_line('8 fl oz heavy cream')
    assert ing['qty'] == '8'
    assert ing['unit'] == 'fl oz'
    assert ing['name'] == 'heavy cream'


def test_parse_text_block():
    items = parse_ingredient_text('2 tbsp olive oil\n3 cloves garlic, minced\n\n1 lb ground beef')
    assert len(items) == 3
    assert items[1]['name'] == 'garlic'
    assert items[2]['unit'] == 'lb'


def test_normalize_names_match_across_variants():
    assert normalize_ingredient_name('Carrots') == normalize_ingredient_name('carrot')
    assert normalize_ingredient_name('Tomatoes') == normalize_ingredient_name('tomato')
    assert normalize_ingredient_name('All-Purpose Flour') == normalize_ingredient_name('all purpose flour')


def test_qty_parsing():
    assert qty_to_number('2') == 2
    assert qty_to_number('0.5') == 0.5
    assert qty_to_number('1,5') == 1.5
    assert qty_to_number('two') is None
    assert qty_to_number(None) is None


def test_unit_families():
    assert resolve_unit('cups')['family'] == 'volume'
    assert resolve_unit('lb')['family'] == 'weight'
    assert resolve_unit('cloves')['family'] == 'count'
    assert resolve_unit('weirdthing')['family'] == 'unknown'


def _ing(name, qty, unit, rid, title):
    return {'name': name, 'qty': qty, 'unit': unit, 'recipeId': rid, 'recipeTitle': title}


def test_aggregate_merges_same_ingredient():
    items = aggregate([
        _ing('flour', '2', 'cup', 'r1', 'Focaccia'),
        _ing('flour', '1', 'cup', 'r2', 'Bread'),
    ])
    assert len(items) == 1
    assert items[0]['qty'] == 3
    assert items[0]['unit'] == 'cup'
    assert set(items[0]['recipes']) == {'Focaccia', 'Bread'}


def test_aggregate_converts_units_into_display_unit():
    # 1 cup + 8 tbsp => all displayed in cups (most frequent vote)
    items = aggregate([
        _ing('water', '1', 'cup', 'r1', 'A'),
        _ing('water', '1', 'cup', 'r2', 'B'),
        _ing('water', '8', 'tbsp', 'r3', 'C'),
    ])
    assert len(items) == 1
    # 2 cups + 8 tbsp (0.5 cup) = 2.5 cups
    assert abs(items[0]['qty'] - 2.5) < 0.01
    assert items[0]['unit'] == 'cup'


def test_aggregate_pantry_flag():
    items = aggregate([
        _ing('salt', '1', 'tsp', 'r1', 'A'),
        _ing('olive oil', '3', 'tbsp', 'r1', 'A'),
    ], pantry={'salt'})
    by_name = {i['normalized_name']: i for i in items}
    assert by_name['salt']['in_pantry'] is True
    assert by_name['olive oil']['in_pantry'] is False
    # pantry items sort last
    assert items[-1]['normalized_name'] == 'salt'


def test_aggregate_missing_qty_marked():
    items = aggregate([
        _ing('pepper', None, None, 'r1', 'A'),
    ])
    assert items[0]['qty'] is None
    assert items[0]['missing_qty'] is True


def test_aggregate_sort_order():
    items = aggregate([
        _ing('zucchini', '1', 'each', 'r1', 'A'),
        _ing('apple', '2', 'each', 'r1', 'A'),
        _ing('vinegar', '1', 'tbsp', 'r1', 'A'),
    ])
    names = [i['name'] for i in items]
    assert names == sorted(names, key=str.lower)


def test_format_number_fractions():
    assert format_number(2) == '2'
    assert format_number(1.5) == '1 1/2'
    assert format_number(0.25) == '1/4'
    assert format_number(2.6667) == '2 2/3'


def test_format_quantity_pluralization():
    assert format_quantity({'qty': 2, 'unit': 'cup'}) == '2 cups'
    assert format_quantity({'qty': 1, 'unit': 'cup'}) == '1 cup'
    assert format_quantity({'qty': 1.5, 'unit': 'tbsp'}) == '1 1/2 tbsp'
    assert format_quantity({'qty': None, 'unit': '', 'missing_qty': True}) == 'to taste'


def test_unknown_units_do_not_convert():
    items = aggregate([
        _ing('tortillas', '8', 'each', 'r1', 'A'),
        _ing('tortillas', '4', 'each', 'r2', 'B'),
    ])
    assert items[0]['qty'] == 12
