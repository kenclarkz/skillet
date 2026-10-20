"""Shared normalization for recipe drafts produced by every importer.

Each importer (URL, PDF/paste, browser bookmarklet) builds a draft dict
and hands it here so the fields the recipe page can display — photo,
servings, prep/cook time, tags, description, ingredients, step photos —
are filled as completely as the source allows. Keeping this in one place
means a fix lands on every import path at once.
"""
from __future__ import annotations

import re
from typing import Optional

MAX_TAGS = 6
MAX_SERVINGS = 100
DEFAULT_SERVINGS = 4

# Recipe-page shape: every importer must return exactly these keys.
DRAFT_KEYS = (
    'title', 'description', 'photo_url', 'prep_minutes', 'cook_minutes',
    'servings', 'tags', 'ingredients', 'instructions', 'step_photos',
    'source_url', 'method',
)


def text_list(value, cap: Optional[int] = None) -> list:
    """Coerce a str / list / tuple / dict-of-text into a clean list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        items = re.split(r'[\r\n]+', value)
    elif isinstance(value, (list, tuple)):
        items = value
    else:
        items = [value]
    out = []
    for item in items:
        if isinstance(item, dict):
            item = item.get('text') or item.get('name') or ''
        s = str(item).strip()
        if s:
            out.append(s)
    return out[:cap] if cap is not None else out


def better_servings(value) -> Optional[int]:
    """Best-effort servings from a schema.org recipeYield / free text.

    Handles "4", "8 servings", "Serves 4 to 6", "4-6", "6 people".
    Ranges resolve to the upper bound (the headline serving count on most
    recipe sites). Returns None when nothing usable is found so the caller
    can decide on a default.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        n = int(value)
        return n if 1 <= n <= MAX_SERVINGS else None
    s = str(value).strip()
    if not s:
        return None
    nums = [int(n) for n in re.findall(r'\d+', s)]
    nums = [n for n in nums if 1 <= n <= MAX_SERVINGS]
    if not nums:
        return None
    return max(nums)


def _tag_values(value) -> list:
    """Split a category/cuisine/keyword value into individual tag strings."""
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r'[,;]|\band\b', value, flags=re.I)
    elif isinstance(value, (list, tuple)):
        parts = []
        for item in value:
            parts.extend(_tag_values(item))
        return parts
    else:
        parts = [value]
    return [p.strip() for p in parts if p and p.strip()]


def derive_tags(*sources, extra=None) -> list:
    """Merge recipeCategory, recipeCuisine and keywords into clean, capped tags.

    Order is preserved (category, then cuisine, then keywords) and duplicates
    are dropped case-insensitively.
    """
    seen = set()
    out = []
    for source in list(sources) + [extra]:
        for tag in _tag_values(source):
            key = tag.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(tag[:200])
    return out[:MAX_TAGS]


def finalize_draft(draft: dict) -> dict:
    """Normalize a draft in place so no displayable field is left missing.

    - description falls back to the first instruction when blank
    - photo falls back to the first available step photo
    - step_photos always aligns with instructions
    - servings defaults to 4 only when the source had nothing
    """
    instructions = text_list(draft.get('instructions'), 60)
    draft['instructions'] = instructions

    photos = list(draft.get('step_photos') or [])
    first_step_photo = next((p for p in photos if p), '')
    # Keep the per-step list aligned with the steps we actually kept.
    draft['step_photos'] = [
        (photos[i] if i < len(photos) and isinstance(photos[i], str) else '')
        for i in range(len(instructions))
    ]

    if not draft.get('photo_url') and first_step_photo:
        draft['photo_url'] = first_step_photo

    draft['ingredients'] = text_list(draft.get('ingredients'), 80)

    desc = (draft.get('description') or '').strip()
    if not desc and instructions:
        candidate = instructions[0].strip()
        if candidate and len(candidate) <= 1000:
            desc = candidate
    draft['description'] = desc[:1000] or None

    servings = better_servings(draft.get('servings'))
    draft['servings'] = servings if servings is not None else DEFAULT_SERVINGS

    tags = derive_tags(draft.get('tags'))
    draft['tags'] = tags

    for key in DRAFT_KEYS:
        draft.setdefault(key, None)
    return draft
