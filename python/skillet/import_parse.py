"""Recipe extraction from HTML — port of src/lib/import/parse.ts.

JSON-LD (schema.org/Recipe) first, then microdata, then Open Graph / meta
fallbacks. Returns an editable draft plus the method used.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin

from .ingredients import parse_ingredient_line

ISO_DURATION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:([\d.]+)S)?)?$", re.IGNORECASE)

NAMED_ENTITIES = {
    "amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'", "nbsp": " ",
    "frac12": "½", "frac14": "¼", "frac34": "¾", "deg": "°", "rsquo": "’",
    "lsquo": "‘", "rdquo": "”", "ldquo": "“", "mdash": "—", "ndash": "–",
}


def parse_iso_duration(value: Any) -> int | None:
    """Parse an ISO-8601 duration ("PT1H30M", "PT45M") into minutes."""
    if not isinstance(value, str):
        return None
    match = ISO_DURATION.match(value.strip())
    if not match:
        hours = re.search(r"(\d+)\s*h", value, re.IGNORECASE)
        mins = re.search(r"(\d+)\s*m", value, re.IGNORECASE)
        if hours or mins:
            return (int(hours.group(1)) * 60 if hours else 0) + (int(mins.group(1)) if mins else 0)
        return None
    days, hours, minutes, seconds = match.groups()
    total = (
        (int(days) * 1440 if days else 0)
        + (int(hours) * 60 if hours else 0)
        + (int(minutes) if minutes else 0)
        + (float(seconds) / 60 if seconds else 0)
    )
    total = round(total)
    return total if total > 0 else None


def parse_yield(value: Any) -> int | None:
    """Extract a numeric serving count from values like "4", "4 servings", ["4"]."""
    if value is None:
        return None
    raw = value[0] if isinstance(value, list) else value
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return round(raw) if raw > 0 else None
    if not isinstance(raw, str):
        return None
    match = re.search(r"(\d+)", raw)
    if not match:
        return None
    n = int(match.group(1))
    return n if n > 0 else None


def first_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, list):
        for v in value:
            s = first_string(v)
            if s:
                return s
    if isinstance(value, dict):
        if "url" in value:
            return first_string(value["url"])
        if "text" in value:
            return first_string(value["text"])
    return None


def flatten_instructions(value: Any, out: list[str] | None = None) -> list[str]:
    if out is None:
        out = []
    if isinstance(value, str):
        for line in re.split(r"\r?\n+", value):
            trimmed = re.sub(r"^\d+[.)]\s*", "", line.strip())
            if trimmed:
                out.append(trimmed)
        return out
    if isinstance(value, list):
        for item in value:
            flatten_instructions(item, out)
        return out
    if isinstance(value, dict):
        if isinstance(value.get("itemListElement"), list):
            flatten_instructions(value["itemListElement"], out)
        elif isinstance(value.get("text"), str) and value["text"].strip():
            out.append(value["text"].strip())
        elif isinstance(value.get("name"), str) and value["name"].strip() and not value.get("@type"):
            out.append(value["name"].strip())
    return out


def as_recipe_node(node: Any, depth: int = 0) -> dict[str, Any] | None:
    if not isinstance(node, (dict, list)) or depth > 6:
        return None
    if isinstance(node, list):
        for item in node:
            found = as_recipe_node(item, depth + 1)
            if found:
                return found
        return None
    node_type = node.get("@type")
    if isinstance(node_type, list):
        types = [str(t) for t in node_type]
    elif node_type is not None:
        types = [str(node_type)]
    else:
        types = []
    if any(t.lower() == "recipe" for t in types):
        return node
    if isinstance(node.get("@graph"), list):
        return as_recipe_node(node["@graph"], depth + 1)
    return None


def extract_json_ld_recipes(html: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    pattern = re.compile(
        r"""<script[^>]*type=["']application/ld\+json["'][^>]*>([\s\S]*?)</script>""", re.IGNORECASE
    )
    for match in pattern.finditer(html):
        body = match.group(1).strip()
        body = re.sub(r"^<!--", "", body)
        body = re.sub(r"-->$", "", body)
        if not body:
            continue
        try:
            parsed = json.loads(body)
        except ValueError:
            continue  # malformed JSON-LD is common
        node = as_recipe_node(parsed)
        if node:
            results.append(node)
    return results


def decode_entities(input_text: str) -> str:
    def hex_sub(m: re.Match) -> str:
        try:
            return chr(int(m.group(1), 16))
        except (ValueError, OverflowError):
            return m.group(0)

    def dec_sub(m: re.Match) -> str:
        try:
            return chr(int(m.group(1)))
        except (ValueError, OverflowError):
            return m.group(0)

    def named_sub(m: re.Match) -> str:
        return NAMED_ENTITIES.get(m.group(1).lower(), m.group(0))

    out = re.sub(r"&#x([0-9a-f]+);", hex_sub, input_text, flags=re.IGNORECASE)
    out = re.sub(r"&#(\d+);", dec_sub, out)
    return re.sub(r"&([a-z0-9]+);", named_sub, out, flags=re.IGNORECASE)


def strip_tags(html: str) -> str:
    return re.sub(r"\s+", " ", decode_entities(re.sub(r"<[^>]*>", " ", html))).strip()


def meta_content(html: str, names: list[str]) -> str | None:
    content_pattern = re.compile(r"""content=(["'])(.*?)\1""", re.IGNORECASE | re.DOTALL)
    for name in names:
        pattern = re.compile(
            rf"<meta[^>]+(?:property|name|itemprop)=[\"']{re.escape(name)}[\"'][^>]*>", re.IGNORECASE
        )
        tag = pattern.search(html)
        if tag:
            content = content_pattern.search(tag.group(0))
            if content and content.group(2):
                return decode_entities(content.group(2)).strip()
        reversed_pattern = re.compile(
            rf"<meta[^>]+content=(['\"])(.*?)\1[^>]*(?:property|name|itemprop)=[\"']{re.escape(name)}[\"'][^>]*>",
            re.IGNORECASE | re.DOTALL,
        )
        alt = reversed_pattern.search(html)
        if alt and alt.group(2):
            return decode_entities(alt.group(2)).strip()
    return None


def extract_microdata(html: str) -> dict[str, Any]:
    ingredients: list[str] = []
    instructions: list[str] = []
    ingredient_pattern = re.compile(
        r"""<(?:li|span|div|p)[^>]*itemprop=["']recipeIngredient["'][^>]*>([\s\S]*?)</(?:li|span|div|p)>""",
        re.IGNORECASE,
    )
    for m in ingredient_pattern.finditer(html):
        text = strip_tags(m.group(1))
        if text:
            ingredients.append(text)
    instruction_pattern = re.compile(
        r"""<(?:li|span|div|p)[^>]*itemprop=["'](?:recipeInstructions|text)["'][^>]*>([\s\S]*?)</(?:li|span|div|p)>""",
        re.IGNORECASE,
    )
    for m in instruction_pattern.finditer(html):
        text = strip_tags(m.group(1))
        if text and len(text) > 2:
            instructions.append(text)
    yield_text = meta_content(html, ["recipeYield", "yield"])
    return {"ingredients": ingredients, "instructions": instructions, "yield_text": yield_text}


def absolutize(url: str | None, base: str) -> str | None:
    if not url:
        return None
    try:
        return urljoin(base, url)
    except ValueError:
        return None


def dedupe_in_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _document_title(html: str) -> str:
    match = re.search(r"<title[^>]*>([\s\S]*?)</title>", html, re.IGNORECASE)
    return strip_tags(match.group(1)) if match else ""


def parse_recipe_html(html: str, source_url: str) -> dict[str, Any]:
    """Parse recipe details out of an HTML document."""
    json_ld = extract_json_ld_recipes(html)

    if json_ld:
        node = json_ld[0]
        raw_ingredients = node.get("recipeIngredient") or node.get("ingredients")
        ingredients: list[dict[str, Any]] = []
        if isinstance(raw_ingredients, list):
            for i in raw_ingredients:
                line = i if isinstance(i, str) else first_string(i)
                if line:
                    ingredients.append(parse_ingredient_line(strip_tags(line)))

        instructions = flatten_instructions(node.get("recipeInstructions"))
        photo = first_string(node.get("image")) or first_string(node.get("thumbnailUrl"))
        tags_raw = node.get("recipeCategory") or node.get("keywords") or node.get("recipeCuisine")
        if isinstance(tags_raw, list):
            tags = [s.strip() for t in tags_raw for s in str(t).split(",")]
        elif isinstance(tags_raw, str):
            tags = [s.strip() for s in tags_raw.split(",")]
        else:
            tags = []

        title = first_string(node.get("name")) or _document_title(html)

        return {
            "title": title or "Imported recipe",
            "description": first_string(node.get("description")),
            "photo_url": absolutize(photo, source_url),
            "prep_minutes": parse_iso_duration(node.get("prepTime")),
            "cook_minutes": parse_iso_duration(node.get("cookTime")) or parse_iso_duration(node.get("totalTime")),
            "servings": parse_yield(node.get("recipeYield")) or 4,
            "source_url": source_url,
            "tags": [t for t in tags if t][:8],
            "ingredients": ingredients,
            "instructions": dedupe_in_order(instructions)[:60],
            "method": "json-ld",
        }

    # Microdata fallback
    micro = extract_microdata(html)
    if micro["ingredients"] or micro["instructions"]:
        return {
            "title": meta_content(html, ["og:title", "twitter:title"]) or _document_title(html) or "Imported recipe",
            "description": meta_content(html, ["og:description", "description"]),
            "photo_url": absolutize(meta_content(html, ["og:image", "twitter:image"]), source_url),
            "prep_minutes": None,
            "cook_minutes": None,
            "servings": parse_yield(micro["yield_text"]) or 4,
            "source_url": source_url,
            "tags": [],
            "ingredients": [parse_ingredient_line(line) for line in micro["ingredients"]],
            "instructions": dedupe_in_order(micro["instructions"]),
            "method": "microdata",
        }

    # Metadata-only fallback: at least give them the title and photo.
    og_title = meta_content(html, ["og:title", "twitter:title"])
    doc_title = _document_title(html)
    if og_title or doc_title:
        return {
            "title": og_title or doc_title,
            "description": meta_content(html, ["og:description", "description"]),
            "photo_url": absolutize(meta_content(html, ["og:image", "twitter:image"]), source_url),
            "prep_minutes": None,
            "cook_minutes": None,
            "servings": 4,
            "source_url": source_url,
            "tags": [],
            "ingredients": [],
            "instructions": [],
            "method": "metadata",
        }

    return {
        "title": "Imported recipe",
        "description": None,
        "photo_url": None,
        "prep_minutes": None,
        "cook_minutes": None,
        "servings": 4,
        "source_url": source_url,
        "tags": [],
        "ingredients": [],
        "instructions": [],
        "method": "none",
    }
