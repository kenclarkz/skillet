"""Recipe CRUD, photo upload, and the recipe form."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from flask import Blueprint, current_app, jsonify, redirect, render_template, request

from .. import auth
from ..db import db
from ..errors import AppError
from ..ingredients import parse_ingredient_text
from ..models import Recipe
from ..queries import (
    editable_cookbooks,
    get_cookbook,
    get_recipe,
    get_role,
    int_or_none,
    parse_instructions,
    parse_tags,
    require_cookbook_role,
    require_visible_cookbook,
)

bp = Blueprint("recipes", __name__)

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/avif": ".avif",
}


@bp.route("/recipes/new")
@auth.require_user
def recipe_new():
    uid = auth.user_id()
    options = editable_cookbooks(uid)
    if not options:
        return render_template("recipes/none_available.html")
    requested = request.args.get("cookbook")
    chosen = next((c for c in options if c["id"] == requested), None)
    if requested and chosen is None:
        return redirect(f"/recipes/new?cookbook={options[0]['id']}")
    if chosen is None:
        chosen = options[0]
    return render_template("recipes/form_page.html", cookbook=chosen, options=options, recipe=None)


@bp.route("/recipes/<recipe_id>")
@auth.require_user
def recipe_detail(recipe_id):
    uid = auth.user_id()
    recipe = get_recipe(uid, recipe_id)
    if not recipe:
        return render_template("not_found.html"), 404
    role = get_role(uid, recipe["cookbook_id"])
    ingredients = recipe.get("ingredients") or []
    if ingredients and isinstance(ingredients[0], str):
        ingredients = parse_ingredient_text("\n".join(ingredients))
    recipe = {**recipe, "ingredients": ingredients}
    return render_template(
        "recipes/detail.html",
        recipe=recipe,
        role=role,
        editable=role in ("owner", "editor"),
    )


@bp.route("/recipes/<recipe_id>/edit")
@auth.require_user
def recipe_edit(recipe_id):
    uid = auth.user_id()
    recipe = get_recipe(uid, recipe_id)
    if not recipe:
        return render_template("not_found.html"), 404
    role = get_role(uid, recipe["cookbook_id"])
    if role not in ("owner", "editor"):
        return redirect(f"/recipes/{recipe_id}")
    cookbook = get_cookbook(uid, recipe["cookbook_id"])
    ingredients = recipe.get("ingredients") or []
    if ingredients and isinstance(ingredients[0], str):
        ingredients = parse_ingredient_text("\n".join(ingredients))
    recipe = {**recipe, "ingredients": ingredients}
    return render_template("recipes/form_page.html", cookbook=cookbook, options=None, recipe=recipe)


@bp.route("/recipes/save", methods=["POST"])
@auth.require_user
def save_recipe():
    uid = auth.user_id()
    recipe_id = (request.form.get("id") or "").strip()
    cookbook_id = (request.form.get("cookbook_id") or "").strip()
    title = (request.form.get("title") or "").strip()
    description = (request.form.get("description") or "").strip() or None
    photo_path = (request.form.get("photo_path") or "").strip() or None
    source_url = (request.form.get("source_url") or "").strip() or None
    prep_minutes = int_or_none(request.form.get("prep_minutes"))
    cook_minutes = int_or_none(request.form.get("cook_minutes"))
    try:
        servings = int(float(request.form.get("servings") or 4))
    except ValueError:
        servings = 4
    servings = max(1, min(100, servings))
    tags = parse_tags(request.form.get("tags") or "")
    ingredients = parse_ingredient_text(request.form.get("ingredients_text") or "")
    instructions = parse_instructions(request.form.get("instructions_text") or "")

    if not title:
        raise AppError("Give the recipe a title.")
    if not ingredients:
        raise AppError("Add at least one ingredient.")

    if recipe_id:
        recipe = db.session.get(Recipe, recipe_id)
        if recipe is None:
            raise AppError("Recipe not found.", 404)
        require_cookbook_role(uid, recipe.cookbook_id)
        recipe.title = title[:200]
        recipe.description = description
        recipe.photo_path = photo_path
        recipe.source_url = source_url
        recipe.prep_minutes = prep_minutes
        recipe.cook_minutes = cook_minutes
        recipe.servings = servings
        recipe.tags = tags
        recipe.ingredients = ingredients
        recipe.instructions = instructions
        db.session.commit()
        return redirect(f"/recipes/{recipe_id}")

    if not cookbook_id:
        raise AppError("Choose a cookbook.")
    require_cookbook_role(uid, cookbook_id)
    recipe = Recipe(
        cookbook_id=cookbook_id,
        created_by=uid,
        title=title[:200],
        description=description,
        photo_path=photo_path,
        source_url=source_url,
        prep_minutes=prep_minutes,
        cook_minutes=cook_minutes,
        servings=servings,
        tags=tags,
        ingredients=ingredients,
        instructions=instructions,
    )
    db.session.add(recipe)
    db.session.commit()
    return redirect(f"/recipes/{recipe.id}")


@bp.route("/recipes/<recipe_id>/delete", methods=["POST"])
@auth.require_user
def delete_recipe(recipe_id):
    uid = auth.user_id()
    recipe = db.session.get(Recipe, recipe_id)
    if recipe is None:
        cookbook_id = request.form.get("cookbook_id") or ""
        return redirect(f"/cookbooks/{cookbook_id}" if cookbook_id else "/cookbooks")
    require_cookbook_role(uid, recipe.cookbook_id)
    cookbook_id = request.form.get("cookbook_id") or recipe.cookbook_id
    db.session.delete(recipe)
    db.session.commit()
    return redirect(f"/cookbooks/{cookbook_id}")


@bp.route("/api/photos", methods=["POST"])
@auth.require_user
def upload_photo():
    """Server-side photo upload into the local uploads directory."""
    cfg = current_app.config["SKILLET"]
    uid = auth.user_id()
    cookbook_id = (request.form.get("cookbook_id") or "").strip()
    file = request.files.get("file")
    if not cookbook_id:
        return jsonify({"error": "Missing cookbook."}), 400
    require_cookbook_role(uid, cookbook_id)
    if file is None or not file.filename:
        return jsonify({"error": "Choose an image first."}), 400
    content = file.read(cfg.MAX_PHOTO_BYTES + 1)
    if len(content) > cfg.MAX_PHOTO_BYTES:
        return jsonify({"error": "Photos must be 5 MB or smaller."}), 400
    content_type = (file.mimetype or "").lower()
    extension = ALLOWED_IMAGE_TYPES.get(content_type)
    if not extension:
        return jsonify({"error": "Upload a JPEG, PNG, GIF, WebP, or AVIF image."}), 400
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "-", Path(file.filename).name)[-60:]
    path = f"{cookbook_id}/{uuid.uuid4()}-{safe_name or 'photo'}{extension}"
    destination = cfg.UPLOAD_DIR / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return jsonify({"path": path, "url": cfg.public_photo_url(path)})
