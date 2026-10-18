"""Recipe CRUD plus cookbook-level authorization (owner / editor / viewer / stranger)."""

from __future__ import annotations

from conftest import post_form, signup, user_data

from skillet.db import db
from skillet.models import Cookbook, CookbookMember, Recipe, User


def make_recipe(client, cookbook_id, title="Pasta", ingredients="1 lb pasta\n2 cups sauce"):
    return post_form(
        client,
        "/recipes/save",
        cookbook_id=cookbook_id,
        title=title,
        ingredients_text=ingredients,
        instructions_text="1. Boil\n2. Sauce",
        servings="4",
        tags="italian, quick",
    )


def add_member(app, cookbook_id, user_email, role="viewer"):
    with app.app_context():
        owner = db.session.query(User).filter(User.email == "alice@example.com").one()
        member = db.session.query(User).filter(User.email == user_email).one()
        cookbook = db.session.get(Cookbook, cookbook_id)
        if cookbook.owner_id == member.id:
            return
        db.session.add(CookbookMember(cookbook_id=cookbook_id, user_id=member.id, role=role))
        db.session.commit()


def test_create_recipe_and_view(client, app):
    signup(client)
    _, cookbooks = user_data(app)
    response = make_recipe(client, cookbooks[0]["id"])
    assert response.status_code == 302
    recipe_id = response.location.rsplit("/", 1)[-1]
    with app.app_context():
        recipe = db.session.get(Recipe, recipe_id)
        assert recipe is not None
        assert recipe.title == "Pasta"
        assert recipe.ingredients[0]["name"] == "pasta"
        assert recipe.tags == ["italian", "quick"]
    page = client.get(f"/recipes/{recipe_id}")
    assert page.status_code == 200
    assert b"Pasta" in page.data


def test_edit_recipe(client, app):
    signup(client)
    _, cookbooks = user_data(app)
    recipe_id = make_recipe(client, cookbooks[0]["id"]).location.rsplit("/", 1)[-1]
    response = post_form(
        client, "/recipes/save", id=recipe_id, title="Better Pasta", ingredients_text="noodles"
    )
    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(Recipe, recipe_id).title == "Better Pasta"


def test_delete_recipe(client, app):
    signup(client)
    _, cookbooks = user_data(app)
    recipe_id = make_recipe(client, cookbooks[0]["id"]).location.rsplit("/", 1)[-1]
    response = post_form(client, f"/recipes/{recipe_id}/delete")
    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(Recipe, recipe_id) is None


def test_recipe_requires_title_and_ingredients(client, app):
    signup(client)
    _, cookbooks = user_data(app)
    response = post_form(client, "/recipes/save", cookbook_id=cookbooks[0]["id"], title="")
    assert response.status_code == 400
    response = post_form(
        client, "/recipes/save", cookbook_id=cookbooks[0]["id"], title="X", ingredients_text=""
    )
    assert response.status_code == 400


def test_viewer_member_cannot_create_or_edit(client, app):
    signup(client)
    _, cookbooks = user_data(app)
    cookbook_id = cookbooks[0]["id"]
    recipe_id = make_recipe(client, cookbook_id).location.rsplit("/", 1)[-1]

    viewer = app.test_client()
    signup(viewer, email="bob@example.com", name="Bob")
    add_member(app, cookbook_id, "bob@example.com", role="viewer")

    # Viewer can see the cookbook and recipe.
    assert viewer.get(f"/cookbooks/{cookbook_id}").status_code == 200
    assert viewer.get(f"/recipes/{recipe_id}").status_code == 200
    # But cannot create or edit.
    denied = make_recipe(viewer, cookbook_id, title="Bob's Recipe")
    assert denied.status_code == 403
    edit = post_form(viewer, "/recipes/save", id=recipe_id, title="Hijacked", ingredients_text="x")
    assert edit.status_code == 403
    delete = post_form(viewer, f"/recipes/{recipe_id}/delete")
    assert delete.status_code == 403


def test_editor_member_can_create(client, app):
    signup(client)
    _, cookbooks = user_data(app)
    cookbook_id = cookbooks[0]["id"]

    editor = app.test_client()
    signup(editor, email="carol@example.com", name="Carol")
    add_member(app, cookbook_id, "carol@example.com", role="editor")

    response = make_recipe(editor, cookbook_id, title="Carol's Stew")
    assert response.status_code == 302
    with app.app_context():
        assert db.session.query(Recipe).filter(Recipe.title == "Carol's Stew").count() == 1


def test_private_cookbook_hidden_from_strangers(client, app):
    signup(client)
    _, cookbooks = user_data(app)
    cookbook_id = cookbooks[0]["id"]

    stranger = app.test_client()
    signup(stranger, email="dave@example.com", name="Dave")

    assert stranger.get(f"/cookbooks/{cookbook_id}").status_code == 404
    listed = stranger.get("/cookbooks")
    assert cookbook_id.encode() not in listed.data
    # Only Dave's own default cookbook shows up.
    _, dave_cookbooks = user_data(app, email="dave@example.com")
    assert len(dave_cookbooks) == 1


def test_public_cookbook_visible_to_signed_in_strangers(client, app):
    signup(client)
    client.post(
        "/cookbooks",
        data={"name": "Public Eats", "is_private": "false", "description": "open to all"},
    )
    _, cookbooks = user_data(app)
    public = next(c for c in cookbooks if c["name"] == "Public Eats")
    assert public["is_private"] is False

    stranger = app.test_client()
    signup(stranger, email="erin@example.com", name="Erin")
    assert stranger.get(f"/cookbooks/{public['id']}").status_code == 200
    # Stranger can view but not edit.
    denied = make_recipe(stranger, public["id"])
    assert denied.status_code == 403
