"""Unit definitions and conversions — port of src/lib/grocery/units.ts.

Families: volume (base ml), weight (base g), count (base each), unknown.
"""

from __future__ import annotations

import re
from typing import Any, TypedDict


class UnitDef(TypedDict):
    canonical: str
    family: str
    factor: float
    size: float


def _u(canonical: str, family: str, factor: float, size: float) -> UnitDef:
    return {"canonical": canonical, "family": family, "factor": factor, "size": size}


UNIT_DEFS: dict[str, UnitDef] = {
    # volume
    "ml": _u("ml", "volume", 1, 0.001),
    "milliliter": _u("ml", "volume", 1, 0.001),
    "millilitre": _u("ml", "volume", 1, 0.001),
    "l": _u("l", "volume", 1000, 1),
    "liter": _u("l", "volume", 1000, 1),
    "litre": _u("l", "volume", 1000, 1),
    "tsp": _u("tsp", "volume", 4.92892, 0.02),
    "teaspoons": _u("tsp", "volume", 4.92892, 0.02),
    "teaspoon": _u("tsp", "volume", 4.92892, 0.02),
    "tbsp": _u("tbsp", "volume", 14.7868, 0.06),
    "tablespoons": _u("tbsp", "volume", 14.7868, 0.06),
    "tablespoon": _u("tbsp", "volume", 14.7868, 0.06),
    "fl_oz": _u("fl oz", "volume", 29.5735, 0.1),
    "floz": _u("fl oz", "volume", 29.5735, 0.1),
    "fluid ounce": _u("fl oz", "volume", 29.5735, 0.1),
    "fluid ounces": _u("fl oz", "volume", 29.5735, 0.1),
    "cup": _u("cup", "volume", 236.588, 1),
    "cups": _u("cup", "volume", 236.588, 1),
    "pint": _u("pint", "volume", 473.176, 2),
    "pints": _u("pint", "volume", 473.176, 2),
    "quart": _u("quart", "volume", 946.353, 4),
    "quarts": _u("quart", "volume", 946.353, 4),
    "gallon": _u("gallon", "volume", 3785.41, 16),
    "gallons": _u("gallon", "volume", 3785.41, 16),
    # weight
    "g": _u("g", "weight", 1, 0.001),
    "gram": _u("g", "weight", 1, 0.001),
    "grams": _u("g", "weight", 1, 0.001),
    "kg": _u("kg", "weight", 1000, 1),
    "kilogram": _u("kg", "weight", 1000, 1),
    "kilograms": _u("kg", "weight", 1000, 1),
    "oz": _u("oz", "weight", 28.3495, 0.03),
    "ounce": _u("oz", "weight", 28.3495, 0.03),
    "ounces": _u("oz", "weight", 28.3495, 0.03),
    "lb": _u("lb", "weight", 453.592, 1),
    "lbs": _u("lb", "weight", 453.592, 1),
    "pound": _u("lb", "weight", 453.592, 1),
    "pounds": _u("lb", "weight", 453.592, 1),
    # count
    "each": _u("", "count", 1, 1),
    "clove": _u("clove", "count", 1, 1),
    "cloves": _u("clove", "count", 1, 1),
    "can": _u("can", "count", 1, 1),
    "cans": _u("can", "count", 1, 1),
    "package": _u("package", "count", 1, 1),
    "packages": _u("package", "count", 1, 1),
    "pkg": _u("package", "count", 1, 1),
    "bunch": _u("bunch", "count", 1, 1),
    "bunches": _u("bunch", "count", 1, 1),
    "head": _u("head", "count", 1, 1),
    "heads": _u("head", "count", 1, 1),
    "stick": _u("stick", "count", 1, 1),
    "sticks": _u("stick", "count", 1, 1),
    "slice": _u("slice", "count", 1, 1),
    "slices": _u("slice", "count", 1, 1),
    "piece": _u("piece", "count", 1, 1),
    "pieces": _u("piece", "count", 1, 1),
    "pinch": _u("pinch", "count", 1, 1),
    "pinches": _u("pinch", "count", 1, 1),
    "dash": _u("dash", "count", 1, 1),
    "dashes": _u("dash", "count", 1, 1),
    "sprig": _u("sprig", "count", 1, 1),
    "sprigs": _u("sprig", "count", 1, 1),
    "pinch of": _u("pinch", "count", 1, 1),
}


def resolve_unit(raw: str | None) -> dict[str, Any]:
    """Resolve a raw unit string to {canonical, family, factor, size}."""
    if not raw:
        return {"canonical": "", "family": "count", "factor": 1, "size": 1}
    key = re.sub(r"\s+", " ", raw.strip().lower().replace(".", "")).strip()
    d = UNIT_DEFS.get(key)
    if d is not None:
        return {"canonical": d["canonical"], "family": d["family"], "factor": d["factor"], "size": d["size"]}
    return {"canonical": raw.strip().lower(), "family": "unknown", "factor": 1, "size": 1}


def to_base(value: float, unit: str | None) -> dict[str, Any]:
    u = resolve_unit(unit)
    return {"base": value * u["factor"], "family": u["family"]}


def from_base(base: float, unit: str | None) -> float:
    return base / resolve_unit(unit)["factor"]


def family_of(unit: str | None) -> str:
    return resolve_unit(unit)["family"]
