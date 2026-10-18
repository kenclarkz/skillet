"""Session handling, login helpers, and CSRF protection."""

from __future__ import annotations

import functools
import hmac
import secrets
import time
from typing import Any, Callable

from flask import abort, current_app, g, jsonify, redirect, request, session

from .supabase import SupabaseClient, SupabaseError, session_expires_at

ACCESS_COOKIE = "skillet_access"
REFRESH_COOKIE = "skillet_refresh"

PROTECTED_PREFIXES = ("/cookbooks", "/recipes", "/import", "/plans", "/grocery", "/settings")
AUTH_PAGES = ("/login", "/signup")

COOKIE_MAX_AGE = 60 * 60 * 24 * 30


def is_protected(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in PROTECTED_PREFIXES)


def is_auth_page(path: str) -> bool:
    return path in AUTH_PAGES


def make_client(access_token: str | None = None, refresh_token: str | None = None) -> SupabaseClient:
    cfg = current_app.config["SKILLET"]
    return SupabaseClient(cfg.SUPABASE_URL, cfg.SUPABASE_ANON_KEY, access_token, refresh_token)


def make_anon_client() -> SupabaseClient:
    return make_client()


def _queue_cookie(response_setter: Callable[[str, str | None], None]) -> None:
    g.setdefault("cookie_ops", []).append(response_setter)


def set_session_tokens(payload: dict[str, Any]) -> None:
    """Remember tokens in HttpOnly cookies; expiry metadata in the signed session."""
    access = payload.get("access_token")
    refresh = payload.get("refresh_token")
    if not access or not refresh:
        raise SupabaseError("Sign-in response did not include session tokens.")
    secure = request.is_secure
    _queue_cookie(
        lambda resp: resp.set_cookie(
            ACCESS_COOKIE, access, httponly=True, samesite="Lax", secure=secure, max_age=COOKIE_MAX_AGE
        )
    )
    _queue_cookie(
        lambda resp: resp.set_cookie(
            REFRESH_COOKIE, refresh, httponly=True, samesite="Lax", secure=secure, max_age=COOKIE_MAX_AGE
        )
    )
    session.permanent = True
    session["expires_at"] = session_expires_at(payload)


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


def current_access_token() -> str | None:
    return request.cookies.get(ACCESS_COOKIE) or None


def current_refresh_token() -> str | None:
    return request.cookies.get(REFRESH_COOKIE) or None


def refresh_client_tokens(client: SupabaseClient) -> bool:
    """Refresh the session using the refresh cookie. Returns True on success."""
    refresh = current_refresh_token()
    if not refresh:
        return False
    try:
        payload = client.refresh_session(refresh)
    except SupabaseError:
        return False
    access = payload.get("access_token")
    new_refresh = payload.get("refresh_token")
    if not access or not new_refresh:
        return False
    client.access_token = access
    client.refresh_token = new_refresh
    set_session_tokens(payload)
    return True


def load_user() -> None:
    """before_request hook: attach g.user / g.client, refreshing as needed."""
    g.user = None
    g.client = None
    g.cookie_ops = []
    if not current_app.config["SKILLET"].is_configured:
        return
    access = current_access_token()
    refresh = current_refresh_token()
    if not access and not refresh:
        return
    client = make_client(access, refresh)
    expires_at = session.get("expires_at")
    needs_refresh = not access or (expires_at and time.time() > float(expires_at) - 30)
    if needs_refresh and refresh:
        if refresh_client_tokens(client):
            access = client.access_token
        else:
            client.access_token = None
            client.refresh_token = None
    if client.access_token:
        user = client.get_user()
        if user is None and client.refresh_token:
            if refresh_client_tokens(client):
                user = client.get_user()
        if user:
            g.user = user
            g.client = client
            session["user_id"] = user.get("id")
            return
    # Tokens are stale — clear them so route guards see a signed-out visitor.
    g.client = make_client()
    clear_session()


def user_id() -> str | None:
    user = g.get("user")
    return user.get("id") if user else None


def db() -> SupabaseClient:
    """User-scoped client for table access (RLS enforced with their JWT)."""
    client = g.get("client")
    if client is None:
        client = make_client()
        g.client = client
    return client


def anon_db() -> SupabaseClient:
    """Anonymous client for public RPCs (guest voting)."""
    return make_anon_client()


def require_user(view: Callable) -> Callable:
    @functools.wraps(view)
    def wrapper(*args: Any, **kwargs: Any):
        if not current_app.config["SKILLET"].is_configured:
            return redirect("/")
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
