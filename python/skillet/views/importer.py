"""Recipe import page and SSRF-safe import API."""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from .. import auth
from ..import_parse import parse_recipe_html
from ..queries import editable_cookbooks
from ..safe_fetch import FetchError, safe_fetch_html

bp = Blueprint("importer", __name__)


@bp.route("/import")
@auth.require_user
def import_page():
    options = editable_cookbooks(auth.user_id())
    if not options:
        return render_template("import/none_available.html")
    requested = request.args.get("cookbook")
    chosen = next((c for c in options if c["id"] == requested), None) or options[0]
    return render_template("import/form.html", cookbooks=options, default_cookbook=chosen)


@bp.route("/api/import", methods=["POST"])
@auth.require_user
def api_import():
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Invalid request body."}), 400
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "Paste a recipe URL first."}), 400
    try:
        page = safe_fetch_html(url)
    except FetchError as exc:
        return jsonify({"error": exc.message}), 400
    draft = parse_recipe_html(page["html"], page["final_url"])
    if draft["method"] == "none":
        return (
            jsonify(
                {
                    "error": (
                        "We could not find recipe details on that page. It may be behind a login "
                        "or rely on JavaScript. You can still add it manually."
                    ),
                    "draft": draft,
                }
            ),
            422,
        )
    return jsonify({"draft": draft})
