"""PDF recipe-card import: parsing plus the import/save flow."""
import io
import os
import re

import pytest

from app.lib.importer import ImportFailed
from app.lib.pdf_importer import parse_recipe_pdf
from tests.pdf_builder import (
    VARIANTS,
    build_blank_pdf,
    build_custom_recipe_pdf,
    build_recipe_pdf,
    build_split_step_pdf,
    build_variant_pdf,
    build_wrapped_title_pdf,
)


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


# ---------------------------------------------------------------------------
# Template variations: all of these use the same headings but different
# amounts of text, ingredients, steps, page breaks, and image positions.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('variant_index', range(len(VARIANTS)))
def test_parse_template_variation_extracts_every_instruction_and_image(variant_index):
    spec = VARIANTS[variant_index]
    draft = parse_recipe_pdf(build_variant_pdf(variant_index))

    assert draft['method'] == 'pdf'
    assert draft['title'] == spec['title']
    assert draft['description'] == spec['description']
    assert draft['prep_minutes'] == spec['prep']
    assert draft['cook_minutes'] == spec['cook']
    assert draft['servings'] == 2

    expected_ingredients = ['%s %s' % (two, name)
                            for two, _four, name in spec['ingredients']]
    assert draft['ingredients'] == expected_ingredients

    expected_steps = ['%s: %s' % (title, body) for title, body in spec['steps']]
    assert draft['instructions'] == expected_steps

    image_indexes = spec.get('step_images')
    if image_indexes is None:
        image_indexes = set(range(len(spec['steps'])))
    assert len(draft['step_photos']) == len(spec['steps'])
    for index in image_indexes:
        assert draft['step_photos'][index] is not None, (
            'step %d should have a photo' % (index + 1))
    assert sum(photo is not None for photo in draft['step_photos']) == \
        len(image_indexes)
    assert draft['photo'] is not None
    assert draft['photo'][1][:2] == b'\xff\xd8'


def test_parse_multi_page_ingredients_continue_in_reading_order():
    draft = parse_recipe_pdf(build_variant_pdf(2))
    # 12 ingredients split across two ingredients pages, then steps over two
    # more pages.  Every row must survive the page break in order.
    assert len(draft['ingredients']) == 12
    assert draft['ingredients'][0] == '1 Red Bell Pepper'
    assert draft['ingredients'][6] == '1 Lime'
    assert len(draft['instructions']) == 8
    assert draft['instructions'][-1].startswith('SERVE:')


def test_parse_long_wrapped_ingredient_name():
    pdf = build_custom_recipe_pdf(
        title='WRAP TEST', description='A card with a very long ingredient name.',
        prep=5, cook=10,
        ingredients=[('2 lbs', '4 lbs', 'Slow Roasted Roma Tomatoes'),
                     ('1', '2', 'Yellow Onion')],
        steps=[('PREP', 'Chop everything into small pieces.')])
    draft = parse_recipe_pdf(pdf)
    assert draft['ingredients'] == [
        '2 lbs Slow Roasted Roma Tomatoes', '1 Yellow Onion']


def test_parse_reports_warnings_for_missing_fields():
    pdf = build_custom_recipe_pdf(
        title='NO TIMES', description='', prep=None, cook=None,
        ingredients=[('1', '2', 'Onion')],
        steps=[('PREP', 'Chop the onion.')], hero=False,
        step_images=set())
    draft = parse_recipe_pdf(pdf)
    assert draft['title'] == 'NO TIMES'
    assert any('description' in warning.lower() for warning in draft['warnings'])
    assert any('prep time' in warning.lower() for warning in draft['warnings'])
    assert any('cook time' in warning.lower() for warning in draft['warnings'])
    assert any('recipe photo' in warning.lower() for warning in draft['warnings'])


def test_import_pdf_preview_shows_extraction_warnings(client, user, auth):
    auth()
    pdf = build_custom_recipe_pdf(
        title='WARNING CARD', description='', prep=None, cook=None,
        ingredients=[('1', '2', 'Onion')],
        steps=[('PREP', 'Chop the onion.')], hero=False,
        step_images=set())
    res = _upload(client, pdf)
    body = res.data.decode()
    assert res.status_code == 200
    assert 'WARNING CARD' in body
    assert 'No prep time was found' in body
    assert 'No cook time was found' in body


def test_step_body_continues_across_a_page_break():
    # The dedicated split-page builder cuts the first body in half.
    draft = parse_recipe_pdf(build_split_step_pdf())
    assert len(draft['instructions']) == 2
    assert draft['instructions'][0] == (
        'CHOP VEGETABLES: Chop the onion and carrots into small pieces. '
        'Keep the pieces roughly the same size so they cook at the same '
        'rate and turn out tender.')
    assert draft['instructions'][1] == 'COOK: Cook the vegetables until soft.'


def test_wrapped_step_title_is_joined_with_its_body():
    draft = parse_recipe_pdf(build_wrapped_title_pdf())
    assert draft['instructions'] == [
        'SIMMER THE TOMATOES UNTIL THEY ARE TENDER: Let the tomatoes bubble gently.',
        'SERVE: Season and serve.',
    ]
