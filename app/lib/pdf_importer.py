"""Extract and parse recipe text from an uploaded PDF.

Text is extracted locally with PyMuPDF (fitz) — the original webpage is
never fetched, no external services or API keys are involved, and the
resulting draft uses the same shape as app.lib.importer.parse_recipe_html
so the existing recipe preview form works unchanged.
"""
from __future__ import annotations

import re
from html import unescape
from typing import Optional

from app.lib.draft import better_servings, derive_tags, finalize_draft
from app.lib.importer import _duration_minutes

MAX_PDF_PAGES = 64
MAX_TEXT_CHARS = 400_000
MIN_TEXT_CHARS = 3


class PdfImportError(Exception):
    """User-facing PDF failure — the message is shown to the user verbatim."""


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extract_pdf(data: bytes) -> tuple:
    """Return (text, title_hint) for a PDF, or raise PdfImportError.

    The bytes are parsed in memory; nothing is written to disk and no
    network request is made. The title hint picks the largest-font line
    near the top of the first page, which is how recipe PDFs set titles.
    """
    if not data or b'%PDF' not in data[:1024]:
        raise PdfImportError(
            "That file doesn't look like a PDF. In your browser use "
            "Print → Save as PDF, then upload the file again — or paste "
            "the recipe text into the box below."
        )
    try:
        import fitz
    except ImportError:  # pragma: no cover - dependency declared in requirements
        raise PdfImportError('PDF support (PyMuPDF) is not installed on this server.')
    try:
        doc = fitz.open(stream=data, filetype='pdf')
    except Exception:
        raise PdfImportError(
            'That file could not be opened as a PDF — it may be corrupt or '
            'truncated. Try re-saving it, or paste the recipe text below instead.'
        )
    try:
        if doc.needs_pass:
            raise PdfImportError(
                'That PDF is password-protected. Remove the password (or paste '
                'the recipe text below) and try again.'
            )
        if doc.page_count > MAX_PDF_PAGES:
            raise PdfImportError(
                f'That PDF has {doc.page_count} pages — it does not look like a '
                'single recipe. Upload just the recipe pages.'
            )
        title_hint = _title_hint(doc)
        parts = []
        total = 0
        try:
            for page in doc:
                text = page.get_text('text') or ''
                total += len(text)
                parts.append(text)
                if total > MAX_TEXT_CHARS:
                    break
        except Exception:
            raise PdfImportError(
                'That PDF could not be read — it may be damaged. Paste the '
                'recipe text below instead.'
            )
        text = '\n'.join(parts)
    finally:
        doc.close()

    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    if len(re.sub(r'\s+', '', text)) < MIN_TEXT_CHARS:
        raise PdfImportError(
            "We couldn't find any readable text in that PDF — it looks like a "
            'scan or image-only file. Copy the recipe text from the page and '
            'paste it into the box below to import it.'
        )
    return text[:MAX_TEXT_CHARS], title_hint


def _title_hint(doc) -> Optional[str]:
    """Largest-font line near the top of page 1, if it stands out."""
    try:
        page = doc[0]
        height = page.rect.height
        info = page.get_text('dict')
    except Exception:
        return None
    all_sizes = []
    candidates = []
    for block in info.get('blocks') or []:
        for line in block.get('lines') or []:
            spans = line.get('spans') or []
            text = ''.join(s.get('text', '') for s in spans).strip()
            if not text:
                continue
            size = max((s.get('size') or 0) for s in spans)
            all_sizes.append(size)
            y = (line.get('bbox') or [0, 0])[1]
            if 2 <= len(text) <= 100 and y < height * 0.6:
                candidates.append((size, text))
    if not candidates or len(all_sizes) < 3:
        return None
    sizes = sorted(all_sizes)
    body = sizes[len(sizes) // 2]
    best_size, best = max(candidates, key=lambda c: c[0])
    if body and best_size >= body * 1.3:
        return best[:200]
    return None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_ING_RE = re.compile(r'^(?:for\s+the\s+)?ingredients?\b(?!\s*\d)', re.I)
# An ingredient group heading like "For the sauce:" / "For the marinade".
_ING_GROUP_RE = re.compile(r'^for\s+the\s+.+?\s*[:\-–—]?\s*$', re.I)
_STEP_RE = re.compile(
    r'^(?:instructions?|directions?|method|preparation|steps?|how to (?:make|cook|prepare)'
    r'|to prepare|recipe steps)\b(?!\s*\d)', re.I)
_STOP_RE = re.compile(
    r'^(?:notes?|nutrition(?:al)?\s*(?:info(?:rmation)?|facts?)|tips?|serving suggestions?'
    r'|allergens?|storage|variations?|recipe notes|faqs?|for serving)\b', re.I)
# ``label: value`` or ``label value`` for a metadata line, anywhere on the
# line. Colons are optional; a stray leading bullet/number is tolerated.
# The value stops at the next known label so several labels can share a line.
_TIME_RE = re.compile(r'\b(prep(?:aration)?|cook(?:ing)?|total|ready\s*in|active|inactive)'
                      r'\s*(?:time)?\b\s*[:\-–—]?\s*(.+?)(?=\s*[•|\-–—]?\s*'
                      r'(?:prep(?:aration)?|cook(?:ing)?|total|ready\s*in|active|inactive|serves?|servings?|makes?|yields?)\b|$)',
                      re.I)
_TIME_RE2 = re.compile(r'^\s*[•\-–—*\d.]*\s*(prep(?:aration)?|cook(?:ing)?|total)\b\s*[:\-–—]\s*(.+)$', re.I)
_YIELD_RE = re.compile(r'\b(serves?|servings?|makes?|yields?)\b\s*[:\-–—]?\s*(.+)$', re.I)
_TAGS_RE = re.compile(
    r'\b(?:tags?|categories|category|cuisine|courses?)\b\s*[:\-–—]\s*(.+)$', re.I)
_PAGE_RE = re.compile(r'^(?:page\s*)?\d+$', re.I)
_URL_RE = re.compile(r'^(?:https?://|www\.)\S+$', re.I)
# A line starts a numbered step: "1. text", "2) text", "Step 3: text".
_NUM_RE = re.compile(r'^(?:[Ss]tep\s+)?\d{1,2}[.)](?=\s|$|[A-Z])|^[Ss]tep\s+\d{1,2}(?=[\s:.]|$)')
_UNIT_RE = re.compile(
    r'\b(?:cups?|tbsp|tsp|tablespoons?|teaspoons?|grams?|kg|ml|litres?|liters?|pounds?'
    r'|lbs?|oz|ounces?|cloves?|slices?|cans?|bunch(?:es)?|packets?|packs?|pinch(?:es)?'
    r'|dash(?:es)?|sticks?|sprigs?|heads?|pieces?|chunks?|blocks?|tins?|sachets?|quarts?'
    r'|pints?|gallons?)\b', re.I)
_BULLET_RE = re.compile(r'^[-–—•*]+\s*')
_QTY_START = '0123456789¼½¾⅓⅔⅛⅜⅝⅞'


def _lines(text: str) -> list:
    out = []
    for raw in (text or '').splitlines():
        line = unescape(raw)
        line = re.sub(r'\s+', ' ', line).strip().strip('|').strip()
        if line:
            out.append(line)
    return out


def _parse_time(fragment: Optional[str]) -> Optional[int]:
    if not fragment:
        return None
    s = ' '.join(str(fragment).split())
    n = _duration_minutes(s)
    if n is not None:
        return n
    total = 0
    found = False
    for m in re.finditer(r'(\d+)\s*(hours?|hrs?|hr|h|minutes?|mins?|min|m)(?![a-z])', s, re.I):
        total += int(m.group(1)) * 60 if m.group(2)[0].lower() == 'h' else int(m.group(1))
        found = True
    return total if found else None


def _strip_step_marker(line: str) -> str:
    line = re.sub(r'^(?:[Ss]tep\s*)?\d{1,2}[.)][\s:.\-–—]*', '', line)
    line = re.sub(r'^[Ss]tep\s+\d{1,2}[\s:.\-–—]*', '', line)
    return _BULLET_RE.sub('', line).strip()


def _looks_like_ingredient(line: str) -> bool:
    if line[:1].isdigit() or line[:1] in _QTY_START:
        return True
    if _UNIT_RE.search(line):
        return True
    return bool(re.search(r'\bto taste\b', line, re.I))


def _clean_ingredients(region: list) -> list:
    """Ingredient lines from a section, dropping group headings and blanks.

    Ingredient lists are often split by sub-headings like "For the sauce:"
    or "For the topping". Those labels become group markers rather than
    ingredients, and the actual amounts underneath are kept.
    """
    out = []
    for raw in region:
        line = _BULLET_RE.sub('', raw).strip()
        if not line:
            continue
        if _ING_RE.match(line) or _STEP_RE.match(line) or _STOP_RE.match(line):
            continue
        # a short label ending in a colon is a group heading, not an ingredient
        if line.endswith(':') and len(line) <= 40 and not _looks_like_ingredient(line):
            continue
        out.append(line)
    return out[:80]


def _leading_text_before_label(line: str) -> str:
    """Text before the first metadata label on a line, if it looks like a title.

    Handles PDFs that pack the title together with the first label, e.g.
    "Muffins  Prep Time 10 min". Returns '' when there is no usable lead.
    """
    m = _TIME_RE.search(line)
    if not m:
        return ''
    lead = line[:m.start()].strip(' \t-–—•|:')
    if 2 <= len(lead) <= 120 and not lead[:1].isdigit():
        return lead
    return ''


def _is_meta(line: str) -> bool:
    return bool(_ING_RE.match(line) or _STEP_RE.match(line) or _STOP_RE.match(line)
                or _TIME_RE.search(line) or _TIME_RE2.match(line) or _YIELD_RE.search(line)
                or _TAGS_RE.search(line) or _PAGE_RE.match(line))


def _scan_metadata(lines: list, draft: dict) -> None:
    """Pull times, yield and tags out of every line, keyword-first.

    Each line is searched for known labels ("prep time", "cook time",
    "total time", "ready in", "serves", "category", "cuisine", "tags"...).
    The value is whatever follows the label — with or without a colon — so
    layouts like "Prep Time 15 min", "Total Time: 25 minutes" and several
    labels packed on one line all work. A "total time"/"ready in" value
    fills cook time when cook time is otherwise absent.
    """
    for line in lines:
        matched = False
        for tm in _TIME_RE.finditer(line):
            label = tm.group(1).lower()
            value = tm.group(2)
            if label.startswith('prep'):
                key = 'prep'
            elif label.startswith(('cook', 'total', 'ready')):
                key = 'cook'
            else:  # active / inactive — not a cooking-time field
                key = None
            if key and draft[f'{key}_minutes'] is None:
                n = _parse_time(value)
                if n is not None:
                    draft[f'{key}_minutes'] = n
            matched = True

        ym = _YIELD_RE.search(line)
        if ym:
            n = better_servings(ym.group(2) or ym.group(0))
            if n is not None and draft['servings'] == 4:
                draft['servings'] = n
            matched = True

        for tag in _TAGS_RE.finditer(line):
            draft['tags'] = derive_tags(draft['tags'], tag.group(1))
            matched = True

        if matched:
            continue


def _steps_from_region(region: list) -> list:
    """Turn an instruction section into steps.

    If any line carries a number marker ("1.", "Step 2:"), continuation
    lines are merged into the current step (PDFs wrap long lines).
    Otherwise each line is one step — matching the form's line-per-step
    convention.
    """
    if any(_NUM_RE.match(ln) for ln in region):
        steps = []
        current = ''
        for line in region:
            if _NUM_RE.match(line):
                if current:
                    steps.append(current)
                current = _strip_step_marker(line)
            elif current:
                current = f'{current} {line}'
            else:
                current = _strip_step_marker(line)
        if current:
            steps.append(current)
        return [s for s in (s.strip() for s in steps) if s]
    return [s for s in (_BULLET_RE.sub('', ln).strip() for ln in region) if s]


def _finish_draft(draft: dict, steps: list) -> None:
    steps = steps[:60]
    if len(steps) == 1 and len(steps[0]) > 250:
        split = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9])', steps[0])
        steps = [s.strip() for s in split if s.strip()][:60]
    draft['instructions'] = steps
    draft['step_photos'] = [''] * len(steps)


def parse_recipe_text(text: str, origin: str = '',
                      title_hint: Optional[str] = None) -> dict:
    """Parse extracted/pasted recipe text into an editable draft dict.

    `origin` (usually the PDF filename) and `title_hint` (largest-font
    line from the PDF) are the title fallbacks. Always returns a draft —
    a raw fallback keeps unrecognisable layouts editable instead of
    erroring out.
    """
    lines = _lines(text)
    if not lines:
        raise PdfImportError(
            'There is no text to import. Copy the recipe text and paste it '
            'into the box below instead.'
        )

    draft = {
        'title': '', 'description': None, 'photo_url': None,
        'prep_minutes': None, 'cook_minutes': None, 'servings': 4,
        'tags': [], 'ingredients': [], 'instructions': [], 'step_photos': [],
        'source_url': '', 'method': 'pdf',
    }

    # --- metadata lines (times, yield, tags) — anywhere in the document ----
    _scan_metadata(lines, draft)

    # --- section headers ---------------------------------------------------
    ing_i = step_i = stop_i = None
    for i, line in enumerate(lines):
        if _STOP_RE.match(line) and stop_i is None and (ing_i is not None or step_i is not None):
            stop_i = i
        if ing_i is None and (_ING_RE.match(line) or _ING_GROUP_RE.match(line)):
            ing_i = i
        elif step_i is None and (ing_i is None or i > ing_i) and _STEP_RE.match(line):
            step_i = i

    # --- title -------------------------------------------------------------
    title_idx = None
    hint = (title_hint or '').strip()
    if hint:
        draft['title'] = hint[:200]
        title_idx = next((i for i, ln in enumerate(lines) if ln[:200] == draft['title']), None)
    for i, line in enumerate(lines[:12]):
        if draft['title']:
            break
        if (ing_i is not None and i > ing_i) or (step_i is not None and i > step_i):
            continue  # inside a section — content, not a title
        if _is_meta(line) or _URL_RE.match(line) or '@' in line:
            # a line that also starts with real text before its first
            # metadata label ("Muffins  Prep Time 10 min") can still be a title
            lead = _leading_text_before_label(line)
            if lead and not draft['title']:
                title_idx = i
                draft['title'] = lead[:200]
            continue
        title_idx = i
        draft['title'] = line[:200]
    if not draft['title']:
        draft['title'] = (origin or 'Imported recipe').strip()[:200]

    # --- sections ----------------------------------------------------------
    def section_bounds(start):
        end = len(lines)
        for j in (stop_i, ing_i, step_i):
            if j is not None and start < j < end:
                end = j
        return end

    if ing_i is not None:
        end = len(lines)
        for j in (step_i, stop_i):
            if j is not None and ing_i < j < end:
                end = j
        draft['ingredients'] = _clean_ingredients(lines[ing_i + 1:end])

        # description: a blurb between the title and the first section header
        first_section = min([j for j in (ing_i, step_i) if j is not None], default=len(lines))
        for i, line in enumerate(lines):
            if i <= (title_idx if title_idx is not None else -1) or i >= first_section:
                continue
            if line[:200] == draft['title']:
                continue
            if len(line) >= 40 and not _URL_RE.match(line) and not _is_meta(line):
                draft['description'] = line[:1000]
                break

    # --- instructions ------------------------------------------------------
    if step_i is not None:
        steps = _steps_from_region(lines[step_i + 1:section_bounds(step_i)])
        _finish_draft(draft, steps)
    else:
        # No instructions header: look for numbered steps after the
        # ingredients section (or after the title when there is one).
        if ing_i is not None:
            scan_from = len(lines)
            for j in (stop_i, step_i):
                if j is not None and ing_i < j < scan_from:
                    scan_from = j
        else:
            scan_from = (title_idx + 1) if title_idx is not None else 0
        numbered = [i for i in range(scan_from, len(lines)) if _NUM_RE.match(lines[i])]
        if numbered:
            steps = _steps_from_region(lines[numbered[0]:])
            _finish_draft(draft, steps)
            if not draft['ingredients']:
                pre = _clean_ingredients(lines[scan_from:numbered[0]])
                draft['ingredients'] = [ln for ln in pre if _looks_like_ingredient(ln)][:80]

    # --- no recognizable structure: raw fallback ---------------------------
    if not draft['ingredients'] and not draft['instructions']:
        draft['method'] = 'pdf-raw'
        keep = []
        for i, line in enumerate(lines):
            if i == title_idx or line[:200] == draft['title'] or _is_meta(line) or _URL_RE.match(line):
                continue
            keep.append(line)
        is_ingredient = [False] * len(keep)
        for i, line in enumerate(keep):
            if _looks_like_ingredient(line):
                is_ingredient[i] = True
            elif len(line) > 60 or line.endswith(('.', '!', '?')):
                draft['instructions'].append(line)
            else:
                is_ingredient[i] = True
        draft['ingredients'] = [ln for ln, flag in zip(keep, is_ingredient) if flag][:80]
        _finish_draft(draft, draft['instructions'])

    if not draft['title']:
        draft['title'] = (origin or 'Imported recipe').strip()[:200]
    return finalize_draft(draft)
