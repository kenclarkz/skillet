"""Skillet Flask application factory."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from flask import Flask, jsonify, render_template, request

from . import auth
from .config import Config
from .qr import qr_svg
from .queries import ingredients_to_lines
from .supabase import SupabaseError


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    cfg = Config()
    app.config["SKILLET"] = cfg
    app.config["SECRET_KEY"] = cfg.SECRET_KEY
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = False  # flipped per-request via set_cookie secure flag

    app.before_request(auth.load_user)
    app.before_request(auth.validate_csrf)
    app.after_request(auth.apply_cookie_ops)

    @app.context_processor
    def inject_globals() -> dict[str, Any]:
        from flask import g

        cfg: Config = app.config["SKILLET"]
        user = g.get("user")
        display_name = session_display_name(user) if user else None
        return {
            "cfg": cfg,
            "is_configured": cfg.is_configured,
            "current_user": user,
            "display_name": display_name,
            "csrf_token": auth.csrf_token(),
            "app_url": cfg.APP_URL,
            "public_photo_url": cfg.public_photo_url,
            "format_date": format_date,
            "format_week": format_week,
            "format_minutes": format_minutes,
            "ingredient_lines": ingredients_to_lines,
            "recipe_photo": recipe_photo,
            "qty_str": qty_display,
            "qr_svg": qr_svg,
        }

    @app.errorhandler(SupabaseError)
    def handle_supabase_error(exc: SupabaseError):
        if request.path.startswith("/api/"):
            return jsonify({"error": exc.message}), exc.status or 400
        return render_template("error.html", message=exc.message), exc.status or 400

    @app.errorhandler(404)
    def handle_not_found(_e):
        return render_template("not_found.html"), 404

    @app.errorhandler(400)
    def handle_bad_request(e):
        message = getattr(e, "description", "Bad request.")
        if request.path.startswith("/api/"):
            return jsonify({"error": message}), 400
        return render_template("error.html", message=message), 400

    from .views import register_blueprints

    register_blueprints(app)
    return app


def session_display_name(user: dict[str, Any]) -> str | None:
    from flask import g

    client = auth.db()
    try:
        profile = client.table("profiles").select("display_name").eq("id", user["id"]).maybe_single().execute()
        if profile and profile.get("display_name"):
            return profile["display_name"]
    except SupabaseError:
        pass
    return user.get("email")


def format_date(value: Any, style: str = "long") -> str:
    d = _as_date(value)
    if d is None:
        return str(value or "")
    if style == "short":
        return f"{d.strftime('%b')} {d.day}"
    return d.strftime("%B %-d, %Y") if hasattr(d, "strftime") else str(d)


def format_week(value: Any) -> str:
    d = _as_date(value)
    if d is None:
        return f"Week of {value}"
    return f"Week of {d.strftime('%b')} {d.day}"


def _as_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def format_minutes(minutes: Any) -> str:
    try:
        total = int(minutes)
    except (TypeError, ValueError):
        return ""
    if total < 60:
        return f"{total} min"
    hours, rest = divmod(total, 60)
    return f"{hours} hr {rest} min" if rest else f"{hours} hr"


def recipe_photo(recipe: dict[str, Any]) -> str | None:
    cfg: Config = current_cfg()
    return cfg.public_photo_url(recipe.get("photo_url") or recipe.get("photo_path"))


def current_cfg() -> Config:
    from flask import current_app

    return current_app.config["SKILLET"]


def qty_display(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    return text
