"""Shared fixtures: a fresh app backed by a per-test temporary SQLite database."""

from __future__ import annotations

import pytest

from skillet import create_app


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLET_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("APP_URL", "http://localhost:5000")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SKILLET_DB_PATH", raising=False)
    application = create_app()
    application.config.update(TESTING=True)
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


def signup(client, email="alice@example.com", password="secret12", name="Alice"):
    return client.post(
        "/signup",
        data={"email": email, "password": password, "display_name": name},
        follow_redirects=False,
    )


def login(client, email="alice@example.com", password="secret12"):
    return client.post("/login", data={"email": email, "password": password})


def post_form(client, url, **data):
    """POST like a browser form: include the session CSRF token when one was issued."""
    with client.session_transaction() as sess:
        csrf = sess.get("csrf")
    if csrf:
        data.setdefault("_csrf", csrf)
    return client.post(url, data=data)


def user_data(app, email="alice@example.com"):
    """Fetch a user row (dict) plus their cookbooks inside an app context."""
    from skillet.db import db
    from skillet.models import Cookbook, User

    with app.app_context():
        user = db.session.query(User).filter(User.email == email).one()
        cookbooks = db.session.query(Cookbook).filter(Cookbook.owner_id == user.id).all()
        return user.to_dict(), [c.to_dict() for c in cookbooks]
