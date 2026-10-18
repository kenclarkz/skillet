"""Grocery list page and item mutations."""

from __future__ import annotations

from flask import Blueprint, redirect, render_template, request

from .. import auth
from ..db import db
from ..errors import AppError
from ..ingredients import normalize_ingredient_name, qty_to_number
from ..models import GroceryItem, PantryItem
from ..queries import (
    build_grocery_list,
    get_grocery_items,
    get_grocery_list_id,
    get_plan,
    get_plan_recipes,
    get_recipes,
    get_role,
    require_grocery_list,
    require_plan,
)

bp = Blueprint("grocery", __name__)


@bp.route("/grocery/<plan_id>")
@auth.require_user
def grocery_list(plan_id):
    uid = auth.user_id()
    plan = get_plan(uid, plan_id)
    if not plan:
        return render_template("not_found.html"), 404
    role = get_role(uid, plan["cookbook_id"])
    editable = role in ("owner", "editor")
    list_id = get_grocery_list_id(uid, plan_id)
    plan_recipes = get_plan_recipes(uid, plan_id)
    recipes = get_recipes(uid, plan["cookbook_id"])
    title_by_id = {r["id"]: r["title"] for r in recipes}
    winning_count = sum(1 for pr in plan_recipes if pr.get("selected"))

    items: list[dict] = []
    if list_id:
        items = get_grocery_items(uid, list_id)
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
    build_grocery_list(auth.user_id(), plan_id)
    return redirect(f"/grocery/{plan_id}")


@bp.route("/grocery/items/toggle", methods=["POST"])
@auth.require_user
def toggle_item():
    uid = auth.user_id()
    list_id = request.form.get("list_id") or ""
    item_id = request.form.get("item_id") or ""
    plan_id = request.form.get("plan_id") or ""
    field = request.form.get("field") or ""
    if field not in ("checked", "excluded"):
        raise AppError("Invalid field.")
    require_grocery_list(uid, list_id, editable=True)
    value = request.form.get("value") == "true"
    item = db.session.get(GroceryItem, item_id)
    if item is not None and item.list_id == list_id:
        setattr(item, field, value)
        db.session.commit()
    return redirect(f"/grocery/{plan_id}")


@bp.route("/grocery/items/add", methods=["POST"])
@auth.require_user
def add_item():
    uid = auth.user_id()
    list_id = request.form.get("list_id") or ""
    plan_id = request.form.get("plan_id") or ""
    name = (request.form.get("name") or "").strip()
    if not name:
        raise AppError("Give the item a name.")
    require_grocery_list(uid, list_id, editable=True)
    qty = qty_to_number(request.form.get("qty"))
    unit = (request.form.get("unit") or "").strip() or ""
    db.session.add(
        GroceryItem(
            list_id=list_id,
            name=name,
            normalized_name=normalize_ingredient_name(name),
            qty=qty,
            unit=unit,
            sort_key=name.lower(),
        )
    )
    db.session.commit()
    return redirect(f"/grocery/{plan_id}")


@bp.route("/grocery/items/delete", methods=["POST"])
@auth.require_user
def delete_item():
    uid = auth.user_id()
    item_id = request.form.get("item_id") or ""
    plan_id = request.form.get("plan_id") or ""
    item = db.session.get(GroceryItem, item_id)
    if item is not None:
        require_grocery_list(uid, item.list_id, editable=True)
        db.session.delete(item)
        db.session.commit()
    return redirect(f"/grocery/{plan_id}")


@bp.route("/grocery/items/mark-pantry", methods=["POST"])
@auth.require_user
def mark_pantry():
    uid = auth.user_id()
    item_id = request.form.get("item_id") or ""
    plan_id = request.form.get("plan_id") or ""
    name = (request.form.get("name") or "").strip()
    if not name:
        raise AppError("Give the item a name.")
    normalized = normalize_item_name(name)
    existing = (
        db.session.query(PantryItem)
        .filter(PantryItem.user_id == uid, PantryItem.normalized_name == normalized)
        .one_or_none()
    )
    if existing is None:
        db.session.add(PantryItem(user_id=uid, name=name, normalized_name=normalized))
    item = db.session.get(GroceryItem, item_id)
    if item is not None:
        require_grocery_list(uid, item.list_id, editable=True)
        item.in_pantry = True
        item.excluded = True
    db.session.commit()
    return redirect(f"/grocery/{plan_id}")
