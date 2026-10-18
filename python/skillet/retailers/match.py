"""Product matching: maps a grocery item to the best candidate product.

Port of src/lib/retailers/match.ts.
"""

from __future__ import annotations

import re
from typing import Any

STOP_WORDS = {
    "fresh", "organic", "the", "of", "and", "a", "an", "for", "with", "large",
    "small", "medium", "whole", "boneless", "skinless", "extra", "virgin",
    "to", "taste", "chopped", "diced", "minced", "sliced", "shredded",
}


def tokens(text: str) -> list[str]:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    out = []
    for t in cleaned.split():
        t = re.sub(r"s$", "", t)
        if t and t not in STOP_WORDS:
            out.append(t)
    return out


def similarity(item_name: str, product_title: str) -> float:
    """0..1 similarity between a grocery item and a product title."""
    a = set(tokens(item_name))
    b = set(tokens(product_title))
    if not a or not b:
        return 0.0
    overlap = len(a & b)
    jaccard = overlap / (len(a) + len(b) - overlap)
    phrase = item_name.lower().strip()
    bonus = 0.35 if len(phrase) > 3 and phrase in product_title.lower() else 0.0
    return min(1.0, jaccard + bonus)


def best_match(item: dict[str, Any], products: list[dict[str, Any]]) -> dict[str, Any]:
    """Return {product, confidence}; product is None when nothing scores >= 0.25."""
    best: dict[str, Any] | None = None
    best_score = 0.0
    for product in products:
        score = similarity(item["name"], product["title"])
        if score > best_score:
            best_score = score
            best = product
    if best_score < 0.25:
        return {"product": None, "confidence": best_score}
    return {"product": best, "confidence": best_score}


def search_query_for_item(item: dict[str, Any]) -> str:
    """Query text for a grocery item."""
    return item["name"].strip()
