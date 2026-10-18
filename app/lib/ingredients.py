"""Parsing and normalization for free-form recipe ingredient lines.

Faithful Python port of the original Skillet TypeScript helpers so that
grocery-list merging behaves the same way it did in the Next.js app.
"""
from __future__ import annotations

import re
from typing import Optional

QTY_PATTERN = re.compile(r"^(\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?|\.(?:\d+)?)\s*")
UNIT_PATTERN = re.compile(r"^([a-zA-Z][a-zA-Z.]*)\s+")

KNOWN_UNITS = {
    'cup', 'cups', 'tsp', 'teaspoon', 'teaspoons', 'tbsp', 'tablespoon', 'tablespoons',
    'oz', 'ounce', 'ounces', 'lb', 'lbs', 'pound', 'pounds', 'g', 'gram', 'grams',
    'kg', 'kilogram', 'kilograms', 'ml', 'milliliter', 'milliliters', 'l', 'liter',
    'liters', 'clove', 'cloves', 'can', 'cans', 'package', 'packages', 'pkg',
    'bunch', 'bunches', 'head', 'heads', 'stick', 'sticks', 'slice', 'slices',
    'piece', 'pieces', 'pinch', 'pinches', 'dash', 'dashes', 'sprig', 'sprigs',
    'fl', 'fluid', 'pint', 'pints', 'quart', 'quarts', 'gallon', 'gallons',
}


def normalize_qty(raw: str) -> str:
    cleaned = raw.strip().replace(',', '.')
    mixed = re.match(r"^(\d+)\s+(\d+)/(\d+)$", cleaned)
    if mixed:
        whole = int(mixed.group(1))
        num = int(mixed.group(2))
        den = int(mixed.group(3))
        if den != 0:
            return str(whole + num / den)
    frac = re.match(r"^(\d+)/(\d+)$", cleaned)
    if frac:
        num = int(frac.group(1))
        den = int(frac.group(2))
        if den != 0:
            return str(num / den)
    return cleaned


def parse_ingredient_line(line: str) -> dict:
    rest = line.strip()
    qty: Optional[str] = None
    unit: Optional[str] = None
    note: Optional[str] = None

    prep_note: Optional[str] = None
    comma_idx = rest.find(',')
    if comma_idx > -1:
        prep_note = rest[comma_idx + 1:].strip() or None
        rest = rest[:comma_idx].strip()

    qty_match = QTY_PATTERN.match(rest)
    if qty_match:
        qty = normalize_qty(qty_match.group(1))
        rest = rest[qty_match.end():].strip()

    paren_match = re.match(r"^\(([^)]+)\)\s*", rest)
    if paren_match:
        inner = paren_match.group(1)
        inner_qty = QTY_PATTERN.match(inner)
        if inner_qty and not qty:
            qty = normalize_qty(inner_qty.group(1))
        rest = rest[paren_match.end():].strip()
        note = f"{note} ({inner})" if note else f"({inner})"

    unit_match = UNIT_PATTERN.match(rest)
    if unit_match:
        candidate = unit_match.group(1).lower().rstrip('.')
        if candidate in KNOWN_UNITS:
            two_word = re.match(r"^(fl|fluid)\s+(oz|ounce|ounces)\s+", rest, re.I)
            if two_word:
                unit = f"{two_word.group(1).lower()} {two_word.group(2).lower().rstrip('.')}"
                rest = rest[two_word.end():].strip()
            else:
                unit = candidate
                rest = rest[unit_match.end():].strip()

    name = re.sub(r"\s*\([^)]*\)\s*$", "", rest).strip()

    if prep_note:
        note = f"{note}, {prep_note}" if note else prep_note

    if not qty and not unit and not name:
        return {'qty': None, 'unit': None, 'name': line.strip(), 'note': None}

    return {
        'qty': qty,
        'unit': unit,
        'name': name or line.strip(),
        'note': note,
    }


def parse_ingredient_text(text: str) -> list:
    return [
        parse_ingredient_line(line)
        for line in (text or '').split('\n')
        if line.strip()
    ]


def normalize_ingredient_name(name: str) -> str:
    if not name:
        return ''
    s = re.sub(r"[^a-z0-9\s]", " ", name.lower())
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"ies$", "y", s)
    s = re.sub(r"oes$", "o", s)
    s = re.sub(r"sses$", "ss", s)
    s = re.sub(r"s$", "", s)
    return s


def qty_to_number(qty: Optional[str]) -> Optional[float]:
    if not qty:
        return None
    try:
        n = float(qty.replace(',', '.'))
    except ValueError:
        return None
    return n if n == n and n not in (float('inf'), float('-inf')) else None
