"""Helpers for guest voting on weekly meal plans (QR-code shared)."""

from collections import defaultdict

from app.models import PlanVote

# Preset guest colors: (hex, label). Guests pick one; server validates membership.
VOTE_COLORS = [
    ('#E4572E', 'Tomato'),
    ('#F3A712', 'Amber'),
    ('#F6C744', 'Sunflower'),
    ('#57AB5A', 'Basil'),
    ('#2A9D8F', 'Teal'),
    ('#3D85C6', 'Sky'),
    ('#9B59B6', 'Grape'),
    ('#6C757D', 'Charcoal'),
]

VALID_HEX = {hex_value for hex_value, _ in VOTE_COLORS}


def tally_votes(plan_id):
    """Return per-recipe standings for a plan, most votes first.

    Each row: {'recipe_id', 'title', 'count', 'voters': [(name, color), ...]}.
    Votes for deleted recipes are kept with a placeholder title so counts stay honest.
    """
    votes = PlanVote.query.filter_by(plan_id=plan_id).order_by(PlanVote.created_at).all()
    by_recipe = defaultdict(list)
    titles = {}
    for v in votes:
        by_recipe[v.recipe_id].append((v.voter_name, v.color))
        if v.recipe:
            titles[v.recipe_id] = v.recipe.title
    rows = []
    for recipe_id, voters in by_recipe.items():
        rows.append({
            'recipe_id': recipe_id,
            'title': titles.get(recipe_id, '(removed recipe)'),
            'count': len(voters),
            'voters': voters,
        })
    rows.sort(key=lambda r: (-r['count'], r['title'].lower()))
    return rows
