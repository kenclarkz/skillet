"""Per-step photos, step builder saves, and ingredients on every recipe page."""
import io
import os

from app.models import Recipe

PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00'
       b'\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00'
       b'\x00\x00IEND\xaeB`\x82')


def _base_fields(**overrides):
    data = {
        'title': 'Step Photo Stew', 'description': '', 'prep_minutes': '5',
        'cook_minutes': '20', 'servings': '4', 'source_url': '', 'tags': 'test',
        'ingredients': '2 potatoes\n1 onion',
    }
    data.update(overrides)
    return data


def test_create_recipe_with_step_rows_and_photos(client, app, db):
    client.post('/auth/signup', data={
        'email': 'steps@example.com', 'display_name': 'Steps',
        'password': 'password123', 'password2': 'password123'})
    client.post('/auth/login', data={'email': 'steps@example.com', 'password': 'password123'})

    res = client.post('/recipes/new', data=dict(
        _base_fields(),
        step_text=['Peel the potatoes', 'Simmer until soft'],
        step_id=['', ''],
        step_photo=[(io.BytesIO(PNG), 'peel.png'), (io.BytesIO(PNG), 'simmer.png')],
    ), content_type='multipart/form-data', follow_redirects=True)
    assert res.status_code == 200
    assert b'Recipe created.' in res.data

    recipe = Recipe.query.filter_by(title='Step Photo Stew').one()
    steps = recipe.steps
    assert [s.text for s in steps] == ['Peel the potatoes', 'Simmer until soft']
    assert steps[0].photo_path and steps[1].photo_path
    for s in steps:
        path = os.path.join(app.config['UPLOAD_FOLDER'], s.photo_path)
        assert os.path.exists(path)
    # legacy text column stays in sync
    assert recipe.instructions == 'Peel the potatoes\nSimmer until soft'

    # view page: ingredients section + step photos
    body = client.get(f'/recipes/{recipe.id}').data.decode()
    assert 'Ingredients' in body
    assert 'potatoes' in body and 'onion' in body
    assert 'Peel the potatoes' in body
    assert body.count('class="step-photo"') == 2


def test_edit_keeps_or_drops_step_photos(client, db, app):
    client.post('/auth/signup', data={
        'email': 'edit@example.com', 'display_name': 'Edit',
        'password': 'password123', 'password2': 'password123'})
    client.post('/auth/login', data={'email': 'edit@example.com', 'password': 'password123'})
    client.post('/recipes/new', data=dict(
        _base_fields(),
        step_text=['One', 'Two'],
        step_id=['', ''],
        step_photo=[(io.BytesIO(PNG), 'one.png'), (io.BytesIO(PNG), 'two.png')],
    ), content_type='multipart/form-data')

    recipe = Recipe.query.filter_by(title='Step Photo Stew').one()
    sid_keep, sid_drop = str(recipe.steps[0].id), str(recipe.steps[1].id)
    keep_path, drop_path = recipe.steps[0].photo_path, recipe.steps[1].photo_path
    assert keep_path and drop_path

    res = client.post(f'/recipes/{recipe.id}/edit', data=dict(
        _base_fields(title='Step Photo Stew'),
        step_text=['One updated', 'Two'],
        step_id=[sid_keep, sid_drop],
        step_drop_photo=[sid_drop],
        step_photo=[(io.BytesIO(b''), ''), (io.BytesIO(b''), '')],
    ), content_type='multipart/form-data', follow_redirects=True)
    assert res.status_code == 200
    assert b'Recipe updated.' in res.data

    db.session.refresh(recipe)
    steps = recipe.steps
    assert [s.text for s in steps] == ['One updated', 'Two']
    # row 0 keeps its photo (same file), row 1 dropped the photo
    assert steps[0].photo_path == keep_path
    assert steps[1].photo_path is None
    assert os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], keep_path))
    assert not os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], drop_path))


def test_empty_steps_are_rejected(client, db):
    client.post('/auth/signup', data={
        'email': 'empty@example.com', 'display_name': 'E',
        'password': 'password123', 'password2': 'password123'})
    client.post('/auth/login', data={'email': 'empty@example.com', 'password': 'password123'})

    res = client.post('/recipes/new', data=dict(
        _base_fields(), step_text=['', ''], step_id=['', ''],
    ), content_type='multipart/form-data')
    assert b'Add at least one cooking step.' in res.data
    assert Recipe.query.count() == 0


def test_legacy_instructions_post_creates_steps(client, db):
    """Posts that only send the plain instructions textarea still work."""
    client.post('/auth/signup', data={
        'email': 'legacy@example.com', 'display_name': 'L',
        'password': 'password123', 'password2': 'password123'})
    client.post('/auth/login', data={'email': 'legacy@example.com', 'password': 'password123'})

    res = client.post('/recipes/new', data=_base_fields(instructions='Boil water\nAdd pasta'),
                      follow_redirects=True)
    assert b'Recipe created.' in res.data
    recipe = Recipe.query.one()
    assert [s.text for s in recipe.steps] == ['Boil water', 'Add pasta']


def test_recipe_cards_show_ingredient_count(client, db):
    client.post('/auth/signup', data={
        'email': 'cards@example.com', 'display_name': 'C',
        'password': 'password123', 'password2': 'password123'})
    client.post('/auth/login', data={'email': 'cards@example.com', 'password': 'password123'})
    client.post('/recipes/new', data=dict(
        _base_fields(), step_text=['Stir'], step_id=[''],
        step_photo=[(io.BytesIO(b''), '')],
    ), content_type='multipart/form-data')

    body = client.get('/recipes').data.decode()
    assert '2 ingredients' in body


def test_every_recipe_page_shows_ingredients_section(client, db):
    """Imported and manual recipes alike must render the ingredients block."""
    client.post('/auth/signup', data={
        'email': 'sec@example.com', 'display_name': 'S',
        'password': 'password123', 'password2': 'password123'})
    client.post('/auth/login', data={'email': 'sec@example.com', 'password': 'password123'})

    client.post('/recipes/new', data=dict(
        _base_fields(title='Soup'), step_text=['Heat'], step_id=[''],
        step_photo=[(io.BytesIO(b''), '')],
    ), content_type='multipart/form-data')
    client.post('/recipes/new', data=dict(
        _base_fields(title='Salad', ingredients='1 lettuce'),
        step_text=['Toss'], step_id=[''],
        step_photo=[(io.BytesIO(b''), '')],
    ), content_type='multipart/form-data')

    for recipe in Recipe.query.all():
        body = client.get(f'/recipes/{recipe.id}').data.decode()
        assert 'Ingredients' in body, f'missing ingredients on {recipe.title}'
