"""Instacart adapter — port of src/lib/retailers/instacart.ts.

Partner APIs require approved credentials; every failure is surfaced
honestly and a cart is only claimed when Instacart returned a cart id.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote_plus

import requests

from .match import best_match, search_query_for_item

DEFAULT_BASE = "https://api.instacart.com/v2"
TIMEOUT = 15


def _env(name: str) -> str | None:
    value = os.environ.get(name, "")
    return value.strip() if value and value.strip() else None


def instacart_search_url(query: str) -> str:
    return f"https://www.instacart.com/store/s?k={quote_plus(query)}"


class InstacartAdapter:
    id = "instacart"
    display_name = "Instacart"

    @property
    def is_configured(self) -> bool:
        return bool(_env("INSTACART_API_KEY"))

    @property
    def base(self) -> str:
        return (_env("INSTACART_API_BASE") or DEFAULT_BASE).rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {
            "authorization": f"Bearer {_env('INSTACART_API_KEY')}",
            "accept": "application/json",
        }

    def search_products(self, query: str, limit: int = 10) -> dict[str, Any]:
        if not self.is_configured:
            return {
                "retailer": self.id,
                "status": "unconfigured",
                "products": [],
                "message": "Instacart partner API credentials are not configured.",
            }
        try:
            path = _env("INSTACART_SEARCH_PATH") or "/products"
            res = requests.get(
                f"{self.base}{path}",
                params={"q": query, "limit": limit},
                headers=self._headers(),
                timeout=TIMEOUT,
            )
            if res.status_code >= 400:
                return {
                    "retailer": self.id,
                    "status": "error",
                    "products": [],
                    "message": f"Instacart search failed ({res.status_code} {res.reason}).",
                }
            data = res.json()
            raw = data.get("products") or data.get("data") or []
            products = [p for p in (_map_product(i) for i in raw) if p is not None]
            return {"retailer": self.id, "status": "ok", "products": products}
        except (requests.RequestException, ValueError) as err:
            return {
                "retailer": self.id,
                "status": "error",
                "products": [],
                "message": str(err) or "Instacart search failed.",
            }

    def create_cart(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.is_configured:
            return {
                "retailer": self.id,
                "status": "link",
                "message": (
                    "Instacart partner API credentials are not configured. "
                    "Use the search links to shop manually."
                ),
                "items": [
                    {
                        "item": item,
                        "query": search_query_for_item(item),
                        "product": None,
                        "confidence": 0,
                        "searchUrl": instacart_search_url(search_query_for_item(item)),
                    }
                    for item in items
                ],
            }

        try:
            matched = []
            for item in items:
                query = search_query_for_item(item)
                search = self.search_products(query, 8)
                if search["status"] == "ok":
                    m = best_match(item, search["products"])
                else:
                    m = {"product": None, "confidence": 0}
                matched.append(
                    {
                        "item": item,
                        "query": query,
                        "product": m["product"],
                        "confidence": m["confidence"],
                        "searchUrl": instacart_search_url(query),
                    }
                )

            line_items = [
                {"product_id": m["product"]["id"], "quantity": 1}
                for m in matched
                if m.get("product")
            ]
            if not line_items:
                return {
                    "retailer": self.id,
                    "status": "link",
                    "message": "No matching products found; use the search links to shop manually.",
                    "items": matched,
                }

            path = _env("INSTACART_CART_PATH") or "/carts"
            headers = {**self._headers(), "content-type": "application/json"}
            res = requests.post(f"{self.base}{path}", json={"line_items": line_items}, headers=headers, timeout=TIMEOUT)
            if res.status_code >= 400:
                return {
                    "retailer": self.id,
                    "status": "error",
                    "message": f"Instacart cart creation failed ({res.status_code}). Shop manually with the links below.",
                    "items": matched,
                }
            data = res.json()
            cart_id = data.get("cart_id") or data.get("id")
            if not cart_id:
                return {
                    "retailer": self.id,
                    "status": "error",
                    "message": "Instacart did not return a cart id, so no cart was created.",
                    "items": matched,
                }
            return {
                "retailer": self.id,
                "status": "created",
                "cartId": cart_id,
                "url": data.get("products_link_url") or data.get("url"),
                "message": "Instacart cart created.",
                "items": matched,
            }
        except (requests.RequestException, ValueError) as err:
            return {
                "retailer": self.id,
                "status": "error",
                "message": str(err) or "Instacart cart creation failed.",
                "items": [
                    {
                        "item": item,
                        "query": search_query_for_item(item),
                        "product": None,
                        "confidence": 0,
                        "searchUrl": instacart_search_url(search_query_for_item(item)),
                    }
                    for item in items
                ],
            }


def _map_product(p: dict[str, Any]) -> dict[str, Any] | None:
    product_id = p.get("id", p.get("product_id"))
    title = p.get("name") or p.get("title")
    if product_id is None or not title:
        return None
    price = p.get("price")
    price_value = float(price) if isinstance(price, (int, float)) else None
    return {
        "id": str(product_id),
        "title": title,
        "brand": p.get("brand") or p.get("brand_name"),
        "size": p.get("size"),
        "price": price_value,
        "priceText": f"${price_value:.2f}" if price_value is not None else None,
        "imageUrl": p.get("image_url") or p.get("image"),
        "url": p.get("url") or p.get("permalink") or f"https://www.instacart.com/products/{product_id}",
    }
