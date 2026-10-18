"""Landing, auth, session, and settings routes."""

from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, redirect, render_template, request, session, url_for

from .. import auth
from ..queries import get_pantry, get_profile
from ..supabase import SupabaseError

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
    client = auth.make_client()
    try:
        payload = client.sign_in(email, password)
    except SupabaseError as exc:
        return render_template("login.html", next_url=next_url, error=exc.message), 400
    auth.set_session_tokens(payload)
    user = client.get_user()
    session["user_id"] = user.get("id") if user else None
    return redirect(next_url)


@bp.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        if g.get("user"):
            return redirect("/cookbooks")
        return render_template("signup.html", next_url=request.args.get("next", ""), error=None, notice=None)

    email = (request.form.get("email") or "").strip()
    password = request.form.get("password") or ""
    display_name = (request.form.get("display_name") or "").strip()
    next_url = safe_next(request.form.get("next"))
    if not email or not password:
        return (
            render_template("signup.html", next_url=next_url, error="Email and password are required.", notice=None),
            400,
        )
    if len(password) < 6:
        return (
            render_template("signup.html", next_url=next_url, error="Password must be at least 6 characters.", notice=None),
            400,
        )
    client = auth.make_client()
    name = display_name or email.split("@")[0]
    try:
        payload = client.sign_up(email, password, {"display_name": name})
    except SupabaseError as exc:
        return render_template("signup.html", next_url=next_url, error=exc.message, notice=None), 400
    if payload.get("access_token") and payload.get("refresh_token"):
        auth.set_session_tokens(payload)
        user = client.get_user()
        session["user_id"] = user.get("id") if user else None
        return redirect(next_url)
    return (
        render_template(
            "signup.html",
            next_url=next_url,
            error=None,
            notice="Check your email to confirm the account, then sign in.",
        ),
        200,
    )


@bp.route("/logout", methods=["POST"])
def logout():
    client = auth.db()
    try:
        client.sign_out()
    except SupabaseError:
        pass
    auth.clear_session()
    return redirect("/login")


@bp.route("/auth/callback")
def auth_callback():
    """Landing page for email-confirmation redirects (PKCE code or implicit tokens)."""
    return render_template("auth_callback.html", next_url=safe_next(request.args.get("next")))


@bp.route("/auth/session", methods=["POST"])
def auth_session():
    """Exchange a confirmation code or accept implicit tokens from the callback page."""
    data = request.get_json(silent=True) or {}
    code = data.get("code")
    access = data.get("access_token")
    refresh = data.get("refresh_token")
    next_url = safe_next(data.get("next"))
    client = auth.make_client()
    try:
        if code:
            payload = client.exchange_code_for_session(code, data.get("code_verifier"))
        elif access and refresh:
            payload = client.set_session(access, refresh)
            payload = {"access_token": access, "refresh_token": refresh}
        else:
            return jsonify({"error": "Missing confirmation code."}), 400
        auth.set_session_tokens(payload)
        user = client.get_user()
        session["user_id"] = user.get("id") if user else None
    except SupabaseError as exc:
        return jsonify({"error": exc.message}), 400
    return jsonify({"ok": True, "next": next_url})


@bp.route("/settings", methods=["GET"])
@auth.require_user
def settings():
    client = auth.db()
    uid = auth.user_id()
    profile = get_profile(client, uid)
    pantry = get_pantry(client, uid)
    user = g.get("user") or {}
    return render_template("settings.html", profile=profile, pantry=pantry, email=user.get("email"))


@bp.route("/settings/profile", methods=["POST"])
@auth.require_user
def update_profile():
    client = auth.db()
    uid = auth.user_id()
    display_name = (request.form.get("display_name") or "").strip()
    if not display_name:
        raise SupabaseError("Display name is required.")
    client.table("profiles").upsert({"id": uid, "display_name": display_name}, on_conflict="id").execute()
    return redirect("/settings")


@bp.route("/settings/pantry/add", methods=["POST"])
@auth.require_user
def add_pantry():
    from ..queries import normalize_item_name

    client = auth.db()
    uid = auth.user_id()
    name = (request.form.get("name") or "").strip()
    if not name:
        raise SupabaseError("Give the pantry item a name.")
    (
        client.table("pantry_items")
        .upsert(
            {"user_id": uid, "name": name, "normalized_name": normalize_item_name(name)},
            on_conflict="user_id,normalized_name",
        )
        .execute()
    )
    return redirect("/settings")


@bp.route("/settings/pantry/remove", methods=["POST"])
@auth.require_user
def remove_pantry():
    client = auth.db()
    uid = auth.user_id()
    item_id = request.form.get("id") or ""
    if not item_id:
        raise SupabaseError("Missing pantry item.")
    client.table("pantry_items").delete().eq("id", item_id).eq("user_id", uid).execute()
    return redirect("/settings")
