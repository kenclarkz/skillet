"""Validate recipe drafts sent by the browser-import bookmarklet.

The bookmarklet runs in the user's own browser on a recipe page they have
already opened, reads the page's schema.org Recipe data, and navigates to
/recipes/import-browser?data=<json>. That top-level GET carries the
existing login cookie (SameSite=Lax), so no tokens, CORS rules, or cookie
changes are needed — and the Skillet server never contacts the source site:
the draft arrives complete and is validated here before rendering.
"""
from __future__ import annotations

import json
import re

from app.lib.pdf_importer import _parse_time

MAX_PAYLOAD_BYTES = 100_000
MAX_TITLE = 200
MAX_DESCRIPTION = 1000
MAX_INGREDIENTS = 80
MAX_INSTRUCTIONS = 60
MAX_TAGS = 6


class BrowserImportError(Exception):
    """User-facing payload validation failure."""


def _str_list(value, cap: int) -> list:
    if isinstance(value, str):
        items = value.splitlines()
    elif isinstance(value, (list, tuple)):
        items = value
    else:
        return []
    out = []
    for item in items:
        if isinstance(item, dict):  # a raw HowToStep leaked through
            item = item.get('text') or item.get('name') or ''
        s = str(item).strip()
        if s:
            out.append(s)
    return out[:cap]


def _minutes(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        n = int(value)
    else:
        n = _parse_time(str(value))
        if n is None:
            return None
    return n if 0 <= n <= 1440 else None


def _servings(value):
    if value is None or isinstance(value, bool):
        return 4
    m = re.search(r'\d+', str(value))
    n = int(m.group(0)) if m else None
    return n if n is not None and 1 <= n <= 100 else 4


def _http_url(value, limit: int) -> str:
    s = str(value or '').strip()
    if len(s) <= limit and s.startswith(('http://', 'https://')):
        return s
    return ''


def _tags(value) -> list:
    if isinstance(value, str):
        items = value.split(',')
    elif isinstance(value, (list, tuple)):
        items = value
    else:
        return []
    tags = [str(t).strip()[:200] for t in items if str(t).strip()]
    return tags[:MAX_TAGS]


def parse_payload(raw: str) -> dict:
    """Turn the bookmarklet's JSON into the shared recipe-draft shape.

    Raises BrowserImportError with a message safe to show the user.
    """
    if raw is None or not str(raw).strip():
        raise BrowserImportError(
            'No recipe data was received. Open a recipe page and click your '
            'Skillet Import bookmark again.'
        )
    if len(raw) > MAX_PAYLOAD_BYTES:
        raise BrowserImportError(
            'That recipe data is too large to import. Use Import Recipe PDF '
            'or paste the recipe text instead.'
        )
    try:
        obj = json.loads(raw)
    except ValueError:
        raise BrowserImportError(
            'The recipe data was not valid JSON. Try the import again, or use '
            'Import Recipe PDF instead.'
        )
    if not isinstance(obj, dict):
        raise BrowserImportError(
            'The recipe data was not a recipe object. Try the import again, '
            'or use Import Recipe PDF instead.'
        )
    title = str(obj.get('title') or '').strip()
    if not title:
        raise BrowserImportError(
            'No recipe title was found on that page. The page may not publish '
            'recipe data — try Import Recipe PDF or paste the recipe text.'
        )
    return {
        'title': title[:MAX_TITLE],
        'description': (str(obj.get('description') or '').strip()[:MAX_DESCRIPTION] or None),
        'photo_url': _http_url(obj.get('photo_url'), 2000) or None,
        'prep_minutes': _minutes(obj.get('prep_minutes')),
        'cook_minutes': _minutes(obj.get('cook_minutes')),
        'servings': _servings(obj.get('servings')),
        'tags': _tags(obj.get('tags')),
        'ingredients': _str_list(obj.get('ingredients'), MAX_INGREDIENTS),
        'instructions': _str_list(obj.get('instructions'), MAX_INSTRUCTIONS),
        'step_photos': [],
        'source_url': _http_url(obj.get('source_url'), 500),
        'method': 'browser',
    }


# ---------------------------------------------------------------------------
# The bookmarklet
# ---------------------------------------------------------------------------
# Authored as readable JS; whitespace is collapsed to a single line because
# browsers strip newlines out of javascript: URLs before executing them.
_SCRIPT = r'''(function () {
  var B = '__BASE__';
  function findRecipe(o) {
    if (!o || typeof o !== 'object') return null;
    if (o instanceof Array) { for (var i = 0; i < o.length; i++) { var r = findRecipe(o[i]); if (r) return r; } return null; }
    var t = o['@type'], ts = t instanceof Array ? t : (t ? [t] : []), j;
    for (j = 0; j < ts.length; j++) { if (String(ts[j]).toLowerCase() === 'recipe') return o; }
    if (o['@graph']) return findRecipe(o['@graph']);
    return null;
  }
  function dur(v) {
    if (v == null) return null;
    var s = String(v).replace(/\s+/g, ' ').trim();
    var m = s.match(/^PT?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$/i);
    if (m && (m[1] || m[2] || m[3])) return (+(m[1] || 0)) * 60 + (+(m[2] || 0)) + ((+(m[3] || 0)) >= 30 ? 1 : 0);
    var n = s.match(/(\d+)/); if (!n) return null;
    return /hour|hrs?|hr|\bh/i.test(s) ? +n[1] * 60 : +n[1];
  }
  function intOrNull(v) { if (v == null) return null; var m = String(v).match(/\d+/); return m ? +m[0] : null; }
  function text(v) { return (v == null ? '' : String(v)).replace(/\s+/g, ' ').trim(); }
  function flatten(v, out) {
    out = out || [];
    if (v == null) return out;
    if (typeof v === 'string') { v.split(/\r?\n/).forEach(function (x) { x = x.replace(/^\s*\d+[.)]\s*/, '').trim(); if (x) out.push(x); }); return out; }
    if (v instanceof Array) { v.forEach(function (x) { flatten(x, out); }); return out; }
    if (v.itemListElement) { flatten(v.itemListElement, out); return out; }
    if (v.text) { var s = text(v.text); if (s) out.push(s); }
    else if (v.name && !v['@type']) { var n2 = text(v.name); if (n2) out.push(n2); }
    return out;
  }
  function imgVal(v) {
    if (v instanceof Array) v = v[0];
    if (v && typeof v === 'object') v = v.url || v.contentUrl || v.content || null;
    if (typeof v === 'string' && /^https?:\/\//i.test(v)) return v;
    return null;
  }
  function meta(p) { var el = document.querySelector('meta[property="' + p + '"],meta[name="' + p + '"]'); return el ? el.getAttribute('content') : null; }
  var rec = null, sc = document.querySelectorAll('script[type="application/ld+json"]'), i;
  for (i = 0; i < sc.length && !rec; i++) {
    try { rec = findRecipe(JSON.parse(sc[i].textContent.replace(/^\s*<!--/, '').replace(/-->\s*$/, ''))); } catch (e) {}
  }
  var d = { title: '', description: '', prep_minutes: null, cook_minutes: null, servings: null, tags: [], ingredients: [], instructions: [], photo_url: null, source_url: location.href.split('#')[0] };
  if (rec) {
    d.title = text(rec.name);
    d.description = text(rec.description);
    d.prep_minutes = dur(rec.prepTime);
    d.cook_minutes = dur(rec.cookTime);
    d.servings = intOrNull(rec.recipeYield);
    var tg = rec.recipeCategory || rec.recipeCuisine || [];
    if (!(tg instanceof Array)) tg = [tg];
    d.tags = tg.map(text).filter(Boolean);
    var ing = rec.recipeIngredient || rec.ingredients || [];
    if (typeof ing === 'string') ing = ing.split(/\r?\n/);
    if (ing instanceof Array) d.ingredients = ing.map(text).filter(Boolean);
    d.instructions = flatten(rec.recipeInstructions);
    d.photo_url = imgVal(rec.image);
  }
  var box = document.querySelector('[itemtype="https://schema.org/Recipe"],[itemtype="http://schema.org/Recipe"]');
  if (box) {
    var el;
    if (!d.title) { el = box.querySelector('[itemprop="name"]'); d.title = el ? text(el.textContent) : ''; }
    if (!d.description) { el = box.querySelector('[itemprop="description"]'); d.description = el ? text(el.textContent) : ''; }
    if (!d.ingredients.length) { d.ingredients = Array.prototype.slice.call(box.querySelectorAll('[itemprop="recipeIngredient"],[itemprop="ingredients"]')).map(function (e) { return text(e.textContent); }).filter(Boolean); }
    if (!d.instructions.length) { d.instructions = flatten(Array.prototype.slice.call(box.querySelectorAll('[itemprop="recipeInstructions"]')).map(function (e) { return text(e.textContent); }).filter(Boolean)); }
    if (!d.prep_minutes) { el = box.querySelector('[itemprop="prepTime"]'); d.prep_minutes = dur(el ? (el.getAttribute('content') || el.textContent) : null); }
    if (!d.cook_minutes) { el = box.querySelector('[itemprop="cookTime"]'); d.cook_minutes = dur(el ? (el.getAttribute('content') || el.textContent) : null); }
    if (!d.servings) { el = box.querySelector('[itemprop="recipeYield"]'); d.servings = intOrNull(el ? (el.getAttribute('content') || el.textContent) : null); }
    if (!d.photo_url) { el = box.querySelector('[itemprop="image"]'); if (el) d.photo_url = imgVal(el.getAttribute('content') || el.getAttribute('src') || el.getAttribute('srcset')); }
  }
  if (!d.title) d.title = text(meta('og:title') || document.title);
  if (!d.description) d.description = text(meta('og:description') || meta('description'));
  if (!d.photo_url) d.photo_url = imgVal(meta('og:image') || meta('twitter:image'));
  d.title = d.title.slice(0, 200);
  d.description = (d.description || '').slice(0, 1000);
  d.ingredients = d.ingredients.slice(0, 80);
  d.instructions = d.instructions.slice(0, 60);
  d.tags = d.tags.slice(0, 6);
  if (!d.title || (!d.ingredients.length && !d.instructions.length)) {
    alert('Skillet could not find a recipe on this page. In Skillet, try Import Recipe PDF or paste the recipe text instead.');
    return;
  }
  var url = B + '/recipes/import-browser?data=' + encodeURIComponent(JSON.stringify(d));
  var w = window.open(url, '_blank');
  if (!w) location.href = url;
})();'''


def bookmarklet(base_url: str) -> str:
    """Return the ready-to-paste javascript: URL for the given Skillet host."""
    script = _SCRIPT.replace('__BASE__', str(base_url).rstrip('/'))
    return 'javascript:' + ' '.join(script.split())
