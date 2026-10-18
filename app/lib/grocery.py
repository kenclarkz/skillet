"""Grocery-list aggregation: unit resolution, merging, and formatting.

Ported from the original Skillet app so ingredient math stays identical.
"""
from __future__ import annotations

import re
from typing import Optional

from app.lib.ingredients import normalize_ingredient_name, qty_to_number

# family: volume (base ml) | weight (base g) | count | unknown
UNIT_DEFS = {
    # volume
    'ml': ('ml', 'volume', 1), 'milliliter': ('ml', 'volume', 1), 'millilitre': ('ml', 'volume', 1),
    'l': ('l', 'volume', 1000), 'liter': ('l', 'volume', 1000), 'litre': ('l', 'volume', 1000),
    'tsp': ('tsp', 'volume', 4.92892), 'teaspoon': ('tsp', 'volume', 4.92892),
    'teaspoons': ('tsp', 'volume', 4.92892),
    'tbsp': ('tbsp', 'volume', 14.7868), 'tablespoon': ('tbsp', 'volume', 14.7868),
    'tablespoons': ('tbsp', 'volume', 14.7868),
    'fl oz': ('fl oz', 'volume', 29.5735), 'floz': ('fl oz', 'volume', 29.5735),
    'fluid ounce': ('fl oz', 'volume', 29.5735), 'fluid ounces': ('fl oz', 'volume', 29.5735),
    'cup': ('cup', 'volume', 236.588), 'cups': ('cup', 'volume', 236.588),
    'pint': ('pint', 'volume', 473.176), 'pints': ('pint', 'volume', 473.176),
    'quart': ('quart', 'volume', 946.353), 'quarts': ('quart', 'volume', 946.353),
    'gallon': ('gallon', 'volume', 3785.41), 'gallons': ('gallon', 'volume', 3785.41),
    # weight
    'g': ('g', 'weight', 1), 'gram': ('g', 'weight', 1), 'grams': ('g', 'weight', 1),
    'kg': ('kg', 'weight', 1000), 'kilogram': ('kg', 'weight', 1000), 'kilograms': ('kg', 'weight', 1000),
    'oz': ('oz', 'weight', 28.3495), 'ounce': ('oz', 'weight', 28.3495), 'ounces': ('oz', 'weight', 28.3495),
    'lb': ('lb', 'weight', 453.592), 'lbs': ('lb', 'weight', 453.592),
    'pound': ('lb', 'weight', 453.592), 'pounds': ('lb', 'weight', 453.592),
    # count
    'each': ('', 'count', 1), 'clove': ('clove', 'count', 1), 'cloves': ('clove', 'count', 1),
    'can': ('can', 'count', 1), 'cans': ('can', 'count', 1),
    'package': ('package', 'count', 1), 'packages': ('package', 'count', 1), 'pkg': ('package', 'count', 1),
    'bunch': ('bunch', 'count', 1), 'bunches': ('bunch', 'count', 1),
    'head': ('head', 'count', 1), 'heads': ('head', 'count', 1),
    'stick': ('stick', 'count', 1), 'sticks': ('stick', 'count', 1),
    'slice': ('slice', 'count', 1), 'slices': ('slice', 'count', 1),
    'piece': ('piece', 'count', 1), 'pieces': ('piece', 'count', 1),
    'pinch': ('pinch', 'count', 1), 'pinches': ('pinch', 'count', 1),
    'dash': ('dash', 'count', 1), 'dashes': ('dash', 'count', 1),
    'sprig': ('sprig', 'count', 1), 'sprigs': ('sprig', 'count', 1),
}


def resolve_unit(raw: Optional[str]) -> dict:
    if not raw:
        return {'canonical': '', 'family': 'count', 'factor': 1.0}
    key = re.sub(r"\s+", " ", raw.strip().lower().replace('.', ''))
    defn = UNIT_DEFS.get(key)
    if defn:
        canonical, family, factor = defn
        return {'canonical': canonical, 'family': family, 'factor': factor}
    return {'canonical': raw.strip().lower(), 'family': 'unknown', 'factor': 1.0}


def to_base(value: float, unit: Optional[str]) -> dict:
    u = resolve_unit(unit)
    return {'base': value * u['factor'], 'family': u['family']}


def from_base(base: float, unit: Optional[str]) -> float:
    u = resolve_unit(unit)
    return base / u['factor']


def aggregate(ingredients: list, pantry: Optional[set] = None) -> list:
    """Merge structured ingredients into a combined grocery list."""
    pantry = pantry or set()
    drafts: dict = {}

    for ing in ingredients:
        raw_name = ing.get('name') or ''
        # Support both structured {qty, unit, name} and raw lines {raw}
        if 'raw' in ing:
            from app.lib.ingredients import parse_ingredient_line
            parsed = parse_ingredient_line(ing['raw'])
            raw_name = parsed['name']
            qty = parsed['qty']
            unit = parsed['unit']
        else:
            qty = ing.get('qty')
            unit = ing.get('unit') or ''

        normalized = normalize_ingredient_name(raw_name)
        if not normalized:
            continue

        family = resolve_unit(unit)['family']
        unit_key = ''
        u = resolve_unit(unit)
        if family == 'unknown' and u['canonical']:
            unit_key = f"|{u['canonical']}"
        key = f"{normalized}|{family}{unit_key}"

        if key not in drafts:
            drafts[key] = {
                'name': raw_name.strip(),
                'normalized_name': normalized,
                'family': family,
                'base_total': 0.0,
                'has_numeric': False,
                'has_non_numeric': False,
                'unit_votes': {},
                'recipe_ids': set(),
                'recipes': {},
            }
        d = drafts[key]
        d['recipe_ids'].add(ing.get('recipeId'))
        d['recipes'][ing.get('recipeId')] = ing.get('recipeTitle')
        if unit:
            d['unit_votes'][unit] = d['unit_votes'].get(unit, 0) + 1

        num = qty_to_number(qty) if qty else None
        if num is None:
            d['has_non_numeric'] = True
        else:
            d['has_numeric'] = True
            scale = ing.get('scale', 1)
            d['base_total'] += to_base(num * scale, unit)['base']

    items = []
    for d in drafts.values():
        display_unit = ''
        best_votes = -1
        for unit, votes in d['unit_votes'].items():
            if votes > best_votes:
                best_votes = votes
                display_unit = unit

        qty_out: Optional[float] = None
        if d['has_numeric']:
            if d['family'] == 'unknown':
                qty_out = d['base_total']
            else:
                qty_out = from_base(d['base_total'], display_unit)
            if abs(qty_out - round(qty_out)) < 0.01:
                qty_out = round(qty_out, 3)
            else:
                qty_out = round(qty_out, 4)

        canonical_unit = (
            display_unit if d['family'] == 'unknown' else resolve_unit(display_unit)['canonical']
        )

        items.append({
            'name': d['name'],
            'normalized_name': d['normalized_name'],
            'qty': qty_out,
            'unit': canonical_unit,
            'family': d['family'],
            'recipe_ids': sorted(x for x in d['recipe_ids'] if x),
            'recipes': sorted({v for v in d['recipes'].values() if v}),
            'in_pantry': d['normalized_name'] in pantry,
            'missing_qty': d['has_non_numeric'],
            'split_note': 'partial quantity' if (d['has_non_numeric'] and d['has_numeric']) else None,
        })

    items.sort(key=lambda a: (a['in_pantry'], a['name'].lower()))
    return items


FRACTIONS = [
    (1 / 8, '1/8'), (1 / 6, '1/6'), (1 / 5, '1/5'), (1 / 4, '1/4'),
    (1 / 3, '1/3'), (3 / 8, '3/8'), (1 / 2, '1/2'), (5 / 8, '5/8'),
    (2 / 3, '2/3'), (3 / 4, '3/4'), (5 / 6, '5/6'), (7 / 8, '7/8'),
]


def format_number(n: float) -> str:
    if float(n).is_integer():
        return str(int(n))
    whole = int(n // 1)
    frac = n - whole
    for value, label in FRACTIONS:
        if abs(frac - value) < 0.025:
            return f"{whole} {label}" if whole > 0 else label
    return str(round(n, 2))


def format_quantity(item: dict) -> str:
    qty = item.get('qty')
    unit = item.get('unit') or ''
    missing = item.get('missing_qty')
    if qty is None:
        return 'to taste' if missing else ''
    q = format_number(qty)
    if not unit:
        return q
    plural_ok = qty != 1 and not unit.endswith('s') and unit not in ('lb', 'oz', 'fl oz', 'tbsp', 'tsp')
    suffix = 's' if plural_ok else ''
    return f"{q} {unit}{suffix}".strip()
