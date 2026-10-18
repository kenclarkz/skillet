"""Session handling, login helpers, and CSRF protection.

Replaces the Supabase GoTrue integration: passwords are hashed locally with
werkzeug (scrypt) and the signed Flask session cookie carries the user id.
"""

from __future__ import annotations

import functools
import hmac
import secrets
from typing import Any, Callable

from flask import abort, current_app, g, jsonify, redirect, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from .db import db
from .errors import AppError
from .models import User, utcnow

# Legacy Supabase cookies (cleared on logout so old sessions expire cleanly).
ACCESS_COOKIE = "skillet_access"
REFRESH_COOKIE = "skillet_refresh"

PROTECTED_PREFIXES = ("/cookbooks", "/recipes", "/import", "/plans", "/grocery", "/settings")
AUTH_PAGES = ("/login", "/signup")

MIN_PASSWORD_LENGTH = 6


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(user: User, password: str) -> bool:
    if not user.password_hash:
        return False
    return check_password_hash(user.password_hash, password)


def find_user_by_email(email: str) -> User | None:
    return db.session.query(User).filter(User.email == email.strip().lower()).one_or_none()


def create_user(email: str, password: str, display_name: str | None = None) -> User:
    email = email.strip().lower()
    name = (display_name or "").strip() or email.split("@")[0]
    user = User(email=email, password_hash=hash_password(password), display_name=name[:80])
    db.session.add(user)
    db.session.flush()
    return user


def is_protected(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in PROTECTED_PREFIXES)


def is_auth_page(path: str) -> bool:
    return path in AUTH_PAGES


def _queue_cookie(response_setter: Callable[[str, str | None], None]) -> None:
    g.setdefault("cookie_ops", []).append(response_setter)


def start_session(user: User) -> None:
    """Sign a user in: remember their id in the signed session cookie."""
    session.permanent = True
    session.clear()
    session["user_id"] = user.id


def clear_session() -> None:
    secure = request.is_secure
    _queue_cookie(lambda resp: resp.delete_cookie(ACCESS_COOKIE, samesite="Lax", secure=secure))
    _queue_cookie(lambda resp: resp.delete_cookie(REFRESH_COOKIE, samesite="Lax", secure=secure))
    session.clear()


def apply_cookie_ops(response):
    for op in g.get("cookie_ops", []):
        op(response)
    g.cookie_ops = []
    return response


def load_user() -> None:
    """before_request hook: attach g.user from the signed session."""
    g.user = None
    g.cookie_ops = []
    user_id = session.get("user_id")
    if not user_id:
        return
    user = db.session.get(User, user_id)
    if user is None:
        session.clear()
        return
    g.user = {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "must_set_password": not bool(user.password_hash),
    }


def current_user_row() -> User | None:
    user_id = g.get("user") and g.user.get("id")
    return db.session.get(User, user_id) if user_id else None


def user_id() -> str | None:
    user = g.get("user")
    return user.get("id") if user else None


def require_user(view: Callable) -> Callable:
    @functools.wraps(view)
    def wrapper(*args: Any, **kwargs: Any):
        if g.get("user") is None:
            next_url = request.full_path if request.query_string else request.path
            return redirect(f"/login?next={next_url}")
        return view(*args, **kwargs)

    return wrapper


def api_require_user(view: Callable) -> Callable:
    @functools.wraps(view)
    def wrapper(*args: Any, **kwargs: Any):
        if g.get("user") is None:
            return jsonify({"error": "Sign in required."}), 401
        return view(*args, **kwargs)

    return wrapper


def change_password(user: User, password: str) -> None:
    user.password_hash = hash_password(password)
    db.session.add(user)


# --- CSRF -----------------------------------------------------------------


def csrf_token() -> str:
    token = session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf"] = token
    return token


def validate_csrf() -> None:
    if request.method not in ("POST", "PATCH", "PUT", "DELETE"):
        return
    expected = session.get("csrf")
    if not expected:
        return  # fresh session with no issued token yet
    supplied = request.form.get("_csrf") or request.headers.get("X-CSRF-Token") or ""
    if not hmac.compare_digest(str(supplied), expected):
        abort(400, description="Invalid or missing CSRF token.")


__all__ = [
    "AppError",
    "MIN_PASSWORD_LENGTH",
    "api_require_user",
    "apply_cookie_ops",
    "change_password",
    "clear_session",
    "create_user",
    "csrf_token",
    "find_user_by_email",
    "hash_password",
    "is_auth_page",
    "is_protected",
    "load_user",
    "require_user",
    "start_session",
    "utcnow",
    "user_id",
    "validate_csrf",
    "verify_password",
]
