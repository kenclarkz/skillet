"""Authentication: local signup/login/logout, password hashing, claim flow."""

from __future__ import annotations

from conftest import login, signup, user_data

from skillet.db import db
from skillet.models import PasswordResetToken, User, new_id, utcnow


def test_signup_creates_user_and_default_cookbook(client, app):
    response = signup(client)
    assert response.status_code == 302
    assert response.location == "/cookbooks"
    user, cookbooks = user_data(app)
    assert user["email"] == "alice@example.com"
    assert user["display_name"] == "Alice"
    assert len(cookbooks) == 1
    assert cookbooks[0]["name"] == "Alice's Cookbook"
    assert cookbooks[0]["is_private"] is True


def test_login_logout_roundtrip(client, app):
    signup(client)
    client.get("/logout", follow_redirects=False)  # ensure session exists
    client.post("/logout")
    response = login(client)
    assert response.status_code == 302
    assert response.location == "/cookbooks"
    page = client.get("/cookbooks")
    assert page.status_code == 200
    assert b"Alice" in page.data


def test_login_wrong_password(client):
    signup(client)
    client.post("/logout")
    response = login(client, password="wrong-password")
    assert response.status_code == 400
    assert b"Wrong email or password" in response.data


def test_duplicate_signup_rejected(client):
    assert signup(client).status_code == 302
    client.post("/logout")
    response = signup(client)
    assert response.status_code == 400
    assert b"already registered" in response.data


def test_short_password_rejected(client):
    response = signup(client, password="abc")
    assert response.status_code == 400
    assert b"at least 6 characters" in response.data


def test_password_hashed_not_plaintext(client, app):
    signup(client)
    with app.app_context():
        user = db.session.query(User).filter(User.email == "alice@example.com").one()
        assert user.password_hash
        assert "secret12" not in user.password_hash


def test_protected_route_requires_login(client):
    response = client.get("/cookbooks")
    assert response.status_code == 302
    assert response.location.startswith("/login")


def test_claim_flow_sets_password(client, app):
    """Imported Supabase users (password_hash=None) claim via one-time token."""
    with app.app_context():
        user = User(email="imported@example.com", password_hash=None, display_name="Imported")
        db.session.add(user)
        db.session.flush()
        token = new_id()
        db.session.add(
            PasswordResetToken(token=token, user_id=user.id, expires_at=utcnow().replace(year=2030))
        )
        db.session.commit()

    # Login is blocked until claimed.
    blocked = login(client, email="imported@example.com", password="newpassword")
    assert blocked.status_code == 400
    assert b"claim link" in blocked.data

    # Claim page renders, then POST sets the password and signs in.
    page = client.get(f"/claim/{token}")
    assert page.status_code == 200
    with client.session_transaction() as sess:
        csrf = sess.get("csrf")
    response = client.post(f"/claim/{token}", data={"password": "newpassword", "_csrf": csrf})
    assert response.status_code == 302
    assert response.location == "/settings"

    client.post("/logout")
    assert login(client, email="imported@example.com", password="newpassword").status_code == 302

    # Token is single-use.
    client.post("/logout")
    reused = client.post(f"/claim/{token}", data={"password": "anotherpass", "_csrf": csrf})
    assert reused.status_code == 400


def test_invalid_claim_token_rejected(client):
    response = client.get("/claim/not-a-real-token")
    assert response.status_code == 400
    assert b"invalid" in response.data.lower()
