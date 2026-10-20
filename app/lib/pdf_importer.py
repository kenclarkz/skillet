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
_STEP_RE = re.compile(
    r'^(?:instructions?|directions?|method|preparation|steps?|how to (?:make|cook|prepare)'
    r'|to prepare|recipe steps)\b(?!\s*\d)', re.I)
_STOP_RE = re.compile(
    r'^(?:notes?|nutrition(?:al)?\s*(?:info(?:rmation)?|facts?)|tips?|serving suggestions?'
    r'|allergens?|storage|variations?|recipe notes|faqs?|for serving)\b', re.I)
_TIME_RE = re.compile(r'^(prep(?:aration)?|cook(?:ing)?)\s+time\b\s*[:\-–—]?\s*(.+)$', re.I)
_TIME_RE2 = re.compile(r'^(prep(?:aration)?|cook(?:ing)?)\s*[:\-–—]\s*(.+)$', re.I)
_YIELD_RE = re.compile(r'^(serves?|servings?|makes?|yields?)\b', re.I)
_TAGS_RE = re.compile(r'^(?:tags?|categories|category|cuisine|courses?)\b\s*[:\-–—]\s*(.+)$', re.I)
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


def _is_meta(line: str) -> bool:
    return bool(_ING_RE.match(line) or _STEP_RE.match(line) or _STOP_RE.match(line)
                or _TIME_RE.match(line) or _TIME_RE2.match(line) or _YIELD_RE.match(line)
                or _PAGE_RE.match(line))


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
    for line in lines:
        m = _TIME_RE.match(line) or _TIME_RE2.match(line)
        if m:
            key = 'prep' if m.group(1).lower().startswith('prep') else 'cook'
            if draft[f'{key}_minutes'] is None:
                draft[f'{key}_minutes'] = _parse_time(m.group(2))
        elif _YIELD_RE.match(line) and draft['servings'] == 4:
            n = better_servings(line)
            if n is not None:
                draft['servings'] = n
        else:
            tm = _TAGS_RE.match(line)
            if tm:
                draft['tags'] = derive_tags(draft['tags'], tm.group(1))

    # --- section headers ---------------------------------------------------
    ing_i = step_i = stop_i = None
    for i, line in enumerate(lines):
        if _STOP_RE.match(line) and stop_i is None and (ing_i is not None or step_i is not None):
            stop_i = i
        if ing_i is None and _ING_RE.match(line):
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
        if _is_meta(line) or _URL_RE.match(line) or '@' in line:
            continue
        if (ing_i is not None and i > ing_i) or (step_i is not None and i > step_i):
            continue  # inside a section — content, not a title
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
        draft['ingredients'] = [
            _BULLET_RE.sub('', ln).strip()
            for ln in lines[ing_i + 1:end] if _BULLET_RE.sub('', ln).strip()
        ][:80]

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
            if ing_i is None:
                pre = [ln for i, ln in enumerate(lines[scan_from:numbered[0]])
                       if not _is_meta(ln) and not _URL_RE.match(ln)]
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
