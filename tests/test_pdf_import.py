"""PDF recipe import: extraction, parsing, upload validation, and saving."""
import io
import re

import pytest

from app.lib.pdf_importer import PdfImportError, extract_pdf, parse_recipe_text


def make_pdf(lines=(), title=None, title_size=24, blank=False, encrypt=False):
    """Build a small PDF in memory with optional large-font title line."""
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    if title:
        page.insert_text((72, y), title, fontsize=title_size)
        y += title_size + 10
    for line in lines:
        page.insert_text((72, y), line, fontsize=11)
        y += 17
    if blank:
        page.draw_rect(fitz.Rect(50, 50, 300, 300))
    kwargs = {}
    if encrypt:
        kwargs = dict(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw='secret')
    data = doc.tobytes(**kwargs)
    doc.close()
    return data


RECIPE_LINES = [
    'Prep time: 20 min',
    'Cook time: 1 hr 5 min',
    'Serves 2',
    'Ingredients',
    '400 g Chicken breast',
    '2 tbsp Olive oil',
    '3 cloves Garlic, minced',
    'salt and pepper',
    'Instructions',
    '1. Preheat the oven to 200C and line a baking sheet with parchment.',
    '2. Pound the chicken breasts and season them well.',
    '3. Bake until golden and cooked through, about 30 minutes.',
]


def login(client):
    client.post('/auth/signup', data={
        'email': 'pdf@example.com', 'display_name': 'Pdf User',
        'password': 'password123', 'password2': 'password123',
    })
    client.post('/auth/login', data={'email': 'pdf@example.com', 'password': 'password123'})


def upload(client, pdf_bytes, filename='recipe.pdf', extra=None):
    data = {'pdf_file': (io.BytesIO(pdf_bytes), filename)}
    if extra:
        data.update(extra)
    return client.post('/recipes/import-pdf', data=data, content_type='multipart/form-data')


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def test_extract_returns_text_and_title_hint():
    pdf = make_pdf(RECIPE_LINES, title='Chicken Rollatini')
    text, hint = extract_pdf(pdf)
    assert 'Chicken breast' in text
    assert 'Preheat the oven' in text
    assert hint == 'Chicken Rollatini'


def test_extract_rejects_non_pdf_bytes():
    with pytest.raises(PdfImportError) as exc:
        extract_pdf(b'<html><body>not a pdf</body></html>')
    assert 'look like a PDF' in str(exc.value)


def test_extract_rejects_corrupt_pdf():
    with pytest.raises(PdfImportError) as exc:
        extract_pdf(b'%PDF-1.4\n' + b'garbage' * 20)
    assert 'could not be opened' in str(exc.value)


def test_extract_rejects_image_only_pdf():
    with pytest.raises(PdfImportError) as exc:
        extract_pdf(make_pdf(blank=True))
    assert 'scan or image-only' in str(exc.value)
    assert 'paste' in str(exc.value)


def test_extract_rejects_encrypted_pdf():
    with pytest.raises(PdfImportError) as exc:
        extract_pdf(make_pdf(lines=['x'] * 5, encrypt=True))
    assert 'password-protected' in str(exc.value)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def test_parse_full_recipe_text():
    text, hint = extract_pdf(make_pdf(RECIPE_LINES, title='Chicken Rollatini'))
    draft = parse_recipe_text(text, title_hint=hint)
    assert draft['title'] == 'Chicken Rollatini'
    assert draft['prep_minutes'] == 20
    assert draft['cook_minutes'] == 65
    assert draft['servings'] == 2
    assert len(draft['ingredients']) == 4
    assert '400 g Chicken breast' in draft['ingredients']
    assert len(draft['instructions']) == 3
    assert draft['instructions'][0].startswith('Preheat the oven')
    assert draft['method'] == 'pdf'
    assert draft['source_url'] == ''


def test_parse_missing_fields_get_defaults():
    draft = parse_recipe_text('Weeknight Pasta\n500 g penne\n2 cloves garlic\n'
                              '1. Boil the pasta.\n2. Toss with sauce.')
    assert draft['title'] == 'Weeknight Pasta'
    assert draft['prep_minutes'] is None
    assert draft['cook_minutes'] is None
    assert draft['servings'] == 4
    assert draft['ingredients'] == ['500 g penne', '2 cloves garlic']
    assert draft['instructions'] == ['Boil the pasta.', 'Toss with sauce.']


def test_parse_headers_without_times():
    draft = parse_recipe_text('Simple Soup\nIngredients\n1 lb carrots\n2 quarts water\n'
                              'Instructions\nSimmer until soft.\nServe hot.')
    assert draft['title'] == 'Simple Soup'
    assert draft['prep_minutes'] is None
    assert draft['cook_minutes'] is None
    assert draft['ingredients'] == ['1 lb carrots', '2 quarts water']
    assert draft['instructions'] == ['Simmer until soft.', 'Serve hot.']


def test_parse_wrapped_numbered_steps_merge():
    draft = parse_recipe_text('Cake\nIngredients\n1 cup flour\nInstructions\n'
                              '1. Mix the flour with the butter and sugar until the '
                              'dough comes together in a smooth ball that holds shape.\n'
                              '2. Bake it.')
    assert len(draft['instructions']) == 2
    assert draft['instructions'][0].startswith('Mix the flour')


def test_parse_structureless_text_uses_raw_fallback():
    draft = parse_recipe_text('Some Recipe Site\nA lovely dish that nobody '
                              'structured properly at all.')
    assert draft['method'] == 'pdf-raw'
    assert draft['title'] == 'Some Recipe Site'
    assert draft['instructions']


def test_parse_filename_used_when_no_title():
    draft = parse_recipe_text('Ingredients\n1 lb carrots\n', origin='grandma soup')
    assert draft['title'] == 'grandma soup'


def test_parse_empty_text_raises():
    with pytest.raises(PdfImportError):
        parse_recipe_text('   \n  \n')


# ---------------------------------------------------------------------------
# Route: upload, validation, preview, saving
# ---------------------------------------------------------------------------

def test_import_pdf_requires_login(client):
    res = client.get('/recipes/import-pdf')
    assert res.status_code == 302
    assert '/auth/login' in res.headers['Location']


def test_import_pdf_page_and_button_render(client, user):
    login(client)
    page = client.get('/recipes/import-pdf')
    assert page.status_code == 200
    assert b'Import Recipe PDF' in page.data
    assert b'name="paste_text"' in page.data
    # the cookbook interface exposes the new button too
    index = client.get('/recipes')
    assert index.data.count(b'Import Recipe PDF') >= 1


def test_pdf_upload_prefills_editable_preview(client, user):
    login(client)
    pdf = make_pdf(RECIPE_LINES, title='Chicken Rollatini')
    res = upload(client, pdf)
    body = res.data.decode()
    assert res.status_code == 200
    assert 'Chicken Rollatini' in body
    assert '400 g Chicken breast' in body
    assert 'Preheat the oven' in body
    assert 'Imported recipe' in body          # no source link for PDFs
    assert 'name="prep_minutes"' in body      # editable fields present
    assert 'value="65"' in body or '>65<' in body


def test_pdf_import_makes_no_network_requests(client, user, monkeypatch):
    """The source website must never be contacted during a PDF import."""
    import app.lib.importer as importer

    def boom(*args, **kwargs):
        raise AssertionError('network request attempted')

    monkeypatch.setattr(importer.requests, 'get', boom)
    login(client)
    res = upload(client, make_pdf(RECIPE_LINES, title='Chicken Rollatini'))
    assert res.status_code == 200
    assert 'Chicken Rollatini' in res.data.decode()


def test_pdf_save_creates_recipe_for_logged_in_user(client, user, db):
    login(client)
    pdf = make_pdf(RECIPE_LINES, title='Chicken Rollatini')
    res = upload(client, pdf)
    body = res.data.decode()

    # submit the preview exactly like the browser would
    def field(name):
        m = re.search(r'name="%s"[^>]*value="([^"]*)"' % name, body)
        return m.group(1) if m else ''

    ings = re.search(r'<textarea[^>]*name="ingredients"[^>]*>([\s\S]*?)</textarea>', body).group(1)
    step_texts = re.findall(r'<textarea[^>]*name="step_text"[^>]*>([\s\S]*?)</textarea>', body)
    action = re.search(r'<form[^>]*action="([^"]+)"', body).group(1)

    res = client.post(action, data={
        'csrf_token': field('csrf_token'),
        'title': field('title'),
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
    pdf_user = User.query.filter_by(email='pdf@example.com').one()
    assert recipe.user_id == pdf_user.id
    assert recipe.title == 'Chicken Rollatini'
    assert recipe.prep_minutes == 20
    assert recipe.cook_minutes == 65
    assert recipe.servings == 2
    assert recipe.photo_path is None
    assert len(recipe.ingredients) == 4
    assert recipe.instructions.count('\n') == 2
    # nothing is stored against any other user
    assert Recipe.query.count() == 1


def test_image_only_pdf_explains_and_offers_paste(client, user):
    login(client)
    res = upload(client, make_pdf(blank=True))
    body = res.data.decode()
    assert res.status_code == 200
    assert 'alert alert-danger' in body
    assert 'paste' in body.lower()
    assert 'name="paste_text"' in body


def test_paste_text_fallback_imports(client, user):
    login(client)
    res = client.post('/recipes/import-pdf', data={
        'paste_text': 'Grandma Soup\n1 lb carrots\n2 quarts water\n'
                      '1. Chop the carrots.\n2. Simmer one hour.'
    })
    body = res.data.decode()
    assert res.status_code == 200
    assert 'Grandma Soup' in body
    assert '1 lb carrots' in body
    assert 'Chop the carrots.' in body


def test_structureless_pdf_shows_warning_but_still_previews(client, user):
    login(client)
    pdf = make_pdf(['Mystery Recipe',
                    'A lovely dish that nobody structured properly at all.'])
    res = upload(client, pdf)
    body = res.data.decode()
    assert res.status_code == 200
    assert 'alert alert-warning' in body
    assert 'Mystery Recipe' in body


def test_wrong_extension_rejected(client, user):
    login(client)
    res = upload(client, make_pdf(RECIPE_LINES, title='X'), filename='recipe.txt')
    body = res.data.decode()
    assert res.status_code == 200
    assert 'alert alert-danger' in body
    assert 'extension' in body


def test_corrupt_file_rejected(client, user):
    login(client)
    res = upload(client, b'%PDF-1.4\n' + b'garbage' * 20, filename='broken.pdf')
    body = res.data.decode()
    assert res.status_code == 200
    assert 'alert alert-danger' in body
    assert 'could not be opened' in body


def test_oversized_pdf_rejected(client, user, app):
    login(client)
    app.config['MAX_PDF_BYTES'] = 512
    res = upload(client, make_pdf(RECIPE_LINES, title='Chicken Rollatini'))
    body = res.data.decode()
    assert res.status_code == 200
    assert 'larger than' in body


def test_empty_upload_and_empty_post_show_error(client, user):
    login(client)
    res = upload(client, b'', filename='empty.pdf')
    assert 'empty' in res.data.decode().lower()
    res = client.post('/recipes/import-pdf', data={})
    assert 'Upload a recipe PDF or paste' in res.data.decode()


def test_existing_url_import_still_works(client, user, monkeypatch):
    """The preview refactor must not break the URL importer."""
    from tests.test_importer import _install_fetch
    _install_fetch(monkeypatch)
    login(client)
    res = client.post('/recipes/import', data={'url': 'https://example.com/lasagna'})
    body = res.data.decode()
    assert res.status_code == 200
    assert 'Easy Classic Lasagne' in body
    assert 'the source page' in body  # URL imports keep their source link
