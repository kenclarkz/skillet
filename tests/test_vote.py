"""Guest voting via QR code: share management, ballot, vote recording, standings."""
from datetime import date

from app.models import MealPlan, PlanShare, PlanVote, Recipe, User


def login(client):
    client.post('/auth/login', data={'email': 'test@example.com', 'password': 'password123'})


def seed_recipe(client, title, ingredients='1 cup flour'):
    client.post('/recipes/new', data={
        'title': title,
        'description': '',
        'prep_minutes': '5',
        'cook_minutes': '10',
        'servings': '4',
        'tags': 'test',
        'ingredients': ingredients,
        'instructions': 'Do the thing',
        'source_url': '',
    }, follow_redirects=True)
    return Recipe.query.filter_by(title=title).first()


def setup_owner_plan(client, db, titles=('Taco Night', 'Pizza Friday')):
    """Log in, seed recipes, create a plan with the first recipe on the menu,
    and attach a share token — ready for guest traffic."""
    login(client)
    recipes = [seed_recipe(client, t) for t in titles]
    client.post('/plans/new', data={
        'week_start': date.today().isoformat(),
        'title': 'Week',
    }, follow_redirects=True)
    plan = MealPlan.query.first()
    client.post(f'/plans/{plan.id}/assign', data={'recipe_id': recipes[0].id, 'day_of_week': 0})
    share = PlanShare(plan_id=plan.id, token='guest-token-abc')
    db.session.add(share)
    db.session.commit()
    return plan, recipes, share


def test_share_requires_login(client, user, db):
    plan = MealPlan(user_id=user.id, week_start=date.today())
    db.session.add(plan)
    db.session.commit()

    res = client.post(f'/plans/{plan.id}/share')
    assert res.status_code == 302
    assert '/auth/login' in res.headers['Location']
    assert PlanShare.query.count() == 0


def test_share_rejects_other_user(client, user, db):
    plan = MealPlan(user_id=user.id, week_start=date.today())
    db.session.add(plan)
    other = User(email='other@example.com', display_name='Other')
    other.set_password('otherpass123')
    db.session.add(other)
    db.session.commit()

    client.post('/auth/login', data={'email': 'other@example.com', 'password': 'otherpass123'})
    res = client.post(f'/plans/{plan.id}/share', follow_redirects=True)
    assert PlanShare.query.count() == 0
    assert b'Not authorized' in res.data


def test_enable_share_shows_qr_and_link(client, user, db):
    plan, recipes, share = setup_owner_plan(client, db)
    existing = PlanShare.query.filter_by(plan_id=plan.id).one()
    db.session.delete(existing)
    db.session.commit()

    res = client.post(f'/plans/{plan.id}/share', follow_redirects=True)
    assert res.status_code == 200
    body = res.data.decode()
    new_share = PlanShare.query.filter_by(plan_id=plan.id).one()
    assert '/vote/qr/' in body
    assert f'/vote/{new_share.token}' in body

    # enabling again reuses the same token instead of minting a new link
    client.post(f'/plans/{plan.id}/share')
    assert PlanShare.query.filter_by(plan_id=plan.id).count() == 1
    assert PlanShare.query.filter_by(plan_id=plan.id).one().token == new_share.token


def test_qr_png_served_and_404_for_unknown(client, user, db):
    plan, recipes, share = setup_owner_plan(client, db)

    res = client.get(f'/vote/qr/{share.token}.png')
    assert res.status_code == 200
    assert res.mimetype == 'image/png'
    assert res.data[:4] == b'\x89PNG'

    assert client.get('/vote/qr/unknown-token.png').status_code == 404


def test_disable_share_kills_link(app, client, user, db):
    plan, recipes, share = setup_owner_plan(client, db)
    guest = app.test_client()

    assert guest.get(f'/vote/{share.token}').status_code == 200

    res = client.post(f'/plans/{plan.id}/share/delete', follow_redirects=True)
    assert res.status_code == 200
    assert PlanShare.query.count() == 0
    assert guest.get(f'/vote/{share.token}').status_code == 404


def test_guest_ballot_needs_no_login_and_lists_both_sections(app, client, user, db):
    plan, recipes, share = setup_owner_plan(client, db)
    guest = app.test_client()

    res = guest.get(f'/vote/{share.token}')
    assert res.status_code == 200
    body = res.data.decode()
    # menu suggestion (assigned) and the other recipe in the "suggest" select
    assert 'Taco Night' in body
    assert 'Pizza Friday' in body
    assert 'Your name' in body
    assert '#2A9D8F' in body  # color palette rendered


def test_unknown_token_is_404(app):
    guest = app.test_client()
    assert guest.get('/vote/nope').status_code == 404
    res = guest.post('/vote/nope', data={'voter_name': 'Sam', 'color': '#E4572E'})
    assert res.status_code == 404


def test_guest_vote_recorded_and_standings_appear_after(app, client, user, db):
    plan, recipes, share = setup_owner_plan(client, db)
    guest = app.test_client()

    # standings hidden until this guest votes
    before = guest.get(f'/vote/{share.token}').data.decode()
    assert 'Standings' not in before

    res = guest.post(f'/vote/{share.token}', data={
        'voter_name': 'Sam',
        'color': '#E4572E',
        'recipe_id': str(recipes[0].id),
    }, follow_redirects=True)
    assert res.status_code == 200
    body = res.data.decode()
    assert 'Vote recorded for' in body and 'Taco Night' in body
    assert 'Standings' in body
    assert 'Sam' in body

    vote = PlanVote.query.one()
    assert vote.plan_id == plan.id
    assert vote.recipe_id == recipes[0].id
    assert vote.voter_name == 'Sam'
    assert vote.color == '#E4572E'


def test_revote_replaces_same_name_case_insensitive(app, client, user, db):
    plan, recipes, share = setup_owner_plan(client, db)
    guest = app.test_client()

    guest.post(f'/vote/{share.token}', data={
        'voter_name': 'Sam', 'color': '#E4572E', 'recipe_id': str(recipes[0].id)})
    guest.post(f'/vote/{share.token}', data={
        'voter_name': 'sam', 'color': '#3D85C6', 'recipe_id': str(recipes[1].id)})

    vote = PlanVote.query.one()
    assert vote.recipe_id == recipes[1].id
    assert vote.color == '#3D85C6'
    assert vote.voter_name == 'sam'


def test_guest_can_suggest_recipe_not_on_menu(app, client, user, db):
    plan, recipes, share = setup_owner_plan(client, db)
    guest = app.test_client()

    guest.post(f'/vote/{share.token}', data={
        'voter_name': 'Alex', 'color': '#57AB5A', 'other_recipe_id': str(recipes[1].id)})
    assert PlanVote.query.one().recipe_id == recipes[1].id


def test_vote_rejects_foreign_users_recipe(app, client, user, db):
    plan, recipes, share = setup_owner_plan(client, db)
    other = User(email='stranger@example.com', display_name='Stranger')
    other.set_password('strangerpass123')
    db.session.add(other)
    db.session.commit()
    foreign = Recipe(user_id=other.id, title='Not Your Recipe', instructions='x')
    db.session.add(foreign)
    db.session.commit()
    guest = app.test_client()

    res = guest.post(f'/vote/{share.token}', data={
        'voter_name': 'Eve', 'color': '#9B59B6', 'recipe_id': str(foreign.id)},
        follow_redirects=True)
    assert PlanVote.query.count() == 0
    assert b'Choose one of the recipes' in res.data


def test_vote_rejects_bad_color_missing_name_and_missing_pick(app, client, user, db):
    plan, recipes, share = setup_owner_plan(client, db)
    guest = app.test_client()

    # bad color
    res = guest.post(f'/vote/{share.token}', data={
        'voter_name': 'Sam', 'color': '#000000', 'recipe_id': str(recipes[0].id)},
        follow_redirects=True)
    assert PlanVote.query.count() == 0
    assert b'Pick a color' in res.data

    # missing name
    res = guest.post(f'/vote/{share.token}', data={
        'color': '#E4572E', 'recipe_id': str(recipes[0].id)}, follow_redirects=True)
    assert PlanVote.query.count() == 0
    assert res.status_code == 200

    # no recipe picked
    res = guest.post(f'/vote/{share.token}', data={
        'voter_name': 'Sam', 'color': '#E4572E'}, follow_redirects=True)
    assert PlanVote.query.count() == 0
    assert b'Choose one of the recipes' in res.data


def test_owner_plan_view_shows_tally_with_voter_chips(app, client, user, db):
    plan, recipes, share = setup_owner_plan(client, db)
    guest = app.test_client()
    guest.post(f'/vote/{share.token}', data={
        'voter_name': 'Sam', 'color': '#E4572E', 'recipe_id': str(recipes[0].id)})

    client.get('/auth/logout')
    login(client)
    res = client.get(f'/plans/{plan.id}')
    body = res.data.decode()
    assert 'Votes so far' in body
    assert 'Taco Night' in body
    assert 'Sam' in body
    assert '#E4572E' in body
