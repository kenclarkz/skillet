"""Grocery list page and item mutations."""

from __future__ import annotations

from flask import Blueprint, redirect, render_template, request

from .. import auth
from ..ingredients import normalize_ingredient_name, qty_to_number
from ..queries import (
    build_grocery_list,
    get_grocery_items,
    get_grocery_list_id,
    get_plan,
    get_plan_recipes,
    get_recipes,
    get_role,
)
from ..supabase import SupabaseError

bp = Blueprint("grocery", __name__)


@bp.route("/grocery/<plan_id>")
@auth.require_user
def grocery_list(plan_id):
    client = auth.db()
    plan = get_plan(client, plan_id)
    if not plan:
        return render_template("not_found.html"), 404
    role = get_role(client, plan["cookbook_id"])
    editable = role in ("owner", "editor")
    list_id = get_grocery_list_id(client, plan_id)
    plan_recipes = get_plan_recipes(client, plan_id)
    recipes = get_recipes(client, plan["cookbook_id"])
    title_by_id = {r["id"]: r["title"] for r in recipes}
    winning_count = sum(1 for pr in plan_recipes if pr.get("selected"))

    items: list[dict] = []
    if list_id:
        items = get_grocery_items(client, list_id)
    for item in items:
        item["recipes"] = [
            {"id": rid, "title": title_by_id.get(rid, "Recipe")}
            for rid in (item.get("recipe_ids") or [])
        ]

    return render_template(
        "grocery/list.html",
        plan=plan,
        editable=editable,
        list_id=list_id,
        items=items,
        winning_count=winning_count,
        active_count=sum(1 for i in items if not i.get("excluded")),
    )


@bp.route("/grocery/<plan_id>/build", methods=["POST"])
@auth.require_user
def build(plan_id):
    client = auth.db()
    build_grocery_list(client, plan_id, auth.user_id())
    return redirect(f"/grocery/{plan_id}")


@bp.route("/grocery/items/toggle", methods=["POST"])
@auth.require_user
def toggle_item():
    client = auth.db()
    list_id = request.form.get("list_id") or ""
    item_id = request.form.get("item_id") or ""
    plan_id = request.form.get("plan_id") or ""
    field = request.form.get("field") or ""
    if field not in ("checked", "excluded"):
        raise SupabaseError("Invalid field.")
    value = request.form.get("value") == "true"
    client.table("grocery_items").update({field: value}).eq("id", item_id).eq("list_id", list_id).execute()
    return redirect(f"/grocery/{plan_id}")


@bp.route("/grocery/items/add", methods=["POST"])
@auth.require_user
def add_item():
    client = auth.db()
    list_id = request.form.get("list_id") or ""
    plan_id = request.form.get("plan_id") or ""
    name = (request.form.get("name") or "").strip()
    if not name:
        raise SupabaseError("Give the item a name.")
    qty = qty_to_number(request.form.get("qty"))
    unit = (request.form.get("unit") or "").strip() or ""
    (
        client.table("grocery_items")
        .insert(
            {
                "list_id": list_id,
                "name": name,
                "normalized_name": normalize_ingredient_name(name),
                "qty": qty,
                "unit": unit,
                "sort_key": name.lower(),
            }
        )
        .execute()
    )
    return redirect(f"/grocery/{plan_id}")


@bp.route("/grocery/items/delete", methods=["POST"])
@auth.require_user
def delete_item():
    client = auth.db()
    item_id = request.form.get("item_id") or ""
    plan_id = request.form.get("plan_id") or ""
    client.table("grocery_items").delete().eq("id", item_id).execute()
    return redirect(f"/grocery/{plan_id}")


@bp.route("/grocery/items/mark-pantry", methods=["POST"])
@auth.require_user
def mark_pantry():
    client = auth.db()
    uid = auth.user_id()
    item_id = request.form.get("item_id") or ""
    plan_id = request.form.get("plan_id") or ""
    name = (request.form.get("name") or "").strip()
    if not name:
        raise SupabaseError("Give the item a name.")
    (
        client.table("pantry_items")
        .upsert(
            {"user_id": uid, "name": name, "normalized_name": normalize_ingredient_name(name)},
            on_conflict="user_id,normalized_name",
        )
        .execute()
    )
    client.table("grocery_items").update({"in_pantry": True, "excluded": True}).eq("id", item_id).execute()
    return redirect(f"/grocery/{plan_id}")
