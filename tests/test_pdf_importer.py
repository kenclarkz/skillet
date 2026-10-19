"""PDF recipe-card import: parsing plus the import/save flow."""
import io
import os
import re

import pytest

from app.lib.importer import ImportFailed
from app.lib.pdf_importer import parse_recipe_pdf
from tests.pdf_builder import build_blank_pdf, build_recipe_pdf


def test_parse_recipe_pdf_extracts_card_fields():
    draft = parse_recipe_pdf(build_recipe_pdf())
    assert draft['method'] == 'pdf'
    assert draft['title'] == 'TEST CHICKEN BOWLS'
    assert draft['description'] == 'with Test Toppings'
    assert draft['prep_minutes'] == 10
    assert draft['cook_minutes'] == 25
    assert draft['servings'] == 2
    assert draft['ingredients'] == [
        '1 Apple', '1/2 Banana', '2 cups Rice', '1 Onion', '1 Lime',
        '1/4 oz Cilantro', '10 oz Chicken', '2 TBSP Crema', '1 Paste',
    ]
    assert draft['instructions'] == [
        'COOK RICE: Step 1 body text.', 'PREP: Step 2 body text.',
        'MAKE SALSA: Step 3 body text.', 'COOK VEGGIES: Step 4 body text.',
        'COOK CHICKEN: Step 5 body text.', 'FINISH: Step 6 body text.',
    ]
    assert draft['photo'][0] == 'jpg'
    assert draft['photo'][1][:2] == b'\xff\xd8'
    assert len(draft['step_photos']) == 6
    assert all(photo and photo[0] == 'jpg' for photo in draft['step_photos'])


def test_parse_recipe_pdf_independent_of_libraries():
    """The parser must not need anything beyond pdfminer + Pillow."""
    draft = parse_recipe_pdf(build_recipe_pdf())
    assert draft['source_url'] == ''
    assert draft['photo_url'] is None


def test_parse_recipe_pdf_rejects_non_pdf():
    with pytest.raises(ImportFailed):
        parse_recipe_pdf(b'not a pdf at all')


def test_parse_recipe_pdf_rejects_empty():
    with pytest.raises(ImportFailed):
        parse_recipe_pdf(b'')


def test_parse_recipe_pdf_rejects_pdf_without_a_card():
    with pytest.raises(ImportFailed):
        parse_recipe_pdf(build_blank_pdf())


def test_local_photo_reference_rejects_traversal(app):
    from app.routes.recipes import resolve_photo_reference
    with app.app_context():
        assert resolve_photo_reference('../../etc/passwd') is None
        assert resolve_photo_reference('nope.jpg') is None


def _upload(client, data, filename='card.pdf'):
    return client.post('/recipes/import/pdf',
                       data={'pdf': (io.BytesIO(data), filename)},
                       content_type='multipart/form-data')


def test_import_pdf_page_requires_login(client):
    res = client.get('/recipes/import/pdf')
    assert res.status_code == 302
    assert '/auth/login' in res.headers['Location']


def test_import_page_offers_both_imports(client, user, auth):
    auth()
    res = client.get('/recipes/import')
    body = res.data.decode()
    assert 'Import a recipe from a URL' in body
    assert 'Import a recipe PDF' in body
    assert 'enctype="multipart/form-data"' in body


def test_import_pdf_prefills_the_recipe_form(client, user, auth):
    auth()
    res = _upload(client, build_recipe_pdf())
    body = res.data.decode()
    assert res.status_code == 200
    assert 'TEST CHICKEN BOWLS' in body
    assert '1/2 Banana' in body
    assert 'Step 1 body text.' in body
    # the hero and step photos are saved immediately and previewed locally
    assert 'name="photo_url"' in body
    assert '/uploads/' in body
    assert 'step_photo_url' in body


def test_import_pdf_reports_non_pdf_upload(client, user, auth):
    auth()
    res = _upload(client, b'this is not a pdf', filename='notes.pdf')
    assert res.status_code == 200
    assert 'not a PDF' in res.data.decode()


def test_import_pdf_requires_a_file(client, user, auth):
    auth()
    res = client.post('/recipes/import/pdf', data={}, follow_redirects=True)
    assert res.status_code == 200
    assert 'Choose a PDF' in res.data.decode()


def test_import_pdf_saves_recipe_with_photos(client, user, auth, app):
    auth()
    res = _upload(client, build_recipe_pdf())
    body = res.data.decode()
    action = re.search(r'<form[^>]*action="([^"]+)"', body).group(1)

    def field(name):
        found = re.search(r'name="%s"[^>]*value="([^"]*)"' % name, body)
        return found.group(1) if found else ''

    ingredients = re.search(
        r'<textarea[^>]*name="ingredients"[^>]*>([\s\S]*?)</textarea>', body).group(1)
    step_texts = re.findall(
        r'<textarea[^>]*name="step_text"[^>]*>([\s\S]*?)</textarea>', body)
    remotes = re.findall(r'name="step_photo_url" value="([^"]*)"', body)

    res = client.post(action, data={
        'csrf_token': field('csrf_token'), 'title': field('title'),
        'description': field('description'), 'prep_minutes': field('prep_minutes'),
        'cook_minutes': field('cook_minutes'), 'servings': field('servings'),
        'source_url': field('source_url'), 'tags': field('tags'),
        'ingredients': ingredients, 'photo_url': field('photo_url'),
        'step_text': step_texts, 'step_id': [''] * len(step_texts),
        'step_photo_url': remotes, 'step_photo': [''] * len(step_texts),
    })
    assert res.status_code == 302
    assert '/recipes/' in res.headers['Location']

    from app.models import Recipe
    recipe = Recipe.query.filter_by(title='TEST CHICKEN BOWLS').first()
    assert recipe is not None
    assert recipe.photo_path is not None
    uploads = app.config['UPLOAD_FOLDER']
    assert os.path.exists(os.path.join(uploads, recipe.photo_path))

    steps = sorted(recipe.steps, key=lambda s: s.position)
    assert [s.text for s in steps][0] == 'COOK RICE: Step 1 body text.'
    assert len(steps) == 6
    assert all(s.photo_path for s in steps)
    for step in steps:
        assert os.path.exists(os.path.join(uploads, step.photo_path))
