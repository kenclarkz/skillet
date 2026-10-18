"""Shopping page, retailer status, and cart/search API."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, render_template, request

from .. import auth
from ..grocery import format_quantity
from ..queries import get_grocery_items, get_grocery_list_id, get_plan
from ..retailers import get_retailer, retailer_status, shop_with_retailer

bp = Blueprint("shop", __name__)


@bp.route("/grocery/<plan_id>/shop")
@auth.require_user
def shop_page(plan_id):
    client = auth.db()
    plan = get_plan(client, plan_id)
    if not plan:
        return render_template("not_found.html"), 404
    list_id = get_grocery_list_id(client, plan_id)
    items = get_grocery_items(client, list_id) if list_id else []
    active_items = [i for i in items if not i.get("excluded")]
    return render_template(
        "grocery/shop.html",
        plan=plan,
        retailers=retailer_status(),
        item_count=len(active_items),
    )


@bp.route("/api/retailers")
def api_retailers():
    return jsonify({"retailers": retailer_status()})


@bp.route("/api/shop", methods=["POST"])
@auth.require_user
def api_shop():
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Invalid request."}), 400
    retailer_id = data.get("retailer")
    plan_id = data.get("planId")
    adapter = get_retailer(retailer_id) if retailer_id else None
    if adapter is None or not plan_id:
        return jsonify({"error": "Unknown retailer or missing plan."}), 400

    client = auth.db()
    plan = get_plan(client, plan_id)
    if not plan:
        return jsonify({"error": "Plan not found."}), 404
    list_id = get_grocery_list_id(client, plan_id)
    items = []
    if list_id:
        rows = (
            client.table("grocery_items")
            .select("id, name, qty, unit, checked, excluded")
            .eq("list_id", list_id)
            .eq("excluded", False)
            .order("sort_key", ascending=True)
            .execute()
        )
        items = [{"id": r["id"], "name": r["name"], "qty": r["qty"], "unit": r.get("unit") or ""} for r in rows]
    if not items:
        return jsonify({"error": "Build the grocery list first — there is nothing to shop for yet."}), 400

    result = shop_with_retailer(retailer_id, items)
    display_items = [
        {**mapped, "display": format_quantity({"qty": mapped["item"]["qty"], "unit": mapped["item"].get("unit") or "", "missing_qty": mapped["item"]["qty"] is None})}
        for mapped in result.get("items", [])
    ]
    result = {**result, "items": display_items}
    return jsonify({"result": result})
