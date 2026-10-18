"""HTML recipe extraction — JSON-LD first, microdata, then metadata fallback."""

from skillet.import_parse import (
    parse_iso_duration,
    parse_recipe_html,
    parse_yield,
)

JSON_LD_HTML = """
<html><head>
<title>Site Title</title>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Recipe",
  "name": "Lemon Pasta",
  "description": "Bright and buttery.",
  "image": "https://example.com/pasta.jpg",
  "prepTime": "PT15M",
  "cookTime": "PT1H",
  "recipeYield": "4 servings",
  "recipeCategory": "Dinner",
  "keywords": "pasta, quick",
  "recipeIngredient": ["2 cups pasta", "1 lemon, zested", "1/2 cup parmesan"],
  "recipeInstructions": [
    {"@type": "HowToStep", "text": "Boil the pasta."},
    "Zest the lemon.",
    "1. Toss and serve."
  ]
}
</script>
</head><body></body></html>
"""


def test_parse_iso_duration():
    assert parse_iso_duration("PT15M") == 15
    assert parse_iso_duration("PT1H30M") == 90
    assert parse_iso_duration("PT45M") == 45
    assert parse_iso_duration("P1D") == 1440
    assert parse_iso_duration(None) is None
    assert parse_iso_duration("nonsense") is None


def test_parse_yield():
    assert parse_yield("4 servings") == 4
    assert parse_yield(["6"]) == 6
    assert parse_yield(8) == 8
    assert parse_yield(None) is None
    assert parse_yield("about two dozen") is None


def test_json_ld_full_recipe():
    draft = parse_recipe_html(JSON_LD_HTML, "https://example.com/lemon-pasta")
    assert draft["method"] == "json-ld"
    assert draft["title"] == "Lemon Pasta"
    assert draft["description"] == "Bright and buttery."
    assert draft["photo_url"] == "https://example.com/pasta.jpg"
    assert draft["prep_minutes"] == 15
    assert draft["cook_minutes"] == 60
    assert draft["servings"] == 4
    assert draft["source_url"] == "https://example.com/lemon-pasta"
    assert [i["name"] for i in draft["ingredients"]] == ["pasta", "lemon", "parmesan"]
    assert draft["ingredients"][1]["note"] == "zested"
    assert draft["instructions"] == [
        "Boil the pasta.",
        "Zest the lemon.",
        "Toss and serve.",
    ]
    # recipeCategory wins over keywords, matching the Next.js importer
    assert draft["tags"] == ["Dinner"]


def test_keywords_used_when_no_category():
    html = """
    <html><head><script type="application/ld+json">
    {"@type": "Recipe", "name": "Tea", "keywords": "warm, cozy",
     "recipeIngredient": ["1 tea bag"], "recipeInstructions": "Steep."}
    </script></head><body></body></html>
    """
    draft = parse_recipe_html(html, "https://example.com/tea")
    assert draft["tags"] == ["warm", "cozy"]


def test_microdata_fallback():
    html = """
    <html><head><title>Grandma's Soup</title>
    <meta property="og:title" content="Grandma's Soup">
    </head><body>
    <span itemprop="recipeIngredient">4 carrots</span>
    <span itemprop="recipeIngredient">2 quarts broth</span>
    <li itemprop="recipeInstructions">Chop the carrots.</li>
    <li itemprop="recipeInstructions">Simmer for an hour.</li>
    </body></html>
    """
    draft = parse_recipe_html(html, "https://example.com/soup")
    assert draft["method"] == "microdata"
    assert draft["title"] == "Grandma's Soup"
    assert [i["name"] for i in draft["ingredients"]] == ["carrots", "broth"]
    assert draft["instructions"] == ["Chop the carrots.", "Simmer for an hour."]


def test_metadata_fallback_still_useful():
    html = """
    <html><head><title>Cookies</title>
    <meta property="og:title" content="Best Cookies">
    <meta property="og:image" content="/cookie.jpg">
    </head><body><p>No recipe markup here.</p></body></html>
    """
    draft = parse_recipe_html(html, "https://blog.example.com/cookies")
    assert draft["method"] == "metadata"
    assert draft["title"] == "Best Cookies"
    assert draft["photo_url"] == "https://blog.example.com/cookie.jpg"
    assert draft["ingredients"] == []
    assert draft["servings"] == 4


def test_none_method_for_empty_page():
    draft = parse_recipe_html("<html><body></body></html>", "https://example.com/blank")
    assert draft["method"] == "none"
    assert draft["title"] == "Imported recipe"


def test_malformed_json_ld_is_skipped():
    html = """
    <html><head>
    <script type="application/ld+json">{ not json </script>
    <meta property="og:title" content="Rescued Title">
    </head><body></body></html>
    """
    draft = parse_recipe_html(html, "https://example.com/x")
    assert draft["title"] == "Rescued Title"
