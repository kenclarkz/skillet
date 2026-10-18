"""URL recipe import: parsing, SSRF guards, and the import flow."""
import re

import pytest

from app.lib.importer import (
    ImportBlocked,
    ImportFailed,
    assert_public_url,
    parse_recipe_html,
)

JSON_LD_PAGE = """
<!doctype html><html><head>
<title>Easy Lasagna | Food Site</title>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Recipe",
  "name": "Easy Classic Lasagne",
  "description": "A comforting layered pasta bake.",
  "prepTime": "PT30M",
  "cookTime": "PT1H",
  "recipeYield": "6 servings",
  "recipeCategory": ["Dinner", "Italian"],
  "recipeIngredient": [
    "2 tbsp olive oil",
    "1 (14 oz) can diced tomatoes",
    "3 cloves garlic, minced",
    "salt to taste"
  ],
  "recipeInstructions": [
    {"@type": "HowToStep", "text": "Heat the oil in a large saucepan."},
    {"@type": "HowToStep", "text": "Add the garlic and cook for 1 minute."},
    {"@type": "HowToSection", "itemListElement": [
      {"@type": "HowToStep", "text": "Layer the pasta with the sauce."}
    ]}
  ],
  "image": "https://raw.githubusercontent.com/favicon.ico"
}
</script>
</head><body><h1>Easy Classic Lasagne</h1></body></html>
"""

MICRODATA_PAGE = """
<!doctype html><html><head>
<meta property="og:title" content="Grandma Soup">
<meta property="og:description" content="Cozy and simple.">
<meta property="og:image" content="https://raw.githubusercontent.com/favicon.ico">
</head><body>
<div itemscope itemtype="https://schema.org/Recipe">
  <span itemprop="name">Grandma Soup</span>
  <ul>
    <li itemprop="recipeIngredient">1 lb carrots</li>
    <li itemprop="recipeIngredient">2 quarts water</li>
  </ul>
  <ol>
    <li itemprop="recipeInstructions">Chop the carrots.</li>
    <li itemprop="recipeInstructions">Simmer for one hour.</li>
  </ol>
</div>
</body></html>
"""

GRAPH_PAGE = """
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
  {"@type":"WebPage","name":"x"},
  {"@type":"Recipe","name":"Graph Cake","recipeIngredient":["1 cup sugar"],
   "recipeInstructions":"Mix and bake.","recipeYield":8}
]}
</script>
"""

GRAPH_PAGE_WRAP = "<html><body>%s</body></html>" % GRAPH_PAGE


def test_parse_json_ld_recipe():
    draft = parse_recipe_html(JSON_LD_PAGE, 'https://example.com/lasagna')
    assert draft['method'] == 'json-ld'
    assert draft['title'] == 'Easy Classic Lasagne'
    assert draft['prep_minutes'] == 30
    assert draft['cook_minutes'] == 60
    assert draft['servings'] == 6
    assert 'Dinner' in draft['tags']
    assert len(draft['ingredients']) == 4
    # nested HowToSection flattened
    assert len(draft['instructions']) == 3
    assert draft['instructions'][0].startswith('Heat the oil')
    assert draft['photo_url'] == 'https://raw.githubusercontent.com/favicon.ico'
    assert draft['source_url'] == 'https://example.com/lasagna'


def test_parse_microdata_fallback():
    draft = parse_recipe_html(MICRODATA_PAGE, 'https://example.com/soup')
    assert draft['method'] == 'microdata'
    assert draft['title'] == 'Grandma Soup'
    assert len(draft['ingredients']) == 2
    assert len(draft['instructions']) == 2
    assert draft['photo_url'] == 'https://raw.githubusercontent.com/favicon.ico'


def test_parse_recipe_inside_graph():
    draft = parse_recipe_html(GRAPH_PAGE_WRAP, 'https://example.com/cake')
    assert draft['title'] == 'Graph Cake'
    assert draft['servings'] == 8


def test_imported_ingredients_are_form_shaped():
    draft = parse_recipe_html(JSON_LD_PAGE, 'https://example.com/lasagna')
    # matches the textarea the recipe form expects: one line per ingredient
    text = '\n'.join(draft['ingredients'])
    assert 'tbsp olive oil' in text
    assert 'cloves garlic' in text


def test_no_recipe_raises():
    with pytest.raises(ImportFailed):
        parse_recipe_html('<html><body><p>Nothing here</p></body></html>', 'https://example.com/x')


def test_blocks_private_and_local_targets():
    for url in (
        'http://127.0.0.1/secret',
        'http://localhost/x',
        'http://192.168.1.10/router',
        'http://10.0.0.5/x',
        'http://169.254.169.254/latest/meta-data',
        'file:///etc/passwd',
        'ftp://example.com/x',
    ):
        with pytest.raises((ImportBlocked, ImportFailed)):
            assert_public_url(url)


def test_allows_public_targets():
    assert assert_public_url('https://example.com/recipe').startswith('https://example.com')


# ---------------------------------------------------------------------------
# Route-level flow (network mocked)
# ---------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, content, content_type='text/html', encoding='utf-8', url='https://example.com/r'):
        self.headers = {'Content-Type': content_type}
        self.encoding = encoding
        self.url = url
        self.status_code = 200
        if isinstance(content, str):
            content = content.encode()
        self._content = content

        class Raw:
            def __init__(self, content):
                self.content = content

            def read(self, n=-1, decode_content=True):
                return self.content[:n] if n and n > 0 else self.content
        self.raw = Raw(content)

    def raise_for_status(self):
        pass


def _install_fetch(monkeypatch, response=None, html=None):
    import app.lib.importer as importer

    def fake_get(url, **kwargs):
        if response is not None:
            return response
        return FakeResponse(html or JSON_LD_PAGE, url=url)

    monkeypatch.setattr(importer.requests, 'get', fake_get)


def login(client):
    client.post('/auth/signup', data={
        'email': 'imp@example.com', 'display_name': 'Importer',
        'password': 'password123', 'password2': 'password123',
    })
    client.post('/auth/login', data={'email': 'imp@example.com', 'password': 'password123'})


def test_import_page_requires_login(client):
    res = client.get('/recipes/import')
    assert res.status_code == 302
    assert '/auth/login' in res.headers['Location']


def test_import_prefills_the_recipe_form(client, user, monkeypatch):
    _install_fetch(monkeypatch)
    login(client)
    res = client.post('/recipes/import', data={'url': 'https://example.com/lasagna'})
    body = res.data.decode()
    assert res.status_code == 200
    assert 'Easy Classic Lasagne' in body
    assert 'olive oil' in body
    assert 'Heat the oil' in body
    # photo carried through as a hidden field for download-on-save
    assert 'raw.githubusercontent.com/favicon.ico' in body


def test_save_imported_recipe_downloads_photo(client, user, db, monkeypatch):
    import os
    import app.lib.importer as importer

    png = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00'
           b'\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00'
           b'\x00\x00IEND\xaeB`\x82')

    calls = {'n': 0}

    def fake_get(url, **kwargs):
        calls['n'] += 1
        if calls['n'] == 1:
            return FakeResponse(JSON_LD_PAGE, url=url)
        return FakeResponse(png, content_type='image/jpeg', url='https://raw.githubusercontent.com/favicon.ico')

    monkeypatch.setattr(importer.requests, 'get', fake_get)
    login(client)

    # step 1: fetch → prefilled form
    client.post('/recipes/import', data={'url': 'https://example.com/lasagna'})

    from app.models import Recipe

    draft = parse_recipe_html(JSON_LD_PAGE, 'https://example.com/lasagna')
    res = client.post('/recipes/new', data={
        'title': draft['title'],
        'description': draft['description'],
        'prep_minutes': str(draft['prep_minutes']),
        'cook_minutes': str(draft['cook_minutes']),
        'servings': str(draft['servings']),
        'source_url': draft['source_url'],
        'tags': ', '.join(draft['tags']),
        'ingredients': '\n'.join(draft['ingredients']),
        'instructions': '\n'.join(draft['instructions']),
        'photo_url': draft['photo_url'],
    }, follow_redirects=True)
    assert res.status_code == 200

    recipe = Recipe.query.filter_by(title=draft['title']).first()
    assert recipe is not None
    assert recipe.photo_path is not None
    path = os.path.join(client.application.config['UPLOAD_FOLDER'], recipe.photo_path)
    assert os.path.exists(path)
    with open(path, 'rb') as fh:
        assert fh.read()[:8] == b'\x89PNG\r\n\x1a\n'
    # structured ingredients saved
    assert len(recipe.ingredients) == 4
    assert recipe.instructions.count('\n') == 2


def test_import_reports_blocked_url(client, user, monkeypatch):
    login(client)
    res = client.post('/recipes/import', data={'url': 'http://127.0.0.1/evil'}, follow_redirects=True)
    assert res.status_code == 200
    assert b'private network' in res.data or b'not allowed' in res.data or b'http' in res.data


def test_import_reports_failed_fetch(client, user, monkeypatch):
    import app.lib.importer as importer

    def fake_get(url, **kwargs):
        raise importer.requests.ConnectionError('boom')

    monkeypatch.setattr(importer.requests, 'get', fake_get)
    login(client)
    res = client.post('/recipes/import', data={'url': 'https://example.com/down'}, follow_redirects=True)
    assert res.status_code == 200
    assert b'Could not fetch' in res.data


def test_proxy_tunnel_403_gets_clear_message(client, user, monkeypatch):
    """PythonAnywhere's proxy answers denied CONNECTs with a 403 tunnel
    error. The user needs a hosting-limitation message, not a raw traceback."""
    import requests
    import app.lib.importer as importer

    def fake_get(url, **kwargs):
        raise requests.exceptions.ProxyError(
            "HTTPSConnectionPool(host='example.com', port=443): "
            "Max retries exceeded with url: / (Caused by ProxyError("
            "'Cannot connect to proxy.', OSError('Tunnel connection "
            "failed: 403 Forbidden')))"
        )

    monkeypatch.setattr(importer.requests, 'get', fake_get)
    login(client)
    res = client.post('/recipes/import', data={'url': 'https://example.com/r'}, follow_redirects=True)
    body = res.data.decode()
    assert res.status_code == 200
    assert 'blocked the outbound request' in body
    assert 'Tunnel connection failed' not in body


def test_image_download_failure_still_saves_recipe(client, user, monkeypatch):
    """A failed photo download must not lose the imported recipe."""
    import requests
    import app.lib.importer as importer

    calls = {'n': 0}

    def fake_get(url, **kwargs):
        calls['n'] += 1
        if calls['n'] == 1:
            return FakeResponse(JSON_LD_PAGE, url=url)
        raise requests.ConnectionError('image host unreachable')

    monkeypatch.setattr(importer.requests, 'get', fake_get)
    login(client)

    client.post('/recipes/import', data={'url': 'https://example.com/lasagna'})

    from app.models import Recipe

    draft = parse_recipe_html(JSON_LD_PAGE, 'https://example.com/lasagna')
    res = client.post('/recipes/new', data={
        'title': draft['title'],
        'description': draft['description'],
        'prep_minutes': str(draft['prep_minutes']),
        'cook_minutes': str(draft['cook_minutes']),
        'servings': str(draft['servings']),
        'source_url': draft['source_url'],
        'tags': ', '.join(draft['tags']),
        'ingredients': '\n'.join(draft['ingredients']),
        'instructions': '\n'.join(draft['instructions']),
        'photo_url': draft['photo_url'],
    }, follow_redirects=True)
    assert res.status_code == 200

    recipe = Recipe.query.filter_by(title=draft['title']).first()
    assert recipe is not None
    assert recipe.photo_path is None
    assert len(recipe.ingredients) == 4


def test_blocked_page_with_title_but_no_recipe_raises():
    """JS-challenge / bot-block pages have a title but no recipe data."""
    blocked = (
        '<html><head><title>Simple Page</title>'
        '<meta property="og:title" content="Just a moment..."></head>'
        '<body>Enable JavaScript and cookies to continue</body></html>'
    )
    with pytest.raises(ImportFailed):
        parse_recipe_html(blocked, 'https://example.com/challenge')


def test_page_with_only_instructions_still_imports():
    """Partial data is fine — the user can fill in the rest."""
    partial = (
        '<html><head><meta property="og:title" content="Half Recipe"></head>'
        '<body><div itemscope itemtype="https://schema.org/Recipe">'
        '<li itemprop="recipeInstructions">Stir it.</li></div></body></html>'
    )
    draft = parse_recipe_html(partial, 'https://example.com/partial')
    assert draft['title'] == 'Half Recipe'
    assert draft['instructions'] == ['Stir it.']


def test_import_accepts_url_without_scheme(client, user, monkeypatch):
    """Pasting 'www.site.com/recipe' must work — auto-prepend https://."""
    _install_fetch(monkeypatch)
    login(client)
    res = client.post('/recipes/import', data={'url': 'www.example.com/lasagna'})
    assert res.status_code == 200
    assert 'Easy Classic Lasagne' in res.data.decode()


def test_import_accepts_quoted_url_with_spaces(client, user, monkeypatch):
    """Copy-pasted URLs often carry stray quotes and whitespace."""
    _install_fetch(monkeypatch)
    login(client)
    res = client.post('/recipes/import', data={'url': '  "https://example.com/lasagna"  '})
    assert res.status_code == 200
    assert 'Easy Classic Lasagne' in res.data.decode()


def test_import_shows_error_for_garbage_input(client, user, monkeypatch):
    """A truly invalid URL must render the form with a visible error."""
    login(client)
    res = client.post('/recipes/import', data={'url': 'not a url at all'})
    body = res.data.decode()
    assert res.status_code == 200
    assert 'Import a recipe from a URL' in body
    assert 'alert alert-danger' in body


def test_browser_save_flow_posts_to_correct_action(client, user, monkeypatch):
    """Browser-faithful flow: after fetch, the form action must point at
    /recipes/new. Without an explicit action the browser posts to the
    current URL (/recipes/import) and the recipe is silently lost."""
    _install_fetch(monkeypatch)
    login(client)

    # Step 1: fetch — response is the prefilled form rendered at /recipes/import
    res = client.post('/recipes/import', data={'url': 'https://example.com/lasagna'})
    body = res.data.decode()
    assert 'Easy Classic Lasagne' in body

    # Step 2: extract the form action exactly like a browser would
    m = re.search(r'<form[^>]*action="([^"]+)"', body)
    assert m, 'prefilled recipe form must declare an explicit action'
    action = m.group(1)

    # Step 3: submit the form fields to that action
    def field(name):
        mm = re.search(r'name="%s"[^>]*value="([^"]*)"' % name, body)
        return mm.group(1) if mm else ''
    ings = re.search(r'<textarea[^>]*name="ingredients"[^>]*>([\s\S]*?)</textarea>', body).group(1)
    step_texts = re.findall(r'<textarea[^>]*name="step_text"[^>]*>([\s\S]*?)</textarea>', body)
    res = client.post(action, data={
        'csrf_token': field('csrf_token'),
        'title': field('title'), 'description': field('description'),
        'prep_minutes': field('prep_minutes'), 'cook_minutes': field('cook_minutes'),
        'servings': field('servings'), 'source_url': field('source_url'),
        'tags': field('tags'), 'ingredients': ings,
        'step_text': step_texts, 'step_id': [''] * len(step_texts),
        'step_photo': [''] * len(step_texts),
        'photo_url': field('photo_url'),
    })
    assert res.status_code == 302
    assert '/recipes/' in res.headers['Location']
    assert 'import' not in res.headers['Location']

    from app.models import Recipe
    assert Recipe.query.count() == 1


STEP_IMAGE_PAGE = """
<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@type":"Recipe","name":"Photo Steps Cake",
 "recipeIngredient":["1 cup flour"],
 "recipeInstructions":[
   {"@type":"HowToStep","text":"Mix the batter.","image":"https://example.org/s1.png"},
   {"@type":"HowToStep","text":"Bake it."}
 ]}
</script></head><body></body></html>
"""

STEP_PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00'
            b'\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00'
            b'\x00\x00IEND\xaeB`\x82')


def test_step_images_collected_aligned_with_instructions():
    draft = parse_recipe_html(STEP_IMAGE_PAGE, 'https://example.com/cake')
    assert draft['instructions'] == ['Mix the batter.', 'Bake it.']
    assert draft['step_photos'] == ['https://example.org/s1.png', '']


def test_imported_step_photos_download_on_save(client, user, monkeypatch):
    import app.lib.importer as importer

    def fake_get(url, **kw):
        if 'example.com' in url:
            return FakeResponse(STEP_IMAGE_PAGE, url=url)
        return FakeResponse(STEP_PNG, content_type='image/png', url=url)

    monkeypatch.setattr(importer.requests, 'get', fake_get)
    login(client)

    res = client.post('/recipes/import', data={'url': 'https://example.com/cake'})
    body = res.data.decode()
    assert 'Photo Steps Cake' in body
    assert 'name="step_photo_url"' in body

    action = re.search(r'<form[^>]*action="([^"]+)"', body).group(1)
    step_texts = re.findall(r'<textarea[^>]*name="step_text"[^>]*>([\s\S]*?)</textarea>', body)
    remotes = re.findall(r'name="step_photo_url" value="([^"]*)"', body)
    sids = re.findall(r'name="step_id" value="([^"]*)"', body)

    def field(name):
        m = re.search(r'name="%s"[^>]*value="([^"]*)"' % name, body)
        return m.group(1) if m else ''

    res = client.post(action, data={
        'csrf_token': field('csrf_token'), 'title': field('title'),
        'description': field('description'), 'prep_minutes': field('prep_minutes'),
        'cook_minutes': field('cook_minutes'), 'servings': field('servings') or '4',
        'source_url': field('source_url'), 'tags': field('tags'),
        'ingredients': re.search(
            r'<textarea[^>]*name="ingredients"[^>]*>([\s\S]*?)</textarea>', body).group(1),
        'step_text': step_texts, 'step_id': sids, 'step_photo_url': remotes,
        'step_photo': [''] * len(step_texts),
    })
    assert res.status_code == 302

    from app.models import RecipeStep
    steps = RecipeStep.query.order_by(RecipeStep.position).all()
    assert [s.text for s in steps] == ['Mix the batter.', 'Bake it.']
    assert steps[0].photo_path is not None   # downloaded from the source page
    assert steps[1].photo_path is None       # this step had no image
