"""Fetch and parse a recipe from a public URL.

Same JSON-LD-first strategy as the original app, plus a strict SSRF guard:
only public http/https hosts are fetched, private/loopback targets are
rejected, and both size and content-type are checked.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from html import unescape
from typing import Optional
from urllib.parse import urlparse

import requests

from app.lib.draft import better_servings, derive_tags, finalize_draft

USER_AGENT = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/122.0 Safari/537.36'
)
MAX_BYTES = 4 * 1024 * 1024
TIMEOUT = 12


class ImportBlocked(Exception):
    """URL points somewhere it should not (private network, bad scheme)."""


class ImportFailed(Exception):
    """Network or parse failure — the user sees this message verbatim."""


BLOCKED_OUTBOUND_HINT = (
    'This server blocked the outbound request. Free hosts like PythonAnywhere '
    'restrict which external sites their apps may contact, so some recipe '
    'sites cannot be imported from here. Try again later, import from a '
    'different network, or add the recipe manually.'
)


def _request_failed(message: str, exc: requests.RequestException) -> ImportFailed:
    """Translate a requests exception, calling out blocked outbound tunnels.

    PythonAnywhere's proxy answers denied CONNECTs with
    ``ProxyError ... Tunnel connection failed: 403 Forbidden``. That is a
    hosting limitation, not a bad URL, so it gets its own clear message.
    """
    text = f'{exc}'
    if (isinstance(exc, requests.exceptions.ProxyError)
            or 'tunnel connection failed' in text.lower()
            or ('403' in text and 'forbidden' in text.lower())):
        return ImportFailed(f'{message} {BLOCKED_OUTBOUND_HINT}')
    return ImportFailed(f'{message} {exc}')


def assert_public_url(url: str) -> str:
    """Validate the URL and resolve its host, rejecting private targets."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ('http', 'https'):
        raise ImportBlocked('Only http:// and https:// URLs are supported.')
    host = parsed.hostname
    if not host:
        raise ImportBlocked('That does not look like a valid URL.')
    if host.lower() == 'localhost':
        raise ImportBlocked('Local addresses are not allowed.')
    try:
        infos = socket.getaddrinfo(host, parsed.port or None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ImportFailed(f'Could not resolve that host: {exc}') from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            raise ImportBlocked('That host points to a private network address.')
    return parsed.geturl()


def fetch_html(url: str) -> tuple:
    """Return (final_url, html). Raises ImportBlocked / ImportFailed."""
    final_url = assert_public_url(url)
    try:
        resp = requests.get(
            final_url,
            headers={'User-Agent': USER_AGENT,
                     'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                     'Accept-Language': 'en-US,en;q=0.9',
                     'Accept-Encoding': 'gzip, deflate, br',
                     'Connection': 'keep-alive'},
            timeout=TIMEOUT,
            allow_redirects=True,
            stream=True,
        )
    except requests.RequestException as exc:
        raise _request_failed('Could not fetch that page.', exc) from exc

    # Redirects can land on a private host — re-check the final target.
    assert_public_url(resp.url)
    try:
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise _request_failed('Could not fetch that page.', exc) from exc

    content_type = (resp.headers.get('Content-Type') or '').lower()
    if content_type and 'html' not in content_type and 'xml' not in content_type:
        raise ImportFailed('That URL did not return a web page.')

    raw = resp.raw.read(MAX_BYTES + 1, decode_content=True)
    if len(raw) > MAX_BYTES:
        raise ImportFailed('That page is too large to import.')
    if not raw:
        raise ImportFailed('That page was empty.')

    encoding = resp.encoding or 'utf-8'
    try:
        html = raw.decode(encoding, errors='replace')
    except LookupError:
        html = raw.decode('utf-8', errors='replace')
    return resp.url, html


def download_image(url: str) -> tuple:
    """Return (filename_extension, bytes) for a recipe photo."""
    final_url = assert_public_url(url)
    try:
        resp = requests.get(
            final_url,
            headers={'User-Agent': USER_AGENT,
                     'Accept': 'image/*,*/*;q=0.8',
                     'Accept-Language': 'en-US,en;q=0.9'},
            timeout=TIMEOUT,
            allow_redirects=True,
            stream=True,
        )
    except requests.RequestException as exc:
        raise _request_failed('Could not download the photo.', exc) from exc
    assert_public_url(resp.url)
    try:
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise _request_failed('Could not download the photo.', exc) from exc
    assert_public_url(resp.url)

    content_type = (resp.headers.get('Content-Type') or '').lower()
    ext = {
        'image/jpeg': 'jpg', 'image/jpg': 'jpg', 'image/png': 'png',
        'image/webp': 'webp', 'image/gif': 'gif',
    }.get(content_type.split(';')[0].strip())
    if not ext:
        raise ImportFailed('The photo URL did not return a supported image.')

    raw = resp.raw.read(MAX_BYTES + 1, decode_content=True)
    if len(raw) > MAX_BYTES or not raw:
        raise ImportFailed('The photo is missing or too large.')
    return ext, raw


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _strip_tags(html: str) -> str:
    text = re.sub(r'<[^>]*>', ' ', html)
    text = unescape(text)
    return re.sub(r'\s+', ' ', text).strip()


def _decode_entities(text: str) -> str:
    named = {
        'amp': '&', 'lt': '<', 'gt': '>', 'quot': '"', 'apos': "'", 'nbsp': ' ',
        'frac12': '½', 'frac14': '¼', 'frac34': '¾', 'deg': '°',
        'rsquo': '’', 'lsquo': '‘', 'rdquo': '”', 'ldquo': '“',
        'mdash': '—', 'ndash': '–',
    }
    text = re.sub(r'&#x([0-9a-f]+);', lambda m: chr(int(m.group(1), 16)), text, flags=re.I)
    text = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), text)
    return re.sub(r'&([a-z0-9]+);', lambda m: named.get(m.group(1).lower(), m.group(0)), text, flags=re.I)


def _duration_minutes(value) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    m = re.match(r'^PT?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$', s, re.I)
    if m and any(m.groups()):
        hours = int(m.group(1) or 0)
        minutes = int(m.group(2) or 0)
        seconds = int(m.group(3) or 0)
        return hours * 60 + minutes + (1 if seconds >= 30 else 0)
    m = re.match(r'^(\d+)\s*(?:min|minutes?|m)$', s, re.I)
    if m:
        return int(m.group(1))
    m = re.match(r'^(\d+)\s*(?:h|hours?|hrs?)$', s, re.I)
    if m:
        return int(m.group(1)) * 60
    return None


def _image_url(value) -> Optional[str]:
    """Pull a usable image URL out of a schema.org image/thumbnailUrl value."""
    if value is None:
        return None
    if isinstance(value, list):
        for item in value:
            found = _image_url(item)
            if found:
                return found
        return None
    if isinstance(value, dict):
        return _image_url(value.get('url') or value.get('contentUrl') or value.get('content'))
    if isinstance(value, str) and value.startswith('http'):
        return value
    return None


def _flatten_instructions(value, out: Optional[list] = None,
                          images: Optional[list] = None) -> tuple:
    """Return (texts, images) kept aligned — images get '' when a step has none."""
    out = out if out is not None else []
    images = images if images is not None else []
    if isinstance(value, str):
        for line in re.split(r'\r?\n+', value):
            line = re.sub(r'^\d+[.)]\s*', '', line.strip())
            if line:
                out.append(line)
                images.append('')
        return out, images
    if isinstance(value, list):
        for item in value:
            _flatten_instructions(item, out, images)
        return out, images
    if isinstance(value, dict):
        if isinstance(value.get('itemListElement'), list):
            _flatten_instructions(value['itemListElement'], out, images)
        elif isinstance(value.get('text'), str) and value['text'].strip():
            img = value.get('image')
            if isinstance(img, list) and img:
                img = img[0]
            if isinstance(img, dict):
                img = img.get('url') or img.get('contentUrl')
            if not (isinstance(img, str) and img.startswith('http')):
                img = ''
            out.append(value['text'].strip())
            images.append(img)
        elif value.get('name') and not value.get('@type'):
            out.append(str(value['name']).strip())
            images.append('')
    return out, images


def _as_recipe_node(node, depth=0) -> Optional[dict]:
    if depth > 6 or node is None:
        return None
    if isinstance(node, list):
        for item in node:
            found = _as_recipe_node(item, depth + 1)
            if found:
                return found
        return None
    if not isinstance(node, dict):
        return None
    node_type = node.get('@type')
    types = node_type if isinstance(node_type, list) else [node_type]
    if any(str(t).lower() == 'recipe' for t in types):
        return node
    if isinstance(node.get('@graph'), list):
        return _as_recipe_node(node['@graph'], depth + 1)
    return None


def _json_ld_recipes(html: str) -> list:
    results = []
    pattern = re.compile(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>', re.I
    )
    for match in pattern.finditer(html):
        body = match.group(1).strip().lstrip('<!--').rstrip('-->').strip()
        if not body:
            continue
        try:
            import json
            node = _as_recipe_node(json.loads(body))
        except (ValueError, TypeError):
            continue
        if node:
            results.append(node)
    return results


def _meta(html: str, names: list) -> Optional[str]:
    for name in names:
        m = re.search(
            r'<meta[^>]+(?:property|name|itemprop)=["\']' + re.escape(name) +
            r'["\'][^>]*>', html, re.I
        )
        if not m:
            continue
        c = re.search(r'content=["\']([^"\']*)["\']', m.group(0), re.I)
        if c and c.group(1).strip():
            return _decode_entities(c.group(1)).strip()
    return None


def _microdata(html: str) -> dict:
    ingredients = []
    instructions = []
    ing_re = re.compile(
        r'<(?:li|span|div|p)[^>]*itemprop=["\']recipeIngredient["\'][^>]*>([\s\S]*?)</(?:li|span|div|p)>', re.I
    )
    for m in ing_re.finditer(html):
        text = _strip_tags(m.group(1))
        if text:
            ingredients.append(text)
    step_re = re.compile(
        r'<(?:li|span|div|p)[^>]*itemprop=["\']recipeInstructions["\'][^>]*>([\s\S]*?)</(?:li|span|div|p)>', re.I
    )
    for m in step_re.finditer(html):
        text = _strip_tags(m.group(1))
        if len(text) > 2:
            instructions.append(text)
    return {'ingredients': ingredients, 'instructions': instructions}


def parse_recipe_html(html: str, source_url: str) -> dict:
    """Extract a structured draft. Fields mirror the recipe form exactly."""
    draft = {
        'title': '', 'description': None, 'photo_url': None,
        'prep_minutes': None, 'cook_minutes': None, 'servings': 4,
        'tags': [], 'ingredients': [], 'instructions': [], 'step_photos': [],
        'source_url': source_url, 'method': 'none',
    }

    for node in _json_ld_recipes(html):
        title = str(node.get('name') or '').strip()
        if not title:
            continue
        draft['method'] = 'json-ld'
        draft['title'] = title[:200]
        draft['description'] = (str(node.get('description') or '').strip()[:1000] or None)
        draft['prep_minutes'] = _duration_minutes(node.get('prepTime'))
        draft['cook_minutes'] = _duration_minutes(node.get('cookTime'))
        draft['servings'] = better_servings(node.get('recipeYield')) or 4

        # category, cuisine and SEO keywords all become tags
        draft['tags'] = derive_tags(node.get('recipeCategory'),
                                    node.get('recipeCuisine'),
                                    node.get('keywords'))

        ing_lines = node.get('recipeIngredient') or node.get('ingredients') or []
        if isinstance(ing_lines, str):
            ing_lines = re.split(r'[\n\r]+', ing_lines)
        draft['ingredients'] = [str(i).strip() for i in ing_lines if str(i).strip()]

        steps, step_images = _flatten_instructions(node.get('recipeInstructions'))
        # Older markup stores instructions as one blob of ingredient-like text.
        if steps and all(len(s) > 200 for s in steps[:1]) and len(steps) == 1:
            steps = re.split(r'(?<=\.)\s{2,}', steps[0])
            step_images = [''] * len(steps)
        draft['instructions'] = steps[:60]
        draft['step_photos'] = (step_images or [])[:60]

        draft['photo_url'] = (_image_url(node.get('image'))
                              or _image_url(node.get('thumbnailUrl')))
        break

    if draft['method'] == 'none':
        micro = _microdata(html)
        if micro['ingredients'] or micro['instructions']:
            draft['method'] = 'microdata'
            draft['ingredients'] = micro['ingredients']
            draft['instructions'] = micro['instructions']
            draft['step_photos'] = [''] * len(micro['instructions'])
            draft['title'] = (_meta(html, ['og:title', 'twitter:title']) or '')[:200]
            draft['description'] = _meta(html, ['og:description', 'description'])
            draft['photo_url'] = _meta(html, ['og:image', 'twitter:image'])

    if draft['method'] == 'none':
        draft['method'] = 'metadata'
        draft['title'] = (_meta(html, ['og:title', 'twitter:title']) or
                          (re.search(r'<title[^>]*>([\s\S]*?)</title>', html, re.I).group(1).strip()
                           if re.search(r'<title[^>]*>([\s\S]*?)</title>', html, re.I) else ''))[:200]
        draft['description'] = _meta(html, ['og:description', 'description'])
        draft['photo_url'] = _meta(html, ['og:image', 'twitter:image'])

    if not draft['title']:
        raise ImportFailed('No recipe found on that page — no title could be extracted.')
    if not draft['ingredients'] and not draft['instructions']:
        raise ImportFailed(
            'We could not find a readable recipe on that page. Some sites (like '
            'Allrecipes and BBC Good Food) block recipe readers or require '
            'JavaScript, so there is nothing to import. Try a different recipe '
            'URL from the same site, or add the recipe manually.'
        )
    return finalize_draft(draft)
