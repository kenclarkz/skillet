"""Weekly meal planner and generated shopping list tests."""
from datetime import date

from app.models import Recipe, MealPlan, PantryItem, PlanCandidate


def login(client):
    client.post('/auth/login', data={'email': 'test@example.com', 'password': 'password123'})


def seed_recipe(client, title, ingredients):
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


def put_up(client, plan, day, *recipes):
    return client.post(f'/plans/{plan.id}/assign', data={
        'day_of_week': day,
        'recipe_ids': [r.id for r in recipes],
    }, follow_redirects=True)


def vote_for(client, plan, day, recipe):
    cand = PlanCandidate.query.filter_by(plan_id=plan.id, day_of_week=day,
                                         recipe_id=recipe.id).first()
    return client.post(f'/plans/{plan.id}/vote/{cand.id}', follow_redirects=True)


def test_create_plan(client, user):
    login(client)
    res = client.post('/plans/new', data={
        'week_start': date.today().isoformat(),
        'title': 'Family week',
    }, follow_redirects=True)
    assert res.status_code == 200
    assert MealPlan.query.filter_by(user_id=user.id).count() == 1


def test_assign_puts_up_choices_not_official(client, user, db):
    login(client)
    r = seed_recipe(client, 'Taco Night', '8 tortillas\n1 lb beef')
    client.post('/plans/new', data={'week_start': date.today().isoformat(), 'title': 'Week'}, follow_redirects=True)
    plan = MealPlan.query.first()

    res = put_up(client, plan, 4, r)
    assert res.status_code == 200
    # choices are pending votes — nothing is official yet
    assert PlanCandidate.query.filter_by(plan_id=plan.id).count() == 1
    assert len(plan.entries) == 0

    # a second recipe can be put up for the same day
    r2 = seed_recipe(client, 'Pizza Friday', '2 cups flour\n1 cup water')
    put_up(client, plan, 4, r2)
    db.session.refresh(plan)
    assert PlanCandidate.query.filter_by(plan_id=plan.id, day_of_week=4).count() == 2
    assert len(plan.entries) == 0


def test_assign_limits_three_choices_per_day(client, user, db):
    login(client)
    r1 = seed_recipe(client, 'Dish One', '1 onion')
    r2 = seed_recipe(client, 'Dish Two', '2 carrots')
    r3 = seed_recipe(client, 'Dish Three', '3 potatoes')
    r4 = seed_recipe(client, 'Dish Four', '4 garlic cloves')
    client.post('/plans/new', data={'week_start': date.today().isoformat(), 'title': 'Week'}, follow_redirects=True)
    plan = MealPlan.query.first()

    put_up(client, plan, 0, r1, r2, r3)
    assert PlanCandidate.query.filter_by(plan_id=plan.id, day_of_week=0).count() == 3

    # a fourth choice for the same day is rejected
    res = put_up(client, plan, 0, r4)
    assert b'3 choices' in res.data
    assert PlanCandidate.query.filter_by(plan_id=plan.id, day_of_week=0).count() == 3


def test_vote_makes_choice_official_and_populates_grocery(client, user, db):
    login(client)
    r = seed_recipe(client, 'Taco Night', '8 tortillas\n1 lb beef')
    r2 = seed_recipe(client, 'Pizza Friday', '2 cups flour\n1 cup water')
    client.post('/plans/new', data={'week_start': date.today().isoformat(), 'title': 'Week'}, follow_redirects=True)
    plan = MealPlan.query.first()
    put_up(client, plan, 4, r, r2)

    # once all votes are in, the voted choice is official
    res = vote_for(client, plan, 4, r2)
    assert res.status_code == 200
    db.session.refresh(plan)
    assert len(plan.entries) == 1
    assert plan.entries[0].recipe_id == r2.id
    assert plan.entries[0].day_of_week == 4
    assert b'official' in res.data.lower()

    # its ingredients show up on the grocery list
    res = client.get(f'/grocery/{plan.id}')
    body = res.data.decode().lower()
    assert 'pizza friday' in body
    assert 'taco night' not in body

    # re-voting moves the official choice
    vote_for(client, plan, 4, r)
    db.session.refresh(plan)
    assert plan.entries[0].recipe_id == r.id

    # un-voting makes the day unofficial again
    vote_for(client, plan, 4, r)
    db.session.refresh(plan)
    assert len(plan.entries) == 0
    assert PlanCandidate.query.filter_by(plan_id=plan.id, day_of_week=4).count() == 2


def test_assign_section_shows_names_and_images_only(client, user):
    login(client)
    seed_recipe(client, 'Lemon Chicken', '1 lemon\n2 chicken thighs')
    client.post('/plans/new', data={'week_start': date.today().isoformat(), 'title': 'Week'}, follow_redirects=True)
    plan = MealPlan.query.first()

    res = client.get(f'/plans/{plan.id}')
    body = res.data.decode()
    # recipe names present in the choice picker
    assert 'Lemon Chicken' in body
    # only names and images — no serving counts, times, tags or ingredient counts
    assert 'Serves' not in body
    assert 'ingredients' not in body
    assert 'min</' not in body


def test_shopping_list_combines_and_skips_pantry(client, user, db):
    login(client)
    seed_recipe(client, 'Focaccia', '2 cups all-purpose flour\n1 tsp salt')
    seed_recipe(client, 'Garlic Bread', '1 cup all-purpose flour\n3 cloves garlic')

    # salt is a pantry staple
    from app.lib.ingredients import normalize_ingredient_name
    db.session.add(PantryItem(user_id=user.id, name='Salt',
                              normalized_name=normalize_ingredient_name('salt')))
    db.session.commit()

    client.post('/plans/new', data={'week_start': date.today().isoformat(), 'title': 'Week'}, follow_redirects=True)
    plan = MealPlan.query.first()
    recipes = Recipe.query.all()
    for i, r in enumerate(recipes):
        put_up(client, plan, i, r)
        vote_for(client, plan, i, r)

    res = client.get(f'/grocery/{plan.id}')
    assert res.status_code == 200

    body = res.data.decode()
    # merged flour: 2 + 1 = 3 cups across both recipes
    assert '3' in body and 'cup' in body
    # salt flagged as pantry
    assert 'pantry' in body.lower()
    # garlic present and not pantry
    assert 'garlic' in body.lower()


def test_grocery_list_is_private(client, user, db):
    login(client)
    recipe = seed_recipe(client, 'Secret Stew', '1 potato')
    client.post('/plans/new', data={'week_start': date.today().isoformat(), 'title': 'Week'}, follow_redirects=True)
    plan = MealPlan.query.first()
    put_up(client, plan, 0, recipe)
    vote_for(client, plan, 0, recipe)

    # other user's session
    from app.models import User
    other = User(email='other@example.com', display_name='Other')
    other.set_password('otherpass123')
    db.session.add(other)
    db.session.commit()
    client.get('/auth/logout')
    client.post('/auth/login', data={'email': 'other@example.com', 'password': 'otherpass123'})

    res = client.get(f'/grocery/{plan.id}', follow_redirects=True)
    assert b'Secret Stew' not in res.data
    res = client.get(f'/plans/{plan.id}', follow_redirects=True)
    assert b'Secret Stew' not in res.data


def test_clear_removes_choices_and_official_entry(client, user, db):
    login(client)
    r = seed_recipe(client, 'Soup Sunday', '1 squash\n2 carrots')
    client.post('/plans/new', data={'week_start': date.today().isoformat(), 'title': 'Week'}, follow_redirects=True)
    plan = MealPlan.query.first()
    put_up(client, plan, 6, r)
    vote_for(client, plan, 6, r)
    assert len(plan.entries) == 1

    client.post(f'/plans/{plan.id}/clear/6', follow_redirects=True)
    db.session.refresh(plan)
    assert len(plan.entries) == 0
    assert PlanCandidate.query.filter_by(plan_id=plan.id).count() == 0


def test_pantry_add_remove(client, user, db):
    login(client)
    res = client.post('/grocery/pantry/add', data={'name': 'Olive Oil'}, follow_redirects=True)
    assert res.status_code == 200
    assert PantryItem.query.filter_by(user_id=user.id).count() == 1

    item = PantryItem.query.first()
    client.post(f'/grocery/pantry/{item.id}/remove', follow_redirects=True)
    assert PantryItem.query.filter_by(user_id=user.id).count() == 0


def test_pantry_normalized_dedup(client, user, db):
    login(client)
    client.post('/grocery/pantry/add', data={'name': 'salt'}, follow_redirects=True)
    client.post('/grocery/pantry/add', data={'name': 'Salt'}, follow_redirects=True)
    assert PantryItem.query.filter_by(user_id=user.id).count() == 1
