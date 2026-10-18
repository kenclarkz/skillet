"""Grocery aggregation and formatting — port of src/lib/grocery/aggregate.ts.

Groups ingredients from many recipes into merged grocery items, converts
quantities across compatible units, and flags pantry staples.
"""

from __future__ import annotations

from typing import Any, Iterable

from .ingredients import normalize_ingredient_name, qty_to_number
from .units import from_base, resolve_unit, to_base

FRACTION_CANDIDATES: list[tuple[float, str]] = [
    (1 / 8, "1/8"), (1 / 6, "1/6"), (1 / 5, "1/5"), (1 / 4, "1/4"),
    (1 / 3, "1/3"), (3 / 8, "3/8"), (1 / 2, "1/2"), (5 / 8, "5/8"),
    (2 / 3, "2/3"), (3 / 4, "3/4"), (5 / 6, "5/6"), (7 / 8, "7/8"),
]


def aggregate_groceries(
    ingredients: Iterable[dict[str, Any]], pantry: set[str] | None = None
) -> list[dict[str, Any]]:
    """Merge source ingredients into grocery items.

    Each input ingredient is a dict: {qty, unit, name, note, recipeId, recipeTitle, scale?}.
    """
    pantry = pantry if pantry is not None else set()
    drafts: dict[str, dict[str, Any]] = {}

    for ing in ingredients:
        normalized = normalize_ingredient_name(ing.get("name") or "")
        if not normalized:
            continue

        scale = ing.get("scale") or 1
        unit_info = resolve_unit(ing.get("unit"))
        family = unit_info["family"]

        # Unknown-family units with differing text never merge across variants.
        unit_key = f"|{unit_info['canonical']}" if family == "unknown" and unit_info["canonical"] else ""
        key = f"{normalized}|{family}{unit_key}"

        draft = drafts.get(key)
        if draft is None:
            draft = {
                "key": key,
                "name": (ing.get("name") or "").strip(),
                "normalized_name": normalized,
                "base_total": 0.0,
                "has_numeric": False,
                "has_non_numeric": False,
                "unit_votes": {},
                "recipes": {},
                "recipe_ids": set(),
                "family": family,
                "unit_texts": set(),
            }
            drafts[key] = draft

        draft["recipe_ids"].add(ing["recipeId"])
        draft["recipes"][ing["recipeId"]] = ing["recipeTitle"]
        if ing.get("unit"):
            draft["unit_votes"][ing["unit"]] = draft["unit_votes"].get(ing["unit"], 0) + 1
        draft["unit_texts"].add(ing.get("unit") or "")

        num = qty_to_number(ing.get("qty"))
        if num is None:
            draft["has_non_numeric"] = True
        else:
            draft["has_numeric"] = True
            draft["base_total"] += to_base(num * scale, ing.get("unit"))["base"]

    items: list[dict[str, Any]] = []

    for d in drafts.values():
        # Choose display unit: most frequently used among contributors.
        display_unit = ""
        best_votes = -1
        for unit, votes in d["unit_votes"].items():
            if votes > best_votes:
                best_votes = votes
                display_unit = unit

        qty: float | None = None
        if d["has_numeric"]:
            qty = d["base_total"] if d["family"] == "unknown" else from_base(d["base_total"], display_unit)
            # Avoid tiny fractional remainders from unit conversion.
            if abs(qty - round(qty)) < 0.01:
                qty = round(qty * 1000) / 1000
            else:
                qty = round(qty * 10000) / 10000

        canonical_unit = (
            display_unit if d["family"] == "unknown" else resolve_unit(display_unit)["canonical"]
        )

        items.append({
            "key": d["key"],
            "name": d["name"],
            "normalized_name": d["normalized_name"],
            "qty": qty,
            "unit": canonical_unit,
            "family": d["family"],
            "recipe_ids": list(d["recipe_ids"]),
            "recipes": [{"id": rid, "title": title} for rid, title in d["recipes"].items()],
            "in_pantry": d["normalized_name"] in pantry,
            "missing_qty": d["has_non_numeric"],
            "split_note": "partial quantity" if d["has_non_numeric"] and d["has_numeric"] else None,
        })

    # Pantry staples sink to the bottom, then alphabetical.
    items.sort(key=lambda item: (item["in_pantry"], item["name"].lower()))
    return items


def format_quantity(item: dict[str, Any]) -> str:
    """Human-readable quantity + unit, e.g. "1 1/2 cups" or "to taste"."""
    if item.get("qty") is None:
        return "to taste" if item.get("missing_qty") else ""
    q = format_number(item["qty"])
    unit = item.get("unit") or ""
    if not unit:
        return q
    pluralize = (
        item["qty"] != 1
        and not unit.endswith("s")
        and unit not in ("lb", "oz", "fl oz", "tbsp", "tsp")
    )
    return f"{q} {unit}{'s' if pluralize else ''}".strip()


def format_number(n: float) -> str:
    """Format a number as a friendly cooking fraction where possible."""
    if float(n).is_integer():
        return str(int(n))
    whole = int(n) if n >= 0 else int(n // 1)  # JS Math.floor semantics
    frac = n - whole
    for value, label in FRACTION_CANDIDATES:
        if abs(frac - value) < 0.025:
            return f"{whole} {label}" if whole > 0 else label
    rounded = round(n * 100) / 100
    if float(rounded).is_integer():
        return str(int(rounded))
    return _trim(rounded)


def _trim(n: float) -> str:
    """Shortest decimal string that round-trips (JS String(n) behavior)."""
    text = f"{n:.10f}".rstrip("0").rstrip(".")
    return text or "0"
