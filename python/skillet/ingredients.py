"""Free-form ingredient parsing — port of src/lib/ingredients.ts."""

from __future__ import annotations

import re
from typing import Any

QTY_PATTERN = re.compile(r"^(\d+\s+\d+\/\d+|\d+\/\d+|\d+(?:[.,]\d+)?|\.(?:\d+)?)\s*")
UNIT_PATTERN = re.compile(r"^([a-zA-Z][a-zA-Z.]*)\s+")

KNOWN_UNITS = {
    "cup", "cups", "tsp", "teaspoon", "teaspoons", "tbsp", "tablespoon", "tablespoons",
    "oz", "ounce", "ounces", "lb", "lbs", "pound", "pounds", "g", "gram", "grams",
    "kg", "kilogram", "kilograms", "ml", "milliliter", "milliliters", "l", "liter",
    "liters", "clove", "cloves", "can", "cans", "package", "packages", "pkg",
    "bunch", "bunches", "head", "heads", "stick", "sticks", "slice", "slices",
    "piece", "pieces", "pinch", "pinches", "dash", "dashes", "sprig", "sprigs",
    "fl", "fluid", "pint", "pints", "quart", "quarts", "gallon", "gallons",
}


def normalize_qty(raw: str) -> str:
    """Normalize a fraction or decimal quantity string to a canonical decimal string."""
    cleaned = raw.strip().replace(",", ".")
    mixed = re.match(r"^(\d+)\s+(\d+)\/(\d+)$", cleaned)
    if mixed:
        whole, num, den = int(mixed.group(1)), int(mixed.group(2)), int(mixed.group(3))
        if den != 0:
            return _num_str(whole + num / den)
    frac = re.match(r"^(\d+)\/(\d+)$", cleaned)
    if frac:
        num, den = int(frac.group(1)), int(frac.group(2))
        if den != 0:
            return _num_str(num / den)
    return cleaned


def _num_str(n: float) -> str:
    """Match JS String(number) for the values we produce (no trailing .0 for ints)."""
    if n == int(n):
        return str(int(n))
    return repr(n)


def parse_ingredient_line(line: str) -> dict[str, Any]:
    """Parse a single ingredient line into {qty, unit, name, note}."""
    rest = line.strip()
    qty: str | None = None
    unit: str | None = None
    note: str | None = None

    # Split off trailing prep notes after a comma: "1 onion, diced"
    comma_idx = rest.find(",")
    prep_note: str | None = None
    if comma_idx > -1:
        prep_note = rest[comma_idx + 1:].strip() or None
        rest = rest[:comma_idx].strip()

    # Leading quantity
    qty_match = QTY_PATTERN.match(rest)
    if qty_match:
        qty = normalize_qty(qty_match.group(1))
        rest = rest[qty_match.end():].strip()

    # Optional parenthetical size, e.g. "1 (14 oz) can diced tomatoes"
    paren_match = re.match(r"^\(([^)]+)\)\s*", rest)
    if paren_match:
        inner = paren_match.group(1)
        inner_qty = QTY_PATTERN.match(inner)
        if inner_qty and not qty:
            qty = normalize_qty(inner_qty.group(1))
        rest = rest[paren_match.end():].strip()
        note = f"{note} ({inner})" if note else f"({inner})"

    # Unit
    unit_match = UNIT_PATTERN.match(rest)
    if unit_match:
        candidate = unit_match.group(1).lower().rstrip(".")
        if candidate in KNOWN_UNITS:
            two_word = re.match(r"^(fl|fluid)\s+(oz|ounce|ounces)\s+", rest, re.IGNORECASE)
            if two_word:
                unit = f"{two_word.group(1).lower()} {two_word.group(2).lower().rstrip('.')}"
                rest = rest[two_word.end():].strip()
            else:
                unit = candidate
                rest = rest[unit_match.end():].strip()

    # Drop trailing size descriptors like "(or as needed)" that would pollute the name
    name = re.sub(r"\s*\([^)]*\)\s*$", "", rest).strip()

    if prep_note:
        note = f"{note}, {prep_note}" if note else prep_note

    # If we captured no qty and no unit, the whole line is the name
    if not qty and not unit and not name:
        return {"qty": None, "unit": None, "name": line.strip(), "note": None}

    return {
        "qty": qty,
        "unit": unit,
        "name": name or line.strip(),
        "note": note,
    }


def parse_ingredient_text(text: str) -> list[dict[str, Any]]:
    """Parse a block of ingredient lines (one per line)."""
    return [parse_ingredient_line(line) for line in (line.strip() for line in text.split("\n")) if line]


def normalize_ingredient_name(name: str) -> str:
    """Stable comparable key for pantry matching and grocery merging."""
    out = re.sub(r"[^a-z0-9\s]", " ", name.lower())
    out = re.sub(r"\s+", " ", out).strip()
    out = re.sub(r"ies$", "y", out)
    out = re.sub(r"oes$", "o", out)
    out = re.sub(r"sses$", "ss", out)
    out = re.sub(r"s$", "", out)
    return out


def qty_to_number(qty: str | None) -> float | None:
    """Parse a decimal number from a qty string, returning None if not numeric."""
    if not qty:
        return None
    try:
        n = float(qty.replace(",", "."))
    except ValueError:
        return None
    return n if n == n and n not in (float("inf"), float("-inf")) else None
