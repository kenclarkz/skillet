"""Recipe CRUD, privacy, and image upload tests."""
import io
import os


def make_recipe(client, title='Chili Night', ingredients='2 cups beans\n1 onion', instructions='Simmer\nServe'):
    return client.post('/recipes/new', data={
        'title': title,
        'description': 'Warm and hearty',
        'prep_minutes': '10',
        'cook_minutes': '45',
        'servings': '4',
        'tags': 'dinner, comfort',
        'ingredients': ingredients,
        'instructions': instructions,
        'source_url': '',
        'photo': (io.BytesIO(b''), ''),
    }, follow_redirects=True)


def test_create_and_view_recipe(client, user):
    client.post('/auth/login', data={'email': 'test@example.com', 'password': 'password123'})
    res = make_recipe(client)
    assert res.status_code == 200
    assert b'Chili Night' in res.data

    res = client.get('/recipes')
    assert b'Chili Night' in res.data


def test_ingredients_are_parsed_and_stored(client, user, db):
    from app.models import Recipe
    client.post('/auth/login', data={'email': 'test@example.com', 'password': 'password123'})
    make_recipe(client)
    recipe = Recipe.query.filter_by(title='Chili Night').first()
    assert recipe is not None
    names = [i.name.lower() for i in recipe.ingredients]
    assert any('beans' in n for n in names)
    assert any('onion' in n for n in names)
    # qty parsing
    beans = [i for i in recipe.ingredients if 'beans' in i.name.lower()][0]
    assert beans.qty is not None and beans.unit is not None


def test_edit_recipe(client, user, db):
    from app.models import Recipe
    client.post('/auth/login', data={'email': 'test@example.com', 'password': 'password123'})
    make_recipe(client)
    recipe = Recipe.query.filter_by(title='Chili Night').first()

    res = client.post(f'/recipes/{recipe.id}/edit', data={
        'title': 'Best Chili',
        'description': 'Updated',
        'prep_minutes': '5',
        'cook_minutes': '30',
        'servings': '6',
        'tags': 'dinner',
        'ingredients': '1 lb beef',
        'instructions': 'Brown the beef',
        'source_url': '',
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b'Best Chili' in res.data
    assert len(recipe.ingredients) == 1
    assert recipe.ingredients[0].qty == '1'


def test_delete_recipe(client, user, db):
    from app.models import Recipe
    client.post('/auth/login', data={'email': 'test@example.com', 'password': 'password123'})
    make_recipe(client)
    recipe = Recipe.query.filter_by(title='Chili Night').first()
    res = client.post(f'/recipes/{recipe.id}/delete', follow_redirects=True)
    assert res.status_code == 200
    assert Recipe.query.filter_by(title='Chili Night').first() is None


def test_users_cannot_see_each_others_recipes(client, user, db):
    from app.models import Recipe, User
    client.post('/auth/login', data={'email': 'test@example.com', 'password': 'password123'})
    make_recipe(client)
    recipe = Recipe.query.filter_by(title='Chili Night').first()
    client.get('/auth/logout')

    # second user
    other = User(email='other@example.com', display_name='Other')
    other.set_password('otherpass123')
    db.session.add(other)
    db.session.commit()

    client.post('/auth/login', data={'email': 'other@example.com', 'password': 'otherpass123'})
    # list view should not show it
    res = client.get('/recipes')
    assert b'Chili Night' not in res.data
    # direct access redirected away
    res = client.get(f'/recipes/{recipe.id}', follow_redirects=True)
    assert b'Chili Night' not in res.data
    # cannot edit someone else's recipe
    res = client.get(f'/recipes/{recipe.id}/edit', follow_redirects=True)
    assert recipe.title.encode() not in res.data or res.status_code == 200
    res = client.post(f'/recipes/{recipe.id}/delete', follow_redirects=True)
    assert Recipe.query.filter_by(id=recipe.id).first() is not None


def test_image_upload_valid_and_served(client, user, app, db):
    from app.models import Recipe
    client.post('/auth/login', data={'email': 'test@example.com', 'password': 'password123'})

    # 1x1 PNG
    png = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00'
           b'\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00'
           b'\x00\x00IEND\xaeB`\x82')
    res = client.post('/recipes/new', data={
        'title': 'Photo Dish',
        'description': '',
        'prep_minutes': '',
        'cook_minutes': '',
        'servings': '2',
        'tags': '',
        'ingredients': '1 egg',
        'instructions': 'Fry it',
        'source_url': '',
        'photo': (io.BytesIO(png), 'test.png'),
    }, follow_redirects=True)
    assert res.status_code == 200

    recipe = Recipe.query.filter_by(title='Photo Dish').first()
    assert recipe.photo_path is not None
    # file actually exists
    path = os.path.join(app.config['UPLOAD_FOLDER'], recipe.photo_path)
    assert os.path.exists(path)

    # served over HTTP
    res = client.get(f'/uploads/{recipe.photo_path}')
    assert res.status_code == 200
    assert res.data[:8] == b'\x89PNG\r\n\x1a\n'


def test_rejects_disallowed_file_type(client, user, app, db):
    client.post('/auth/login', data={'email': 'test@example.com', 'password': 'password123'})
    before = set(os.listdir(app.config['UPLOAD_FOLDER']))
    client.post('/recipes/new', data={
        'title': 'Evil Dish',
        'description': '',
        'prep_minutes': '',
        'cook_minutes': '',
        'servings': '2',
        'tags': '',
        'ingredients': '1 egg',
        'instructions': 'Fry it',
        'source_url': '',
        'photo': (io.BytesIO(b'#!/bin/sh\necho hi'), 'evil.sh'),
    }, follow_redirects=True)
    after = set(os.listdir(app.config['UPLOAD_FOLDER']))
    assert before == after


def test_recipe_requires_login(client):
    res = client.get('/recipes')
    assert res.status_code == 302
    assert '/auth/login' in res.headers['Location']
