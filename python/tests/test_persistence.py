"""SQLite persistence: data survives a full app restart (the Supabase→SQLite core guarantee)."""

from __future__ import annotations

from conftest import login, signup, user_data

from skillet import create_app
from skillet.db import db
from skillet.models import Recipe


def test_data_survives_app_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLET_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("APP_URL", "http://localhost:5000")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")

    app1 = create_app()
    app1.config.update(TESTING=True)
    client1 = app1.test_client()
    signup(client1, email="persist@example.com", name="Persist")
    _, cookbooks = user_data(app1, email="persist@example.com")
    response = client1.post(
        "/recipes/save",
        data={
            "cookbook_id": cookbooks[0]["id"],
            "title": "Survives Restarts Stew",
            "ingredients_text": "3 potatoes",
        },
    )
    assert response.status_code == 302
    recipe_id = response.location.rsplit("/", 1)[-1]

    # Simulate a process restart: brand-new app, same data directory.
    app2 = create_app()
    app2.config.update(TESTING=True)
    client2 = app2.test_client()
    with app2.app_context():
        recipe = db.session.get(Recipe, recipe_id)
        assert recipe is not None
        assert recipe.title == "Survives Restarts Stew"
    # The user (and password hash) also survived — logging in on the "new server" works.
    assert login(client2, email="persist@example.com", password="secret12").status_code == 302
    page = client2.get(f"/recipes/{recipe_id}")
    assert page.status_code == 200
    assert b"Survives Restarts Stew" in page.data


def test_cascading_delete_removes_children(app, client):
    signup(client)
    _, cookbooks = user_data(app)
    cookbook_id = cookbooks[0]["id"]
    response = client.post(
        "/recipes/save",
        data={"cookbook_id": cookbook_id, "title": "Doomed", "ingredients_text": "1 cup fate"},
    )
    recipe_id = response.location.rsplit("/", 1)[-1]
    client.post(f"/plans/create", data={"cookbook_id": cookbook_id, "week_start": "2026-10-19"})
    with app.app_context():
        from skillet.models import WeeklyPlan

        plan = db.session.query(WeeklyPlan).first()
        client.post(f"/plans/{plan.id}/recipes", data={"recipe_id": recipe_id})

    client.post(f"/cookbooks/{cookbook_id}/delete")
    with app.app_context():
        assert db.session.get(Recipe, recipe_id) is None
        assert db.session.query(WeeklyPlan).count() == 0
