"""Import API: JSON auth guard, fetch-failure surfacing, and HelloFresh-style pages."""

from __future__ import annotations

from conftest import signup

from skillet.safe_fetch import FetchError
from skillet.views import importer

HELLOFRESH_STYLE_HTML = """
<html><head>
<title>Green Goddess Shrimp &amp; Grain Bowls Recipe | HelloFresh</title>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Person",
      "name": "Recipe Development Team"
    },
    {
      "@type": "Recipe",
      "name": "Green Goddess Shrimp & Grain Bowls",
      "description": "with Arugula, Roasted Radishes, Brussels & Zucchini",
      "image": "https://img.hellofresh.com/f_auto,fl_lossy,h_640,q_80/w_488/hero.jpg",
      "prepTime": "PT10M",
      "cookTime": "PT20M",
      "recipeYield": "2 servings",
      "recipeIngredient": [
        "12 oz Shrimp",
        "4 oz Arugula",
        "1 cup Quinoa",
        "1 Lemon"
      ],
      "recipeInstructions": [
        {"@type": "HowToStep", "text": "Preheat the oven to 425 degrees."},
        {"@type": "HowToStep", "text": "Roast the vegetables for 20 minutes."},
        {"@type": "HowToStep", "text": "Sear the shrimp, then serve over arugula."}
      ]
    }
  ]
}
</script>
</head><body></body></html>
"""


def _signed_in_client(client):
    """Sign up, then render a page so the session has a CSRF token."""
    signup(client)
    client.get("/cookbooks")
    with client.session_transaction() as sess:
        csrf = sess.get("csrf")
    return csrf


def _post_import(client, url, csrf):
    return client.post(
        "/api/import",
        json={"url": url},
        headers={"X-CSRF-Token": csrf or ""},
    )


def test_fetch_error_surfaces_real_message(client, monkeypatch):
    """A FetchError must reach the client as JSON — not an HTML 500 page."""
    csrf = _signed_in_client(client)

    def boom(_url):
        raise FetchError("The site responded with 403.")

    monkeypatch.setattr(importer, "safe_fetch_html", boom)
    response = _post_import(client, "https://www.hellofresh.com/recipes/anything-123", csrf)
    assert response.status_code == 400
    assert response.get_json() == {"error": "The site responded with 403."}


def test_import_success_with_hellofresh_style_json_ld(client, monkeypatch):
    csrf = _signed_in_client(client)
    monkeypatch.setattr(
        importer,
        "safe_fetch_html",
        lambda url: {"html": HELLOFRESH_STYLE_HTML, "final_url": url},
    )
    response = _post_import(
        client,
        "https://www.hellofresh.com/recipes/green-goddess-shrimp-and-grain-bowls-68d3",
        csrf,
    )
    assert response.status_code == 200
    draft = response.get_json()["draft"]
    assert draft["method"] == "json-ld"
    assert draft["title"] == "Green Goddess Shrimp & Grain Bowls"
    assert len(draft["ingredients"]) == 4
    assert len(draft["instructions"]) == 3
    assert draft["prep_minutes"] == 10
    assert draft["cook_minutes"] == 20
    assert draft["servings"] == 2
    assert draft["source_url"] == "https://www.hellofresh.com/recipes/green-goddess-shrimp-and-grain-bowls-68d3"


def test_import_no_recipe_returns_422_with_draft(client, monkeypatch):
    csrf = _signed_in_client(client)
    monkeypatch.setattr(
        importer,
        "safe_fetch_html",
        lambda url: {"html": "<html><head></head><body>Log in to continue</body></html>", "final_url": url},
    )
    response = _post_import(client, "https://example.com/shop", csrf)
    assert response.status_code == 422
    payload = response.get_json()
    assert "error" in payload
    assert payload["draft"]["method"] == "none"


def test_import_requires_json_sign_in_not_html_redirect(client):
    response = client.post("/api/import", json={"url": "https://example.com/r"})
    assert response.status_code == 401
    assert "error" in response.get_json()


def test_import_rejects_empty_url(client):
    csrf = _signed_in_client(client)
    response = _post_import(client, "", csrf)
    assert response.status_code == 400
    assert response.get_json() == {"error": "Paste a recipe URL first."}
