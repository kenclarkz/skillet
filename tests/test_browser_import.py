"""Browser-assisted import: payload validation, endpoint, preview, saving."""
import json
import re
from urllib.parse import quote

import pytest

from app.lib.browser_import import (MAX_INGREDIENTS, MAX_PAYLOAD_BYTES,
                                    BrowserImportError, bookmarklet,
                                    parse_payload)


def draft_payload(**over):
    d = {
        'title': 'Chicken Rollatini',
        'description': 'Crispy rolled chicken.',
        'prep_minutes': 20,
        'cook_minutes': 65,
        'servings': 2,
        'tags': ['Dinner', 'Italian'],
        'ingredients': ['400 g Chicken breast', '2 tbsp Olive oil', '3 cloves Garlic'],
        'instructions': ['Pound the chicken.', 'Bake until golden.'],
        'photo_url': '',  # empty so no download happens during save tests
        'source_url': 'https://www.hellofresh.com/recipes/chicken-rollatini',
    }
    d.update(over)
    return d


def get_with_payload(client, payload):
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    return client.get('/recipes/import-browser?data=' + quote(raw))


def login(client):
    client.post('/auth/signup', data={
        'email': 'bm@example.com', 'display_name': 'Bookmark',
        'password': 'password123', 'password2': 'password123',
    })
    client.post('/auth/login', data={'email': 'bm@example.com', 'password': 'password123'})


# ---------------------------------------------------------------------------
# Payload validation
# ---------------------------------------------------------------------------

def test_parse_valid_payload_returns_shared_draft_shape():
    draft = parse_payload(json.dumps(draft_payload()))
    assert draft['title'] == 'Chicken Rollatini'
    assert draft['description'] == 'Crispy rolled chicken.'
    assert draft['prep_minutes'] == 20
    assert draft['cook_minutes'] == 65
    assert draft['servings'] == 2
    assert draft['tags'] == ['Dinner', 'Italian']
    assert len(draft['ingredients']) == 3
    assert len(draft['instructions']) == 2
    assert draft['source_url'].startswith('https://www.hellofresh.com/')
    assert draft['method'] == 'browser'
    assert draft['step_photos'] == []


def test_parse_rejects_missing_title():
    with pytest.raises(BrowserImportError) as exc:
        parse_payload(json.dumps({'ingredients': ['1 cup flour'], 'instructions': ['Mix.']}))
    assert 'title' in str(exc.value).lower()


def test_parse_rejects_empty_malformed_and_oversized_payloads():
    for bad, expected in (
        (None, 'No recipe data'),
        ('', 'No recipe data'),
        ('%7Bnot-json', 'not valid JSON'),
        (json.dumps(['not', 'a', 'dict']), 'not a recipe object'),
        ('x' * (MAX_PAYLOAD_BYTES + 1), 'too large'),
    ):
        with pytest.raises(BrowserImportError) as exc:
            parse_payload(bad)
        assert expected.lower() in str(exc.value).lower()


def test_parse_coerces_types():
    draft = parse_payload(json.dumps(draft_payload(
        prep_minutes='1 hr 5 min', cook_minutes='abc', servings='6 servings',
        ingredients='1 lb carrots\n2 quarts water',
        instructions=None,
        description=123,
    )))
    assert draft['prep_minutes'] == 65
    assert draft['cook_minutes'] is None
    assert draft['servings'] == 6
    assert draft['ingredients'] == ['1 lb carrots', '2 quarts water']
    assert draft['instructions'] == []
    assert draft['description'] == '123'


def test_parse_sanitizes_urls_and_ranges():
    draft = parse_payload(json.dumps(draft_payload(
        photo_url='javascript:alert(1)',
        source_url='not-a-url',
        servings=999,
        cook_minutes=-5,
    )))
    assert draft['photo_url'] is None
    assert draft['source_url'] == ''
    assert draft['servings'] == 4
    assert draft['cook_minutes'] is None


def test_parse_caps_lengths():
    draft = parse_payload(json.dumps(draft_payload(
        title='T' * 500,
        ingredients=['ing %d' % i for i in range(200)],
        instructions=['step %d' % i for i in range(200)],
        tags=['tag%d' % i for i in range(20)],
    )))
    assert len(draft['title']) == 200
    assert len(draft['ingredients']) == MAX_INGREDIENTS
    assert len(draft['instructions']) == 60
    assert len(draft['tags']) == 6


def test_parse_unwraps_dict_items():
    draft = parse_payload(json.dumps(draft_payload(
        instructions=[{'@type': 'HowToStep', 'text': 'Stir it well.'}],
        ingredients=[{'text': '1 lemon'}],
    )))
    assert draft['instructions'] == ['Stir it well.']
    assert draft['ingredients'] == ['1 lemon']


# ---------------------------------------------------------------------------
# Bookmarklet builder
# ---------------------------------------------------------------------------

def test_bookmarklet_is_single_line_and_targets_app():
    url = bookmarklet('https://me.pythonanywhere.com/')
    assert url.startswith('javascript:')
    assert '\n' not in url
    assert "'https://me.pythonanywhere.com'" in url
    assert "'/recipes/import-browser?data='" in url
    assert 'application/ld+json' in url
    assert '__BASE__' not in url


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

def test_import_browser_requires_login(client):
    res = get_with_payload(client, draft_payload())
    assert res.status_code == 302
    assert '/auth/login' in res.headers['Location']


def test_import_browser_page_shows_install_instructions(client, user):
    login(client)
    res = client.get('/recipes/import-browser')
    body = res.data.decode()
    assert res.status_code == 200
    assert 'Import from your browser' in body
    assert 'Set up once' in body
    # the textarea holds the ready-to-paste bookmarklet code
    code = re.search(r'<textarea[^>]*id="bm-code"[^>]*>([\s\S]*?)</textarea>', body).group(1)
    assert code.startswith('javascript:')
    assert 'application/ld+json' in code
    assert '/recipes/import-browser?data=' in code


def test_payload_renders_editable_preview(client, user):
    login(client)
    res = get_with_payload(client, draft_payload(photo_url='https://img.example.com/r.jpg'))
    body = res.data.decode()
    assert res.status_code == 200
    assert 'Chicken Rollatini' in body
    assert '400 g Chicken breast' in body
    assert 'Pound the chicken.' in body
    assert 'value="65"' in body
    # source link shown because source_url arrived
    assert 'the source page' in body
    # photo carried as a hidden field for download-on-save
    assert 'https://img.example.com/r.jpg' in body


def test_invalid_payload_shows_error_and_help_page(client, user):
    login(client)
    res = get_with_payload(client, '{broken json')
    body = res.data.decode()
    assert res.status_code == 200
    assert 'alert alert-danger' in body
    assert 'not valid JSON' in body
    assert 'Set up once' in body  # still the install page


def test_payload_without_recipe_content_errors(client, user):
    login(client)
    res = get_with_payload(client, {'title': '', 'ingredients': []})
    assert 'No recipe title' in res.data.decode()


def test_oversized_payload_errors(client, user):
    login(client)
    res = get_with_payload(client, 'x' * (MAX_PAYLOAD_BYTES + 1))
    assert 'too large' in res.data.decode()


def test_save_flow_stores_recipe_for_logged_in_user(client, user, db):
    login(client)
    res = get_with_payload(client, draft_payload())
    body = res.data.decode()

    def field(name):
        m = re.search(r'name="%s"[^>]*value="([^"]*)"' % name, body)
        return m.group(1) if m else ''

    ings = re.search(r'<textarea[^>]*name="ingredients"[^>]*>([\s\S]*?)</textarea>', body).group(1)
    step_texts = re.findall(r'<textarea[^>]*name="step_text"[^>]*>([\s\S]*?)</textarea>', body)
    action = re.search(r'<form[^>]*action="([^"]+)"', body).group(1)

    res = client.post(action, data={
        'csrf_token': field('csrf_token'),
        'title': field('title'),
        'description': field('description'),
        'prep_minutes': field('prep_minutes'),
        'cook_minutes': field('cook_minutes'),
        'servings': field('servings'),
        'source_url': field('source_url'),
        'tags': field('tags'),
        'ingredients': ings,
        'step_text': step_texts,
        'step_id': [''] * len(step_texts),
        'step_photo': [''] * len(step_texts),
        'step_photo_url': [''] * len(step_texts),
        'photo_url': field('photo_url'),
    })
    assert res.status_code == 302

    from app.models import Recipe, User
    recipe = Recipe.query.one()
    bm_user = User.query.filter_by(email='bm@example.com').one()
    assert recipe.user_id == bm_user.id
    assert recipe.title == 'Chicken Rollatini'
    assert recipe.prep_minutes == 20
    assert recipe.cook_minutes == 65
    assert recipe.servings == 2
    assert recipe.source_url.endswith('/chicken-rollatini')
    assert len(recipe.ingredients) == 3
    assert recipe.instructions.count('\n') == 1


def test_import_pages_link_to_browser_import(client, user):
    login(client)
    assert b'Import from your browser' in client.get('/recipes/import').data
    assert b'Import from browser' in client.get('/recipes/import-pdf').data
