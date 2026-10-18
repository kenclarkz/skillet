"""Week plans, member invites, and guest voting (ballot + cast)."""

from __future__ import annotations

from conftest import post_form, signup, user_data

from skillet.db import db
from skillet.models import CookbookMember, Invite, Recipe, WeeklyPlan


def create_recipe(client, cookbook_id, title):
    response = post_form(
        client, "/recipes/save", cookbook_id=cookbook_id, title=title, ingredients_text="1 onion"
    )
    assert response.status_code == 302, response.data[:300]
    return response.location.rsplit("/", 1)[-1]


def setup_plan(client, app, week_start="2026-10-19"):
    """Create two recipes and a plan with both on the ballot."""
    signup(client)
    _, cookbooks = user_data(app)
    cookbook_id = cookbooks[0]["id"]
    r1 = create_recipe(client, cookbook_id, "Chili")
    r2 = create_recipe(client, cookbook_id, "Curry")
    response = client.post(
        "/plans/create",
        data={"cookbook_id": cookbook_id, "week_start": week_start, "title": "Dinner week"},
    )
    plan_id = response.location.rsplit("/", 1)[-1]
    client.post(f"/plans/{plan_id}/recipes", data={"recipe_id": r1})
    client.post(f"/plans/{plan_id}/recipes", data={"recipe_id": r2})
    return cookbook_id, plan_id, r1, r2


def create_vote_invite(client, app, plan_id=None):
    with app.app_context():
        if plan_id:
            cookbook_id = db.session.get(WeeklyPlan, plan_id).cookbook_id
        else:
            _, cookbooks = user_data(app)
            cookbook_id = cookbooks[0]["id"]
    data = {"kind": "vote", "cookbook_id": cookbook_id}
    if plan_id:
        data["plan_id"] = plan_id
    client.post("/invites/create", data=data)
    with app.app_context():
        invite = (
            db.session.query(Invite)
            .filter(Invite.kind == "vote")
            .order_by(Invite.created_at.desc())
            .first()
        )
        return invite.token


def test_create_plan_with_recipes(client, app):
    cookbook_id, plan_id, r1, r2 = setup_plan(client, app)
    with app.app_context():
        plan = db.session.get(WeeklyPlan, plan_id)
        assert plan is not None
        assert plan.week_start.isoformat() == "2026-10-19"
    page = client.get(f"/plans/{plan_id}")
    assert page.status_code == 200
    assert b"Chili" in page.data
    assert b"Curry" in page.data


def test_member_invite_join(client, app):
    signup(client)
    _, cookbooks = user_data(app)
    cookbook_id = cookbooks[0]["id"]
    client.post("/invites/create", data={"cookbook_id": cookbook_id, "kind": "member", "role": "editor"})
    with app.app_context():
        token = db.session.query(Invite).filter(Invite.kind == "member").one().token

    guest = app.test_client()
    signup(guest, email="frank@example.com", name="Frank")
    response = guest.get(f"/invite/{token}")
    assert response.status_code == 200
    with app.app_context():
        from skillet.models import User

        frank = db.session.query(User).filter(User.email == "frank@example.com").one()
        member = db.session.get(CookbookMember, {"cookbook_id": cookbook_id, "user_id": frank.id})
        assert member is not None
        assert member.role == "editor"
    # Frank can now see the cookbook and add recipes.
    assert guest.get(f"/cookbooks/{cookbook_id}").status_code == 200
    assert create_recipe(guest, cookbook_id, "Frank's Soup")


def test_revoked_invite_rejected(client, app):
    signup(client)
    _, cookbooks = user_data(app)
    cookbook_id = cookbooks[0]["id"]
    client.post("/invites/create", data={"cookbook_id": cookbook_id, "kind": "member", "role": "viewer"})
    with app.app_context():
        invite = db.session.query(Invite).filter(Invite.kind == "member").one()
        token = invite.token
        invite_id = invite.id
    client.post(f"/invites/{invite_id}/revoke", data={"cookbook_id": cookbook_id})

    guest = app.test_client()
    signup(guest, email="grace@example.com", name="Grace")
    response = guest.get(f"/invite/{token}")
    assert response.status_code == 200
    assert b"This invite" in response.data


def test_guest_ballot_and_vote(client, app):
    _, plan_id, r1, r2 = setup_plan(client, app)
    token = create_vote_invite(client, app, plan_id=plan_id)

    guest = app.test_client()
    page = guest.get(f"/vote/{token}")
    assert page.status_code == 200

    ballot = guest.get(f"/api/vote/ballot?token={token}")
    assert ballot.status_code == 200
    payload = ballot.get_json()["ballot"]
    assert payload["plan"]["id"] == plan_id
    titles = {r["title"] for r in payload["recipes"]}
    assert titles == {"Chili", "Curry"}

    with guest.session_transaction() as sess:
        csrf = sess.get("csrf")
    cast = guest.post(
        "/api/vote/cast",
        json={
            "plan_id": plan_id,
            "recipe_id": r1,
            "value": 1,
            "voter_key": "guest-abc",
            "voter_name": "Guesty",
            "invite_token": token,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert cast.status_code == 200

    # Tallies update and the voter's choice is remembered.
    ballot2 = guest.get(f"/api/vote/ballot?token={token}&voter_key=guest-abc").get_json()["ballot"]
    assert ballot2["tallies"][r1]["up"] == 1
    assert ballot2["my_votes"][r1] == 1


def test_vote_requires_valid_invite(client, app):
    _, plan_id, r1, _ = setup_plan(client, app)
    guest = app.test_client()
    response = guest.post(
        "/api/vote/cast",
        json={
            "plan_id": plan_id,
            "recipe_id": r1,
            "value": 1,
            "voter_key": "nobody",
            "voter_name": "Nobody",
            "invite_token": "bogus",
        },
    )
    assert response.status_code == 403


def test_expired_vote_invite_rejected(client, app):
    _, plan_id, _, _ = setup_plan(client, app)
    token = create_vote_invite(client, app, plan_id=plan_id)
    with app.app_context():
        invite = db.session.query(Invite).filter(Invite.token == token).one()
        from datetime import timedelta

        from skillet.models import utcnow

        invite.expires_at = utcnow() - timedelta(days=1)
        db.session.commit()
    response = client.get(f"/api/vote/ballot?token={token}")
    assert response.status_code == 400


def test_select_top_and_build_grocery(client, app):
    _, plan_id, r1, r2 = setup_plan(client, app)
    token = create_vote_invite(client, app, plan_id=plan_id)

    guest = app.test_client()
    guest.get(f"/vote/{token}")  # issues csrf
    with guest.session_transaction() as sess:
        csrf = sess.get("csrf")
    guest.post(
        "/api/vote/cast",
        json={
            "plan_id": plan_id,
            "recipe_id": r1,
            "value": 1,
            "voter_key": "g1",
            "voter_name": "G",
            "invite_token": token,
        },
        headers={"X-CSRF-Token": csrf},
    )

    response = client.post(f"/plans/{plan_id}/select-top", data={"slots": "5"})
    assert response.status_code == 302
    with app.app_context():
        from skillet.models import PlanRecipe

        rows = db.session.query(PlanRecipe).filter(PlanRecipe.plan_id == plan_id).all()
        selected = {row.recipe_id for row in rows if row.selected}
        assert selected == {r1}

    grocery = client.post(f"/plans/{plan_id}/build-grocery")
    assert grocery.status_code == 302
    with app.app_context():
        from skillet.models import GroceryItem, GroceryList

        grocery_list = db.session.query(GroceryList).filter(GroceryList.plan_id == plan_id).one()
        items = db.session.query(GroceryItem).filter(GroceryItem.list_id == grocery_list.id).all()
        names = {item.normalized_name for item in items}
        assert "onion" in names


def test_plan_hidden_from_strangers(client, app):
    _, plan_id, _, _ = setup_plan(client, app)
    stranger = app.test_client()
    signup(stranger, email="zoe@example.com", name="Zoe")
    assert stranger.get(f"/plans/{plan_id}").status_code == 404
