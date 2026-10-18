"""Skillet Flask application factory."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from flask import Flask, jsonify, render_template, request, send_from_directory
from sqlalchemy.exc import SQLAlchemyError

from . import auth
from .config import Config
from .db import init_db
from .errors import AppError
from .qr import qr_svg
from .queries import ingredients_to_lines


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    cfg = Config()
    app.config["SKILLET"] = cfg
    app.config["SECRET_KEY"] = cfg.SECRET_KEY
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = False  # flipped per-request via set_cookie secure flag
    app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 30

    init_db(app)

    app.before_request(auth.load_user)
    app.before_request(auth.validate_csrf)
    app.after_request(auth.apply_cookie_ops)

    @app.context_processor
    def inject_globals() -> dict[str, Any]:
        cfg: Config = app.config["SKILLET"]
        user = g_user()
        return {
            "cfg": cfg,
            "is_configured": True,
            "current_user": user,
            "display_name": user.get("display_name") if user else None,
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

    @app.route("/media/<path:photo_path>")
    def media(photo_path: str):
        """Serve uploaded recipe photos (replaces the Supabase Storage bucket)."""
        return send_from_directory(str(cfg.UPLOAD_DIR), photo_path)

    @app.errorhandler(AppError)
    def handle_app_error(exc: AppError):
        if request.path.startswith("/api/"):
            return jsonify({"error": exc.message}), exc.status
        return render_template("error.html", message=exc.message), exc.status

    @app.errorhandler(SQLAlchemyError)
    def handle_db_error(exc: SQLAlchemyError):
        from .db import db

        app.logger.exception("Database error on %s %s", request.method, request.path)
        db.session.rollback()
        message = "The database is busy — please try again."
        if request.path.startswith("/api/"):
            return jsonify({"error": message}), 503
        return render_template("error.html", message=message), 503

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


def g_user():
    from flask import g

    return g.get("user")


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
