"""Every import path fills the same complete set of recipe fields.

These tests cover the shared normalizer (app.lib.draft) and assert that a
URL import, a PDF/paste import and a bookmarklet import all surface the
fields the recipe page can display — especially the ones that used to be
dropped: real servings, category+cuisine+keyword tags, description,
photo and per-step photos.
"""
import json

from app.lib.browser_import import parse_payload
from app.lib.draft import (DEFAULT_SERVINGS, MAX_TAGS, better_servings,
                           derive_tags, finalize_draft, text_list)
from app.lib.importer import parse_recipe_html
from app.lib.pdf_importer import parse_recipe_text


# ---------------------------------------------------------------------------
# Shared normalizer
# ---------------------------------------------------------------------------

def test_better_servings_handles_ranges_and_text():
    assert better_servings('4-6') == 6          # upper bound
    assert better_servings('Serves 4 to 6') == 6
    assert better_servings('6 servings') == 6
    assert better_servings('8') == 8
    assert better_servings(12) == 12
    assert better_servings('6 people') == 6
    assert better_servings(None) is None
    assert better_servings('a lot') is None
    assert better_servings(9999) is None        # out of range


def test_derive_tags_merges_sources_dedupes_and_caps():
    tags = derive_tags('Dinner, Italian', 'Italian', ['weeknight', 'Pasta'], 'quick, weeknight')
    assert tags[:4] == ['Dinner', 'Italian', 'weeknight', 'Pasta']
    assert tags.count('Italian') == 1
    assert tags.count('weeknight') == 1
    assert len(derive_tags(['t%d' % i for i in range(20)])) == MAX_TAGS


def test_text_list_coerces_and_caps():
    assert text_list('a\nb\n c ') == ['a', 'b', 'c']
    assert text_list([{'text': 'hi'}, {'name': 'there'}]) == ['hi', 'there']
    assert text_list(['a', 'b', 'c'], cap=2) == ['a', 'b']
    assert text_list(None) == []


def test_finalize_fills_description_photo_and_aligns_step_photos():
    draft = finalize_draft({
        'title': 'X',
        'description': '',
        'photo_url': None,
        'instructions': ['First step.', 'Second step.'],
        'step_photos': ['https://img/1.jpg'],  # only one provided
        'ingredients': ['1 cup flour'],
        'tags': [],
        'servings': None,
    })
    # description falls back to the first step
    assert draft['description'] == 'First step.'
    # hero photo falls back to the first step photo
    assert draft['photo_url'] == 'https://img/1.jpg'
    # step list stays aligned with the instructions
    assert draft['step_photos'] == ['https://img/1.jpg', '']
    assert draft['servings'] == DEFAULT_SERVINGS


def test_finalize_prefers_real_main_photo_over_step_photo():
    draft = finalize_draft({
        'title': 'X', 'description': None,
        'photo_url': 'https://img/hero.jpg',
        'instructions': ['Step.'],
        'step_photos': ['https://img/step.jpg'],
        'ingredients': [], 'tags': [], 'servings': 2,
    })
    assert draft['photo_url'] == 'https://img/hero.jpg'


# ---------------------------------------------------------------------------
# URL import — richest source
# ---------------------------------------------------------------------------

RICH_PAGE = """
<!doctype html><html><head><title>Rich</title>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Recipe",
  "name": "Rich Ramen",
  "description": "Deeply savoury weeknight ramen.",
  "prepTime": "PT15M",
  "cookTime": "PT25M",
  "recipeYield": "4-6",
  "recipeCategory": "Dinner",
  "recipeCuisine": "Japanese",
  "keywords": "soup, noodles, quick",
  "recipeIngredient": ["2 packs ramen", "4 cups broth"],
  "recipeInstructions": [
    {"@type": "HowToStep", "text": "Boil the noodles.", "image": "https://img/step1.jpg"},
    {"@type": "HowToStep", "text": "Add the broth."}
  ],
  "image": "https://img/hero.jpg"
}
</script></head><body></body></html>
"""


def test_url_import_keeps_every_displayable_field():
    draft = parse_recipe_html(RICH_PAGE, 'https://example.com/ramen')
    assert draft['title'] == 'Rich Ramen'
    assert draft['description'] == 'Deeply savoury weeknight ramen.'
    assert draft['prep_minutes'] == 15
    assert draft['cook_minutes'] == 25
    assert draft['servings'] == 6                       # upper bound of "4-6"
    assert draft['photo_url'] == 'https://img/hero.jpg'
    assert draft['ingredients'] == ['2 packs ramen', '4 cups broth']
    assert draft['instructions'] == ['Boil the noodles.', 'Add the broth.']
    assert draft['step_photos'] == ['https://img/step1.jpg', '']
    # category + cuisine + keywords all survive
    for tag in ('Dinner', 'Japanese', 'soup', 'noodles', 'quick'):
        assert tag in draft['tags']


def test_url_import_falls_back_to_step_photo_for_hero():
    page = RICH_PAGE.replace('"image": "https://img/hero.jpg"', '"image": null')
    draft = parse_recipe_html(page, 'https://example.com/ramen')
    assert draft['photo_url'] == 'https://img/step1.jpg'


# ---------------------------------------------------------------------------
# PDF / pasted-text import
# ---------------------------------------------------------------------------

PASTE = """Creamy Tomato Soup

Prep time: 10 minutes
Cook time: 30 minutes
Serves 4 to 6
Tags: Soup, Comfort Food, Vegetarian

Ingredients
1 tbsp olive oil
1 onion, diced
2 (14 oz) cans tomatoes

Instructions
1. Heat the oil in a pot.
2. Add the onion and cook until soft.
3. Add the tomatoes and simmer for 20 minutes.
"""


def test_paste_import_keeps_times_servings_and_tags():
    draft = parse_recipe_text(PASTE)
    assert draft['title'] == 'Creamy Tomato Soup'
    assert draft['prep_minutes'] == 10
    assert draft['cook_minutes'] == 30
    assert draft['servings'] == 6                        # upper bound of "4 to 6"
    assert 'Soup' in draft['tags']
    assert 'Vegetarian' in draft['tags']
    assert len(draft['ingredients']) == 3
    assert len(draft['instructions']) == 3


def test_paste_import_description_defaults_to_first_step():
    draft = parse_recipe_text(PASTE)
    assert draft['description'] == 'Heat the oil in a pot.'


# ---------------------------------------------------------------------------
# Bookmarklet import
# ---------------------------------------------------------------------------

def test_bookmarklet_import_keeps_step_photos_and_servings():
    raw = json.dumps({
        'title': 'Browser Bowl',
        'description': '',
        'servings': '2 to 3',
        'tags': ['Dinner', 'Healthy', 'quick'],
        'ingredients': ['1 cup rice', '1 avocado'],
        'instructions': ['Cook the rice.', 'Top with avocado.'],
        'step_photos': ['https://img/s1.jpg', 'https://img/s2.jpg'],
        'photo_url': '',
        'source_url': 'https://example.com/bowl',
    })
    draft = parse_payload(raw)
    assert draft['servings'] == 3                        # upper bound of "2 to 3"
    assert draft['step_photos'] == ['https://img/s1.jpg', 'https://img/s2.jpg']
    # no main photo given, so the first step photo becomes the hero
    assert draft['photo_url'] == 'https://img/s1.jpg'
    assert draft['description'] == 'Cook the rice.'
    assert draft['tags'][:3] == ['Dinner', 'Healthy', 'quick']


def test_all_import_paths_return_the_same_draft_keys():
    from app.lib.draft import DRAFT_KEYS
    url_draft = parse_recipe_html(RICH_PAGE, 'https://example.com/ramen')
    pdf_draft = parse_recipe_text(PASTE)
    bm_draft = parse_payload(json.dumps({'title': 'T', 'ingredients': ['x'],
                                         'instructions': ['step']}))
    for draft in (url_draft, pdf_draft, bm_draft):
        assert set(draft) >= set(DRAFT_KEYS)
