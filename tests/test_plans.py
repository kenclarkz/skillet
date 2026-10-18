"""Weekly meal planner and generated shopping list tests."""
from datetime import date

from app.models import Recipe, MealPlan, PantryItem


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


def test_create_plan(client, user):
    login(client)
    res = client.post('/plans/new', data={
        'week_start': date.today().isoformat(),
        'title': 'Family week',
    }, follow_redirects=True)
    assert res.status_code == 200
    assert MealPlan.query.filter_by(user_id=user.id).count() == 1


def test_assign_recipe_to_day(client, user, db):
    login(client)
    r = seed_recipe(client, 'Taco Night', '8 tortillas\n1 lb beef')
    client.post('/plans/new', data={'week_start': date.today().isoformat(), 'title': 'Week'}, follow_redirects=True)
    plan = MealPlan.query.first()

    res = client.post(f'/plans/{plan.id}/assign', data={
        'recipe_id': r.id,
        'day_of_week': 4,
    }, follow_redirects=True)
    assert res.status_code == 200
    assert len(plan.entries) == 1
    assert plan.entries[0].day_of_week == 4

    # assigning to the same day replaces the previous recipe
    r2 = seed_recipe(client, 'Pizza Friday', '2 cups flour\n1 cup water')
    client.post(f'/plans/{plan.id}/assign', data={
        'recipe_id': r2.id,
        'day_of_week': 4,
    }, follow_redirects=True)
    db.session.refresh(plan)
    assert len(plan.entries) == 1
    assert plan.entries[0].recipe_id == r2.id


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
        client.post(f'/plans/{plan.id}/assign', data={'recipe_id': r.id, 'day_of_week': i})

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
    seed_recipe(client, 'Secret Stew', '1 potato')
    client.post('/plans/new', data={'week_start': date.today().isoformat(), 'title': 'Week'}, follow_redirects=True)
    plan = MealPlan.query.first()
    recipe = Recipe.query.first()
    client.post(f'/plans/{plan.id}/assign', data={'recipe_id': recipe.id, 'day_of_week': 0})

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
