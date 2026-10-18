"""Landing, auth, session, and settings routes."""

from __future__ import annotations

from flask import Blueprint, current_app, g, redirect, render_template, request

from .. import auth
from ..db import db
from ..errors import AppError
from ..models import PantryItem, PasswordResetToken, User, utcnow
from ..queries import ensure_default_cookbook, get_pantry, get_profile

bp = Blueprint("main", __name__)


def safe_next(target: str | None, default: str = "/cookbooks") -> str:
    if target and target.startswith("/") and not target.startswith("//") and not target.startswith("/\\"):
        return target
    return default


@bp.route("/")
def index():
    return render_template("index.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if g.get("user"):
            return redirect("/cookbooks")
        return render_template("login.html", next_url=request.args.get("next", ""), error=None)

    email = (request.form.get("email") or "").strip()
    password = request.form.get("password") or ""
    next_url = safe_next(request.form.get("next"))
    if not email or not password:
        return render_template("login.html", next_url=next_url, error="Email and password are required."), 400
    user = auth.find_user_by_email(email)
    if user is None or (user.password_hash and not auth.verify_password(user, password)):
        return render_template("login.html", next_url=next_url, error="Wrong email or password."), 400
    if not user.password_hash:
        return (
            render_template(
                "login.html",
                next_url=next_url,
                error="This account was imported from Supabase. Open your claim link to set a password first.",
            ),
            400,
        )
    auth.start_session(user)
    return redirect(next_url)


@bp.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        if g.get("user"):
            return redirect("/cookbooks")
        return render_template("signup.html", next_url=request.args.get("next", ""), error=None)

    email = (request.form.get("email") or "").strip()
    password = request.form.get("password") or ""
    display_name = (request.form.get("display_name") or "").strip()
    next_url = safe_next(request.form.get("next"))
    if not email or not password:
        return render_template("signup.html", next_url=next_url, error="Email and password are required."), 400
    if len(password) < auth.MIN_PASSWORD_LENGTH:
        return (
            render_template("signup.html", next_url=next_url, error="Password must be at least 6 characters."),
            400,
        )
    if auth.find_user_by_email(email):
        return render_template("signup.html", next_url=next_url, error="That email is already registered."), 400
    user = auth.create_user(email, password, display_name)
    ensure_default_cookbook(user)
    db.session.commit()
    auth.start_session(user)
    return redirect(next_url)


@bp.route("/logout", methods=["POST"])
def logout():
    auth.clear_session()
    return redirect("/login")


@bp.route("/claim/<token>", methods=["GET", "POST"])
def claim_account(token):
    """Set a first password on an account imported from Supabase."""
    reset = db.session.query(PasswordResetToken).filter(PasswordResetToken.token == token).one_or_none()
    valid = bool(
        reset
        and reset.used_at is None
        and reset.expires_at > utcnow()
    )
    if not valid:
        return render_template("claim.html", token=token, error="This claim link is invalid or has expired."), 400

    if request.method == "GET":
        return render_template("claim.html", token=token, error=None)

    password = request.form.get("password") or ""
    if len(password) < auth.MIN_PASSWORD_LENGTH:
        return render_template("claim.html", token=token, error="Password must be at least 6 characters."), 400
    user = db.session.get(User, reset.user_id)
    if user is None:
        return render_template("claim.html", token=token, error="Account no longer exists."), 400
    auth.change_password(user, password)
    reset.used_at = utcnow()
    db.session.commit()
    auth.start_session(user)
    return redirect("/settings")


@bp.route("/settings", methods=["GET"])
@auth.require_user
def settings():
    uid = auth.user_id()
    profile = get_profile(uid)
    pantry = get_pantry(uid)
    user = g.get("user") or {}
    return render_template("settings.html", profile=profile, pantry=pantry, email=user.get("email"))


@bp.route("/settings/profile", methods=["POST"])
@auth.require_user
def update_profile():
    uid = auth.user_id()
    display_name = (request.form.get("display_name") or "").strip()
    if not display_name:
        raise AppError("Display name is required.")
    user = db.session.get(User, uid)
    user.display_name = display_name[:80]
    db.session.commit()
    return redirect("/settings")


@bp.route("/settings/pantry/add", methods=["POST"])
@auth.require_user
def add_pantry():
    from ..queries import normalize_item_name

    uid = auth.user_id()
    name = (request.form.get("name") or "").strip()
    if not name:
        raise AppError("Give the pantry item a name.")
    normalized = normalize_item_name(name)
    existing = (
        db.session.query(PantryItem)
        .filter(PantryItem.user_id == uid, PantryItem.normalized_name == normalized)
        .one_or_none()
    )
    if existing is None:
        db.session.add(PantryItem(user_id=uid, name=name, normalized_name=normalized))
    else:
        existing.name = name
    db.session.commit()
    return redirect("/settings")


@bp.route("/settings/pantry/remove", methods=["POST"])
@auth.require_user
def remove_pantry():
    uid = auth.user_id()
    item_id = request.form.get("id") or ""
    if not item_id:
        raise AppError("Missing pantry item.")
    db.session.query(PantryItem).filter(PantryItem.id == item_id, PantryItem.user_id == uid).delete()
    db.session.commit()
    return redirect("/settings")
