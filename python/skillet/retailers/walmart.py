"""Walmart adapter — port of src/lib/retailers/walmart.ts.

Honest behavior: a cart is only reported when the API confirms a cart id.
Without credentials the adapter returns real search links, never a fake cart.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any

import requests

from .match import best_match, search_query_for_item

DEFAULT_BASE = "https://developer.api.walmart.com"
TIMEOUT = 15


def _env(name: str) -> str | None:
    import os

    value = os.environ.get(name, "")
    return value.strip() if value and value.strip() else None


def walmart_search_url(query: str) -> str:
    from urllib.parse import quote_plus

    return f"https://www.walmart.com/search?q={quote_plus(query)}"


class WalmartAdapter:
    id = "walmart"
    display_name = "Walmart"

    def __init__(self) -> None:
        self._cached_token: dict[str, Any] | None = None
        self._token_lock = threading.Lock()

    @property
    def is_configured(self) -> bool:
        if _env("WALMART_ACCESS_TOKEN"):
            return True
        return bool(_env("WALMART_CONSUMER_ID") and _env("WALMART_PRIVATE_KEY"))

    @property
    def base(self) -> str:
        return (_env("WALMART_API_BASE") or DEFAULT_BASE).rstrip("/")

    def _get_token(self) -> str:
        direct = _env("WALMART_ACCESS_TOKEN")
        if direct:
            return direct
        with self._token_lock:
            if self._cached_token and self._cached_token["expires_at"] > time.time() + 30:
                return self._cached_token["value"]
            consumer_id = _env("WALMART_CONSUMER_ID")
            private_key = _env("WALMART_PRIVATE_KEY")
            if not consumer_id or not private_key:
                raise RuntimeError("Walmart credentials are not configured.")
            res = requests.post(
                f"{self.base}/api-proxy/service/affiliate/v2/token",
                headers={
                    "WM_CONSUMER.ID": consumer_id,
                    "WM_CONSUMER.SIGNATURE": private_key,
                    "WM_QOS.CORRELATION_ID": str(uuid.uuid4()),
                    "accept": "application/json",
                },
                timeout=TIMEOUT,
            )
            if res.status_code >= 400:
                raise RuntimeError(f"Walmart token request failed ({res.status_code}).")
            data = res.json()
            token = data.get("access_token")
            if not token:
                raise RuntimeError("Walmart token response did not include an access token.")
            expires_in = data.get("expires_in")
            try:
                seconds = float(expires_in)
            except (TypeError, ValueError):
                seconds = 600.0
            self._cached_token = {"value": token, "expires_at": time.time() + seconds}
            return token

    def search_products(self, query: str, limit: int = 10) -> dict[str, Any]:
        if not self.is_configured:
            return {
                "retailer": self.id,
                "status": "unconfigured",
                "products": [],
                "message": "Walmart Affiliate API credentials are not configured.",
            }
        try:
            token = self._get_token()
            res = requests.get(
                f"{self.base}/api-proxy/service/affiliate/v2/items/search",
                params={"query": query, "numItems": limit},
                headers={
                    "WM_SEC.ACCESS_TOKEN": token,
                    "WM_QOS.CORRELATION_ID": str(uuid.uuid4()),
                    "accept": "application/json",
                },
                timeout=TIMEOUT,
            )
            if res.status_code >= 400:
                return {
                    "retailer": self.id,
                    "status": "error",
                    "products": [],
                    "message": f"Walmart search failed ({res.status_code} {res.reason}).",
                }
            items = res.json().get("items") or []
            products = [p for p in (_map_item(i) for i in items) if p is not None]
            return {"retailer": self.id, "status": "ok", "products": products}
        except (requests.RequestException, RuntimeError, ValueError) as err:
            return {
                "retailer": self.id,
                "status": "error",
                "products": [],
                "message": str(err) or "Walmart search failed.",
            }

    def create_cart(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        # The Walmart Affiliate API does not expose a general cart-creation
        # endpoint for all partners. Only claim a cart when a configured
        # endpoint confirms it; otherwise return honest search links.
        cart_endpoint = _env("WALMART_CART_ENDPOINT")

        if not self.is_configured or not cart_endpoint:
            return {
                "retailer": self.id,
                "status": "link",
                "message": (
                    "Direct Walmart cart creation is not available with the current configuration. "
                    "Use the per-item search links below to shop manually."
                ),
                "items": [
                    {
                        "item": item,
                        "query": search_query_for_item(item),
                        "product": None,
                        "confidence": 0,
                        "searchUrl": walmart_search_url(search_query_for_item(item)),
                    }
                    for item in items
                ],
            }

        try:
            token = self._get_token()
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
                        "searchUrl": walmart_search_url(query),
                    }
                )

            product_ids = [m["product"]["id"] for m in matched if m.get("product")]
            if not product_ids:
                return {
                    "retailer": self.id,
                    "status": "link",
                    "message": "No matching products found; use the search links to shop manually.",
                    "items": matched,
                }

            res = requests.post(
                cart_endpoint,
                json={"items": [{"itemId": pid, "quantity": 1} for pid in product_ids]},
                headers={
                    "WM_SEC.ACCESS_TOKEN": token,
                    "WM_QOS.CORRELATION_ID": str(uuid.uuid4()),
                    "content-type": "application/json",
                    "accept": "application/json",
                },
                timeout=TIMEOUT,
            )
            if res.status_code >= 400:
                return {
                    "retailer": self.id,
                    "status": "error",
                    "message": f"Walmart cart creation failed ({res.status_code}). Shop manually with the links below.",
                    "items": matched,
                }
            data = res.json()
            cart_id = data.get("cartId")
            if not cart_id:
                return {
                    "retailer": self.id,
                    "status": "error",
                    "message": "Walmart did not return a cart id, so no cart was created.",
                    "items": matched,
                }
            return {
                "retailer": self.id,
                "status": "created",
                "cartId": cart_id,
                "url": data.get("url"),
                "message": "Walmart cart created.",
                "items": matched,
            }
        except (requests.RequestException, RuntimeError, ValueError) as err:
            return {
                "retailer": self.id,
                "status": "error",
                "message": str(err) or "Walmart cart creation failed.",
                "items": [
                    {
                        "item": item,
                        "query": search_query_for_item(item),
                        "product": None,
                        "confidence": 0,
                        "searchUrl": walmart_search_url(search_query_for_item(item)),
                    }
                    for item in items
                ],
            }


def _map_item(item: dict[str, Any]) -> dict[str, Any] | None:
    raw_id = item.get("itemId")
    item_id = str(raw_id) if raw_id is not None else None
    name = item.get("name")
    if not item_id or not name:
        return None
    price = item.get("salePrice")
    price_value = float(price) if isinstance(price, (int, float)) else None
    url = (
        item.get("productUrl")
        or item.get("canonicalUrl")
        or f"https://www.walmart.com/ip/{item_id}"
    )
    return {
        "id": item_id,
        "title": name,
        "brand": item.get("brandName"),
        "size": item.get("size"),
        "price": price_value,
        "priceText": f"${price_value:.2f}" if price_value is not None else None,
        "imageUrl": item.get("largeImage") or item.get("mediumImage") or item.get("thumbnailImage"),
        "url": url,
    }
