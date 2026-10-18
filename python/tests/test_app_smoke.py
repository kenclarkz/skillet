"""Boot-level smoke tests: the app starts, routes resolve, guards work. No network."""

from __future__ import annotations

import pytest

from skillet import create_app


def test_landing_page_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Skillet" in response.data


def test_login_and_signup_pages(client):
    assert client.get("/login").status_code == 200
    assert client.get("/signup").status_code == 200


def test_protected_pages_redirect_to_login(client):
    response = client.get("/cookbooks")
    assert response.status_code == 302
    assert response.location.startswith("/login")


def test_unknown_route_shows_404_page(client):
    response = client.get("/definitely-not-a-page")
    assert response.status_code == 404


def test_retailers_api_is_public_json(client):
    response = client.get("/api/retailers")
    assert response.status_code == 200
    payload = response.get_json()
    assert "retailers" in payload
    ids = {r["id"] for r in payload["retailers"]}
    assert {"walmart", "instacart"} <= ids


def test_import_api_requires_sign_in(client):
    response = client.post("/api/import", json={"url": "https://example.com/recipe"})
    assert response.status_code == 302  # page guard redirects to login
    assert "/login" in response.location


def test_vote_api_missing_token_is_a_clean_400(client):
    response = client.get("/api/vote/ballot")
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_vote_page_renders_for_any_token(client):
    response = client.get("/vote/some-token")
    assert response.status_code == 200
    assert b"ballot" in response.data


def test_csrf_is_enforced_once_a_token_is_issued(client):
    client.get("/login")  # establish session + CSRF token
    response = client.post("/logout")
    assert response.status_code == 400
    assert b"CSRF" in response.data


def test_logout_without_session_redirects(client):
    response = client.post("/logout")
    assert response.status_code == 302
    assert response.location == "/login"


def test_static_assets_served(client):
    assert client.get("/static/css/skillet.css").status_code == 200
    assert client.get("/static/js/voter.js").status_code == 200
    assert client.get("/static/favicon.ico").status_code == 200


def test_qr_endpoint_returns_svg(client):
    response = client.get("/api/qr?value=https%3A%2F%2Fexample.com%2Fvote%2Fabc")
    assert response.status_code == 200
    assert b"<svg" in response.data


def test_unconfigured_app_shows_setup_notice(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("NEXT_PUBLIC_SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("NEXT_PUBLIC_SUPABASE_ANON_KEY", raising=False)
    application = create_app()
    application.config.update(TESTING=True)
    unconfigured = application.test_client()
    response = unconfigured.get("/")
    assert response.status_code == 200
    assert b"Supabase" in response.data
    # Protected routes send you to setup, not login.
    redirect = unconfigured.get("/cookbooks")
    assert redirect.status_code == 302
    assert redirect.location == "/"
