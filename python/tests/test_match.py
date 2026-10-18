"""Product matching — threshold, confidence, and stop-word handling."""

from skillet.retailers.match import best_match, search_query_for_item, similarity


def test_exact_name_is_confident():
    score = similarity("chicken broth", "Swanson Chicken Broth 32 oz")
    assert score >= 0.25


def test_unrelated_scores_low():
    assert similarity("chicken broth", "Dishwasher pods lemon scent") < 0.25


def test_stop_words_ignored():
    # "fresh organic" are stop words; both reduce to {chicken, breast}
    assert similarity("fresh organic chicken breasts", "Chicken Breast") >= 0.9


def test_best_match_picks_top_candidate():
    products = [
        {"id": "p1", "title": "Dish Soap Lemon", "url": "u1", "priceText": "$3"},
        {"id": "p2", "title": "Lemons, 1 lb bag", "url": "u2", "priceText": "$2"},
    ]
    result = best_match({"name": "lemons"}, products)
    assert result["product"]["id"] == "p2"
    assert result["confidence"] >= 0.25


def test_best_match_returns_none_below_threshold():
    result = best_match({"name": "saffron threads"}, [
        {"id": "p1", "title": "Paper towels 6-pack", "url": "u1"},
    ])
    assert result["product"] is None


def test_best_match_empty_products():
    assert best_match({"name": "rice"}, []) == {"product": None, "confidence": 0.0}


def test_search_query_is_item_name():
    assert search_query_for_item({"name": "canned tomatoes"}) == "canned tomatoes"
