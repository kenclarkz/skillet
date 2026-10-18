"""Retailer registry + shopping orchestration — port of retailers/index.ts."""

from __future__ import annotations

from typing import Any

from .instacart import InstacartAdapter, instacart_search_url
from .match import best_match, search_query_for_item, similarity, tokens
from .walmart import WalmartAdapter, walmart_search_url

walmart = WalmartAdapter()
instacart = InstacartAdapter()

RETAILERS: dict[str, Any] = {
    "walmart": walmart,
    "instacart": instacart,
}


def get_retailer(retailer_id: str) -> Any | None:
    return RETAILERS.get(retailer_id)


def retailer_status() -> list[dict[str, Any]]:
    return [
        {
            "id": rid,
            "displayName": adapter.display_name,
            "configured": adapter.is_configured,
        }
        for rid, adapter in RETAILERS.items()
    ]


def shop_with_retailer(retailer_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Send the list to a retailer, degrading honestly to manual links."""
    adapter = RETAILERS[retailer_id]
    return adapter.create_cart(items)


__all__ = [
    "walmart",
    "instacart",
    "RETAILERS",
    "get_retailer",
    "retailer_status",
    "shop_with_retailer",
    "walmart_search_url",
    "instacart_search_url",
    "best_match",
    "similarity",
    "tokens",
    "search_query_for_item",
]
