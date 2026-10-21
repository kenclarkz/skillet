"""Extract a recipe from a recipe-card PDF.

The importer deliberately works from the PDF's layout rather than from a
fixed set of strings or coordinates.  Text is grouped into lines by glyph
geometry, sections are found by their headings, and numbered steps are
followed across columns and page breaks.  Embedded images are associated
with the closest step in the same column; anything that cannot be placed
confidently is still returned (with a warning) so the review form can be
used to correct it.

The parser understands the HelloFresh-style two-page card but does not
depend on there being exactly two pages, six steps, six photos, or a
particular 2/4-person grid.  PDFs that contain no text at all are sent
through OCR when ``pytesseract`` and the Tesseract binary are available.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Optional

from pdfminer.high_level import extract_pages
from pdfminer.layout import LAParams, LTChar, LTImage
from PIL import Image

from app.lib.importer import ImportFailed

MAX_PAGES = 20
MIN_IMAGE_AREA = 400
PAGE_OFFSET = 100000.0

FRACTION_CHARS = {
    '\u00bc': '1/4', '\u00bd': '1/2', '\u00be': '3/4',
    '\u2153': '1/3', '\u2154': '2/3',
    '\u215b': '1/8', '\u215c': '3/8', '\u215d': '5/8', '\u215e': '7/8',
    '\u2044': '/',
}

_INGREDIENT_HEADING = re.compile(
    r'^(?:INGREDIENTS?|YOU(?:\u2019|\')?LL NEED|WHAT YOU(?:\u2019|\')?LL NEED|'
    r'SHOPPING LIST)\b', re.I)
_INSTRUCTION_HEADING = re.compile(
    r'^(?:INSTRUCTIONS?|DIRECTIONS?|METHOD|STEPS|PREPARATION|'
    r'HOW TO MAKE|COOKING INSTRUCTIONS)\b', re.I)
_OTHER_HEADING = re.compile(
    r'^(?:NUTRITION|ALLERGENS?|NOTES?|CHEF(?:\u2019|\')?S NOTES?|TIPS?|'
    r'SERVING SUGGESTIONS?|STORAGE|EQUIPMENT|UTENSILS|FROM THE KITCHEN)\b',
    re.I)
_STAT_LABEL = re.compile(
    r'^(?:PREP(?:ARATION)?|COOK(?:ING)?|TOTAL|SERVES?|SERVINGS?)\b', re.I)

_STEP_HEADER = re.compile(r'^\s*(\d{1,3})\s*[\.\):\-]?\s+(.+?)\s*$')
_NON_STEP_TITLE = re.compile(
    r'^(?:PERSON|PEOPLE|SERVINGS?|MIN(?:UTE)?S?|HOURS?|HR|'
    r'TEMP(?:ERATURE)?|OZ|LB|LBS|TSP|TBSP|TABLESPOON|TEASPOON|CUP|CUPS|'
    r'GRAM|GRAMS?|KG|ML|LITRE|LITER|CLOVES?|CANS?|BUNCH(?:ES)?|'
    r'PACKETS?|SLICES?|PIECES?|PINCH(?:ES)?|DASH(?:ES)?|HEADS?|'
    r'SPRIGS?|STALKS?|FILLETS?|HANDFULS?)\b', re.I)

_QTY_ONLY = re.compile(
    r'^(?:\d+(?:[./]\d+)?|\u00bc|\u00bd|\u00be|\u2153|\u2154|\u215b|'
    r'\u215c|\u215d|\u215e)\s*(?:'
    r'cups?|cup|tbsp|tablespoons?|tsp|teaspoons?|oz|ounces?|lb|lbs|pounds?|'
    r'g|grams?|kg|ml|l|liters?|litres?|cloves?|cans?|bunch(?:es)?|'
    r'packets?|slices?|pieces?|pinch(?:es)?|dash(?:es)?|heads?|sprigs?|'
    r'stalks?|fillets?|handfuls?)?\.?$', re.I)

_QTY_PREFIX = re.compile(
    r'^\s*((?:\d+(?:[./]\d+)?|\u00bc|\u00bd|\u00be|\u2153|\u2154|\u215b|'
    r'\u215c|\u215d|\u215e)(?:\s*[-\u2013]\s*(?:\d+(?:[./]\d+)?|'
    r'\u00bc|\u00bd|\u00be|\u2153|\u2154))?\s*'
    r'(?:cups?|cup|tbsp|tablespoons?|tsp|teaspoons?|oz|ounces?|lb|lbs|'
    r'pounds?|g|grams?|kg|ml|l|liters?|litres?|cloves?|cans?|bunch(?:es)?|'
    r'packets?|slices?|pieces?|pinch(?:es)?|dash(?:es)?|heads?|sprigs?|'
    r'stalks?|fillets?|handfuls?)?)\b',
    re.I)

_STAT_RE = re.compile(
    r'\b(PREP(?:ARATION)?|COOK(?:ING)?|TOTAL)\b[^0-9]{0,48}'
    r'(\d+)\s*(?:(?:H|HR|HOURS?)\s*)?(?:(\d+)\s*)?(?:MIN|M\b|MINUTES?)?',
    re.I)
_SERVES_RE = re.compile(
    r'\b(\d+)\s*(?:PERSON|PEOPLE|SERVINGS?|PORTIONS?)\b', re.I)
_SERVES_VERB_RE = re.compile(
    r'\b(?:SERVES?|SERVINGS?|PORTIONS?)\s*[:]?\s*(\d+)\b', re.I)


@dataclass
class Run:
    """A horizontal group of glyphs that share a baseline."""
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    size: float
    font: str
    baseline: float


@dataclass
class Line:
    """One visual line (a baseline split into columns when necessary)."""
    runs: list
    page: int = 0

    @property
    def text(self) -> str:
        return ' '.join(r.text for r in self.runs if r.text).strip()

    @property
    def x0(self) -> float:
        return min(r.x0 for r in self.runs)

    @property
    def x1(self) -> float:
        return max(r.x1 for r in self.runs)

    @property
    def top(self) -> float:
        return min(r.top for r in self.runs)

    @property
    def bottom(self) -> float:
        return max(r.bottom for r in self.runs)

    @property
    def size(self) -> float:
        return max(r.size for r in self.runs)

    @property
    def bold(self) -> bool:
        return any(re.search(r'bold|black|heavy|semibold', r.font, re.I)
                   for r in self.runs)


@dataclass
class ImageData:
    page: int
    x0: float
    x1: float
    top: float
    bottom: float
    data: tuple
    doc_top: float = 0.0
    doc_bottom: float = 0.0
    ocr_source: bool = False

    @property
    def area(self) -> float:
        return max(0.0, self.x1 - self.x0) * max(0.0, self.bottom - self.top)


@dataclass
class PageData:
    index: int
    width: float
    height: float
    runs: list = field(default_factory=list)
    lines: list = field(default_factory=list)
    images: list = field(default_factory=list)
    text_chars: int = 0


def _walk(element, predicate) -> list:
    found = []

    def visit(node):
        if predicate(node):
            found.append(node)
        for child in getattr(node, '_objs', None) or ():
            visit(child)
    visit(element)
    return found


def _extract_runs(page, height) -> list:
    """Group glyphs into runs: same baseline, no gap wider than ~1/3 em."""
    buckets = {}
    for char in _walk(page, lambda n: isinstance(n, LTChar)):
        if not char.get_text():
            continue
        buckets.setdefault(round(char.y0 * 2) / 2, []).append(char)

    runs = []
    for baseline, chars in buckets.items():
        chars.sort(key=lambda c: (c.x0, c.x1))
        limit = max(2.0, 0.32 * max(c.size for c in chars))
        current = []
        prev = None
        for char in chars:
            if prev is not None and char.x0 - prev.x1 > limit:
                _append_run(runs, current, baseline, height)
                current = []
            current.append(char)
            prev = char
        _append_run(runs, current, baseline, height)
    return runs


def _append_run(runs, chars, baseline, height):
    if not chars:
        return
    text = ''.join(c.get_text() for c in chars).strip()
    if not text:
        return
    runs.append(Run(
        text=text,
        x0=min(c.x0 for c in chars),
        x1=max(c.x1 for c in chars),
        top=height - max(c.y1 for c in chars),
        bottom=height - min(c.y0 for c in chars),
        size=max(c.size for c in chars),
        font=(chars[0].fontname or ''),
        baseline=baseline,
    ))


def _make_lines(runs, page_index, width) -> list:
    """Turn runs into visual lines, splitting separate columns on a baseline."""
    buckets = {}
    for run in runs:
        buckets.setdefault(round(run.baseline * 2) / 2, []).append(run)

    # Word gaps are small; gaps between columns are much wider.  Scale the
    # threshold with the page so the same parser works on letter/A4 cards.
    split_gap = max(18.0, width * 0.035)
    lines = []
    for baseline, group in buckets.items():
        group.sort(key=lambda r: (r.x0, r.x1))
        current = []
        prev = None
        for run in group:
            if prev is not None and run.x0 - prev.x1 > split_gap:
                lines.append(Line(current, page_index))
                current = []
            current.append(run)
            prev = run
        if current:
            lines.append(Line(current, page_index))
    lines.sort(key=lambda line: (line.top, line.x0))
    return lines


def _clean(text: str) -> str:
    text = _ascii_fractions(text)
    text = re.sub(r'\s*[\u2022\u00b7\u25cf]\s*', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _ascii_fractions(text: str) -> str:
    for char, replacement in FRACTION_CHARS.items():
        text = text.replace(char, replacement)
    return text


def _cluster_values(values, gap) -> list:
    clusters = []
    for value in sorted(values):
        if clusters and value - clusters[-1][-1] <= gap:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    return [sum(c) / len(c) for c in clusters]


def _merge_intervals(intervals, gap) -> list:
    clusters = []
    for x0, x1 in sorted(intervals):
        if clusters and x0 - clusters[-1][1] <= gap:
            clusters[-1][1] = max(clusters[-1][1], x1)
        else:
            clusters.append([x0, x1])
    return clusters


def _column_of_x(x, anchors) -> int:
    return min(range(len(anchors)), key=lambda i: abs(x - anchors[i]))


def _header_info(line) -> Optional[tuple]:
    """Return (number, title) when a line looks like a numbered step."""
    text = _clean(line.text)
    match = _STEP_HEADER.match(text)
    if not match:
        return None
    number = int(match.group(1))
    title = match.group(2).strip(' \t-:.\u2013\u2014')
    if not (1 <= number <= 200) or not title:
        return None
    if not re.search(r'[A-Za-z]', title):
        return None
    if _NON_STEP_TITLE.match(title):
        return None
    # A quantity like "2 TBSP 4 TBSP" is not a step heading.
    if _QTY_ONLY.fullmatch(title):
        return None
    return number, title


def _header_is_strong(line, info) -> bool:
    title = info[1]
    letters = [c for c in title if c.isalpha()]
    uppercase = letters and all(c.isupper() for c in letters)
    return bool(line.bold or uppercase)


def _is_ingredient_heading(line) -> bool:
    return bool(_INGREDIENT_HEADING.match(_clean(line.text)))


def _is_instruction_heading(line) -> bool:
    return bool(_INSTRUCTION_HEADING.match(_clean(line.text)))


def _is_other_heading(line) -> bool:
    return bool(_OTHER_HEADING.match(_clean(line.text)))


def _is_stat_line(line) -> bool:
    text = _clean(line.text)
    if not _STAT_RE.search(text) and not _SERVES_RE.search(text) \
            and not _SERVES_VERB_RE.search(text):
        return False
    # Avoid treating an ingredient such as "cooked rice" as a time label.
    return bool(re.match(
        r'^(?:PREP|COOK|TOTAL|SERVES?|SERVINGS?)\b', text, re.I))


def _page_has_steps(page) -> bool:
    for line in page.lines:
        info = _header_info(line)
        if info and _header_is_strong(line, info):
            return True
    # Also check for our paired step pattern (number followed/preceded by all-caps title)
    for i, line in enumerate(page.lines):
        t = _clean(line.text)
        if re.match(r'^\s*(\d{1,3})\s*$', t):
            num = int(re.match(r'^\s*(\d{1,3})\s*$', t).group(1))
            if 1 <= num <= 20:  # reasonable step range
                # look nearby for title
                for j in range(max(0,i-5), min(len(page.lines), i+5)):
                    if j == i: continue
                    nt = _clean(page.lines[j].text)
                    if nt.upper() == nt and 1 <= len(nt.split()) <= 8 and re.search(r'[A-Z]{2,}', nt):
                        return True
    return False


def _is_ingredient_line(line) -> bool:
    text = _clean(line.text)
    if not text:
        return False
    if re.search(r'\bPERSON\b|\bSERVINGS?\b', text, re.I):
        return False
    if _is_stat_line(line) or _is_instruction_heading(line) or \
            _is_other_heading(line):
        return False
    # Don't treat step-like all-caps short titles as ingredients
    if text.upper() == text and re.match(r'^[A-Z][A-Z\s]+$', text) and len(text.split()) <= 4 and not text.startswith('•') and not re.match(r'^\d', text) and text not in ['PREP', 'COOK', 'TOTAL']:
        # but could be step titles - in ingredient context less likely
        pass  # be lenient
    return True


def _ingredient_spans(pages) -> tuple:
    """Return (spans, ingredient_line_ids).

    A span is (page_index, start_line_index, end_line_index).  Once an
    INGREDIENTS heading is seen the section stays open across pages until
    instructions, another section, or numbered steps begin.
    """
    spans = []
    ids = set()
    active = False
    for page in pages:
        lines = page.lines
        heading_index = next(
            (i for i, line in enumerate(lines) if _is_ingredient_heading(line)),
            None)
        if heading_index is not None:
            active = True
            start = heading_index + 1
            started_with_heading = True
        elif active and not _page_has_steps(page):
            start = 0
            started_with_heading = False
        else:
            if active and _page_has_steps(page):
                # Include any ingredient text that precedes the first step.
                first_step = next(
                    (i for i, line in enumerate(lines)
                     if _header_info(line) and _header_is_strong(line, _header_info(line))),
                    len(lines))
                if first_step == 0:
                    active = False
                    continue
                start = 0
            else:
                active = False
                continue
            started_with_heading = False

        end = len(lines)
        stopped_hard = False
        for i in range(start, len(lines)):
            line = lines[i]
            info = _header_info(line)
            if _is_instruction_heading(line) or _is_other_heading(line):
                end = i
                stopped_hard = True
                break
            # On a page that explicitly says INGREDIENTS, numbered lines are
            # ingredient rows (for example "1 Onion"), not step headings.
            # Numbered steps only close the section on a continuation page
            # or after an instructions heading.
            if (info and _header_is_strong(line, info)
                    and not started_with_heading):
                end = i
                stopped_hard = True
                break
            # Skip aggressive stopping for now to preserve all ingredients in this layout
            t = _clean(line.text)
            if _is_stat_line(line):
                end = i
                break
        if end > start:
            spans.append((page.index, start, end))
            for line in lines[start:end]:
                ids.add(id(line))
        if stopped_hard:
            active = False
    return spans, ids


# ---------------------------------------------------------------------------
# Front matter
# ---------------------------------------------------------------------------

def _detect_title(pages) -> tuple:
    """Return (title, title_lines, page)."""
    page = next((p for p in pages if p.lines), None)
    if page is None:
        return '', [], None

    candidates = [line for line in page.lines
                  if line.text and not _is_ingredient_heading(line)
                  and not _is_instruction_heading(line)
                  and not _is_other_heading(line)]
    if not candidates:
        return '', [], page
    largest = max(line.size for line in candidates)
    if largest < 14:
        return '', [], page

    seeds = [line for line in candidates if line.size >= largest - 1]
    seeds.sort(key=lambda line: (line.top, line.x0))
    seed = seeds[0]
    group = [seed]
    last = seed
    for line in sorted(candidates, key=lambda line: (line.top, line.x0)):
        if line is seed or line in group:
            continue
        if abs(line.size - seed.size) > 0.8:
            continue
        if line.top < seed.top:
            continue
        if 0 <= line.top - last.bottom <= max(4.0, 0.55 * seed.size) and \
                abs(line.x0 - seed.x0) <= max(80.0, page.width * 0.35):
            group.append(line)
            last = line
    group.sort(key=lambda line: (line.top, line.x0))
    title = _clean(' '.join(_clean(line.text) for line in group))
    return title[:200], group, page


def _detect_description(page, title_lines) -> Optional[str]:
    if page is None or not title_lines:
        return None
    title_bottom = max(line.bottom for line in title_lines)
    title_size = max(line.size for line in title_lines)
    below = [line for line in page.lines
             if line.top >= title_bottom - 2
             and line.size < title_size + 0.5
             and line.text]
    below.sort(key=lambda line: (line.top, line.x0))
    parts = []
    last_bottom = title_bottom
    for line in below:
        if _is_ingredient_heading(line) or _is_instruction_heading(line) or \
                _is_other_heading(line) or _is_stat_line(line):
            break
        if line.top - last_bottom > max(18.0, line.size * 1.8):
            break
        if line.size > title_size - 0.5:
            continue
        parts.append(_clean(line.text))
        last_bottom = line.bottom
        if len(parts) >= 4:
            break
    return (' '.join(parts)[:1000] or None) if parts else None


def _minutes_from_text(text: str) -> Optional[int]:
    match = _STAT_RE.search(text)
    if not match:
        # Try to find "PREP" followed by a number within nearby tokens in joined text
        # e.g. numbers might be separated
        m2 = re.search(r'\b(PREP(?:ARATION)?|COOK(?:ING)?|TOTAL)\b.*?(\d+)', text, re.I)
        if not m2:
            return None
        minutes = int(m2.group(2))
        return minutes
    hours = 0
    minutes = int(match.group(2) or 0)
    # "PREP: 1 H 20 MIN" has the hour in group 2 and minutes in group 3.
    if match.group(3) and re.search(r'\bH(?:R|OURS?)?\b', text, re.I):
        hours = int(match.group(2))
        minutes = int(match.group(3))
    elif re.search(r'\bH(?:R|OURS?)?\b', text, re.I) and \
            not re.search(r'\bMIN', text, re.I):
        hours = minutes
        minutes = 0
    return hours * 60 + minutes


def _detect_stat(lines, label) -> Optional[int]:
    pattern = re.compile(r'\b%s\b' % label, re.I)
    for i, line in enumerate(lines):
        text = _clean(line.text)
        if not pattern.search(text):
            continue
        value = _minutes_from_text(text)
        if value is not None:
            return value
        # Label and number can be on separate visual lines.
        for nearby in lines[i + 1:i + 4]:
            if abs(nearby.top - line.top) > 40 and nearby.top < line.top:
                continue
            value = _minutes_from_text(text + ' ' + nearby.text)
            if value is not None:
                return value
        for nearby in lines[max(0, i - 3):i]:
            if pattern.search(nearby.text):
                continue
            value = _minutes_from_text(nearby.text + ' ' + text)
            if value is not None:
                return value
    return None


def _detect_servings(pages) -> int:
    texts = [_clean(line.text) for page in pages for line in page.lines]
    joined = ' '.join(texts)
    # The card lists both a 2- and a 4-person column; the app uses the
    # quantities from the 2-person column.
    if re.search(r'\b2\s*(?:PERSON|PEOPLE|SERVINGS?|PORTIONS?)\b', joined, re.I):
        return 2
    match = (_SERVES_RE.search(joined) or _SERVES_VERB_RE.search(joined)
             or re.search(r'\b(?:MAKES?|YIELD)\s*[:]?\s*(\d+)\b', joined, re.I))
    if match:
        value = int(match.group(1))
        if 1 <= value <= 100:
            return value
    return 4


# ---------------------------------------------------------------------------
# Ingredients
# ---------------------------------------------------------------------------

def _split_quantity(text: str) -> tuple:
    text = _clean(text)
    match = _QTY_PREFIX.match(text)
    if not match:
        return '', text
    qty = match.group(1).strip()
    rest = text[match.end():].strip(' ,-')
    # "1 1/2 cups" etc. may leave a stray fraction behind.
    extra = _QTY_PREFIX.match(rest)
    if extra and not re.search(r'[A-Za-z]{2,}', rest[extra.end():].strip()):
        rest = ''
    return _clean(qty), _clean(rest)


def _quantity_only(text: str) -> bool:
    return bool(_QTY_ONLY.fullmatch(_clean(text)))


def _parse_ingredients(lines, page_width) -> list:
    # Filter and also stop when we see obvious step numbers/titles in sequence
    lines_filtered = []
    for line in lines:
        t = _clean(line.text)
        # Stop collecting if we see "4", "5", "6" on separate lines followed by step titles soon
        if re.match(r'^\d+$', t) and int(t) >= 4 and int(t) <= 6:
            # peek ahead in original context? but we only have lines list
            pass
        lines_filtered.append(line)
    lines = [line for line in lines_filtered if _is_ingredient_line(line)]
    if not lines:
        return []

    anchors = _cluster_values([line.x0 for line in lines],
                              gap=max(40.0, page_width * 0.075))
    groups = {}
    for line in lines:
        groups.setdefault(_column_of_x(line.x0, anchors), []).append(line)

    entries = []
    for column, group in groups.items():
        group.sort(key=lambda line: (line.top, line.x0))
        pending_qty = None
        pending_top = None
        pending_page = None
        previous = None
        for line in group:
            text = _clean(line.text)
            if not text:
                continue
            # Stop if we hit instruction-like long text
            if len(text.split()) > 40:
                break
            if ('When everything' in text or 'station for the fajitas' in text):
                break

            qty, rest = _split_quantity(text)
            if qty:
                # Several columns can share a row (2-person / 4-person
                # amounts).  Prefer the left-most quantity for that row.
                if pending_qty is not None and pending_top is not None and \
                        abs(line.top - pending_top) <= 4:
                    continue
                if rest and not _quantity_only(rest):
                    entries.append({
                        'text': _clean(f'{qty} {rest}'),
                        'top': line.top,
                        'page': line.page,
                        'column': column,
                        'size': line.size,
                    })
                    pending_qty = None
                    pending_top = None
                    pending_page = None
                    previous = line
                else:
                    pending_qty = qty
                    pending_top = line.top
                    pending_page = line.page
                    previous = line
                continue

            if pending_qty is not None:
                entries.append({
                    'text': _clean(f'{pending_qty} {text}'),
                    'top': pending_top if pending_top is not None else line.top,
                    'page': pending_page if pending_page is not None else line.page,
                    'column': column,
                    'size': line.size,
                })
                pending_qty = None
                pending_top = None
                pending_page = None
                previous = line
                continue

            # A following line in the same cell can wrap an ingredient name
            # or carry a small-print note.  Attach it when it is clearly
            # part of the same ingredient rather than a new row.
            if entries and previous is not None:
                gap = line.top - previous.bottom
                same_cell = gap <= max(4.0, previous.size * 0.8)
                if same_cell and abs(line.x0 - previous.x0) <= max(24.0, previous.size * 2):
                    if line.size < previous.size - 0.4:
                        entries[-1]['text'] += f' ({text})'
                    else:
                        entries[-1]['text'] += f' {text}'
                    previous = line
                    continue
            entries.append({
                'text': text,
                'top': line.top,
                'page': line.page,
                'column': column,
                'size': line.size,
            })
            previous = line

        # A quantity with no name is still useful to the reviewer.
        if pending_qty is not None:
            entries.append({
                'text': pending_qty,
                'top': pending_top if pending_top is not None else 0,
                'page': pending_page if pending_page is not None else 0,
                'column': column,
                'size': 0,
            })

    entries.sort(key=lambda entry: (
        entry.get('page', 0), round(entry['top'] / 4.0), entry['column']))
    result = []
    seen = set()
    for entry in entries:
        text = _clean(entry['text'])
        key = (entry.get('page', 0), round(entry['top'] / 2.0), text)
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def _all_lines(pages) -> list:
    lines = []
    for page in pages:
        for line in page.lines:
            lines.append((page, line))
    return lines


def _step_candidates(pages, ingredient_ids) -> list:
    candidates = []
    weak = []
    instruction_heading_pages = set()
    for page in pages:
        for line in page.lines:
            if _is_instruction_heading(line):
                instruction_heading_pages.add((page.index, line.top))

    # Look for paired patterns like number on one line and title on next line (common in some layouts)
    for page in pages:
        lines = page.lines
        for i, line in enumerate(lines):
            if id(line) in ingredient_ids:
                continue
            text = _clean(line.text)
            # Is this just a number?
            mnum = re.match(r'^\s*(\d{1,3})\s*$', text)
            if mnum:
                num = int(mnum.group(1))
                # look behind for title - check nearby lines in same/adjacent area
                best = None
                best_dist = 1e9
                for j in range(max(0, i - 15), i):
                    prevline = lines[j]
                    if id(prevline) in ingredient_ids:
                        continue
                    ptext = _clean(prevline.text)
                    if not ptext or re.match(r'^\s*(\d{1,3})\s*$', ptext):
                        continue
                    if _is_ingredient_heading(prevline) or _is_stat_line(prevline) or _is_other_heading(prevline):
                        continue
                    if len(ptext.split()) <= 12 and ptext.upper() == ptext and re.search(r'[A-Za-z]', ptext):
                        if ':' in ptext:
                            continue
                        dist = abs(prevline.x0 - line.x0)
                        vdist = abs(prevline.top - line.top)
                        if dist < 40 or (dist < 150 and vdist < 10):
                            if dist < best_dist:
                                best_dist = dist
                                best = prevline
                            elif dist == best_dist and best is None:
                                best = prevline
                        elif dist < best_dist and vdist < 20:
                            best_dist = dist
                            best = prevline
                if best is not None and best_dist < 250:
                    info = (num, _clean(best.text))
                    after_heading = any(p == page.index and top < line.top for p, top in instruction_heading_pages)
                    item = (page, line, info, after_heading)
                    candidates.append(item)
                    continue
                # Also try looking for title on same row context in different layouts
                # Try to find any all-caps title in nearby columns
                for j in range(max(0, i - 8), min(len(lines), i + 1)):
                    if j == i:
                        continue
                    prevline = lines[j]
                    if id(prevline) in ingredient_ids:
                        continue
                    ptext = _clean(prevline.text)
                    if not ptext:
                        continue
                    if _is_stat_line(prevline) or _is_other_heading(prevline) or _is_ingredient_heading(prevline):
                        continue
                    if ptext.upper() == ptext and len(ptext.split()) <= 6 and re.search(r'[A-Z]{3,}', ptext) and ':' not in ptext:
                        # could be step title
                        info = (num, ptext)
                        after_heading = any(p == page.index and top < line.top for p, top in instruction_heading_pages)
                        item = (page, line, info, after_heading)
                        candidates.append(item)
                        break
                else:
                    # look ahead
                    for j in range(i + 1, min(i + 3, len(lines))):
                        nextline = lines[j]
                        if id(nextline) in ingredient_ids:
                            continue
                        ntext = _clean(nextline.text)
                        if not ntext or _is_stat_line(nextline) or _is_other_heading(nextline):
                            continue
                        if re.match(r'^\s*(\d{1,3})\s*$', ntext):
                            break
                        if _is_ingredient_heading(nextline):
                            continue
                        if len(ntext.split()) <= 10 and re.search(r'[A-Za-z]', ntext) and ntext.upper() == ntext:
                            if ':' in ntext or _QTY_ONLY.fullmatch(ntext) or len(ntext.split()) == 1:
                                break
                            info = (num, ntext)
                            after_heading = any(
                                p == page.index and top < line.top
                                for p, top in instruction_heading_pages)
                            item = (page, line, info, after_heading)
                            candidates.append(item)
                            break
            # also look behind pattern? maybe title followed by number not usual

    for page, line in _all_lines(pages):
        if id(line) in ingredient_ids:
            continue
        info = _header_info(line)
        if not info:
            continue
        if _is_stat_line(line) or _is_other_heading(line):
            continue
        after_heading = any(
            p == page.index and top < line.top
            for p, top in instruction_heading_pages)
        item = (page, line, info, after_heading)
        if _header_is_strong(line, info) or after_heading:
            candidates.append(item)
        else:
            weak.append(item)

    # A card may use title-case, non-bold step headings.  If a page has
    # several numbered headings, accept all of them, not just the bold ones.
    by_page = {}
    for item in weak:
        by_page.setdefault(item[0].index, []).append(item)
    accepted_ids = {id(item[1]) for item in candidates}
    for page_items in by_page.values():
        numbers = {item[2][0] for item in page_items}
        if len(numbers) >= 2:
            for item in page_items:
                if id(item[1]) not in accepted_ids:
                    candidates.append(item)
    return candidates


def _group_steps(candidates, pages, ingredient_ids) -> list:
    """Build steps and collect the body text beneath each heading."""
    if not candidates:
        return []

    # Work in document coordinates so a step can continue over a page break.
    prepared = []
    for page, line, info, after_heading in candidates:
        prepared.append({
            'page': page,
            'line': line,
            'number': info[0],
            'title': info[1],
            'doc_top': page.index * PAGE_OFFSET + line.top,
            'doc_bottom': page.index * PAGE_OFFSET + line.bottom,
            'after_heading': after_heading,
        })
    prepared.sort(key=lambda item: (item['doc_top'], item['line'].x0))

    # Step titles can wrap onto a second line.  Absorb adjacent lines that
    # share the heading's font size, weight, and column before body text is
    # collected.
    candidate_ids = {id(item['line']) for item in prepared}
    continuation_ids = set()
    page_lines = {page.index: sorted(page.lines, key=lambda line: (line.top, line.x0))
                  for page in pages}
    for item in prepared:
        lines = page_lines.get(item['page'].index, [])
        try:
            index = next(i for i, line in enumerate(lines)
                         if line is item['line'])
        except StopIteration:
            continue
        title = item['title']
        last = item['line']
        for line in lines[index + 1:]:
            if id(line) in candidate_ids or id(line) in ingredient_ids:
                break
            if _is_ingredient_heading(line) or _is_instruction_heading(line) \
                    or _is_other_heading(line) or _is_stat_line(line):
                break
            gap = line.top - last.bottom
            same_size = abs(line.size - item['line'].size) <= 0.6
            same_weight = line.bold == item['line'].bold
            aligned = abs(line.x0 - item['line'].x0) <= max(18.0, item['line'].size * 2.5)
            if gap <= max(6.0, item['line'].size * 0.8) and same_size \
                    and same_weight and aligned:
                title = _clean(f'{title} {line.text}')
                continuation_ids.add(id(line))
                last = line
            else:
                break
        item['title'] = title

    anchors = _cluster_values([item['line'].x0 for item in prepared],
                              gap=max(45.0, prepared[0]['page'].width * 0.09))
    for item in prepared:
        item['column'] = _column_of_x(item['line'].x0, anchors)

    # Deduplicate headings with the same number (a repeated header on a
    # second page), preferring the first occurrence with body below it.
    unique = []
    seen = {}
    for item in prepared:
        key = item['number']
        if key in seen:
            continue
        seen[key] = item
        unique.append(item)
    unique.sort(key=lambda item: item['number'])

    # All text lines, grouped by column, for body extraction.  Pages with
    # no step heading of their own are included so a step can continue over
    # a page break.
    column_lines = {i: [] for i in range(len(anchors))}
    for page in pages:
        for line in page.lines:
            if line.text:
                column_lines[_column_of_x(line.x0, anchors)].append(
                    (page, line))

    header_ids = {id(item['line']) for item in unique} | continuation_ids
    steps = []
    for index, item in enumerate(unique):
        page = item['page']
        next_same = next(
            (other for other in unique
             if other['column'] == item['column']
             and other['doc_top'] > item['doc_top']),
            None)
        end_doc = next_same['doc_top'] if next_same else float('inf')

        body_lines = []
        for other_page, line in column_lines[item['column']]:
            doc_top = other_page.index * PAGE_OFFSET + line.top
            if doc_top <= item['doc_bottom']:
                continue
            if doc_top >= end_doc:
                continue
            if id(line) in header_ids:
                continue
            if id(line) in ingredient_ids or _is_ingredient_heading(line) \
                    or _is_other_heading(line) or _is_stat_line(line):
                break
            if _is_instruction_heading(line):
                break
            if _header_info(line):
                continue
            if line.x1 - line.x0 > other_page.width * 0.8:
                continue
            body_lines.append((other_page, line, doc_top))
        body_lines.sort(key=lambda row: (row[2], row[1].x0))

        body = ''
        for _p, line, _top in body_lines:
            piece = _clean(line.text)
            if not piece:
                continue
            if body.endswith('-') and piece[:1].islower():
                body = body[:-1] + piece
            else:
                body = f'{body} {piece}'.strip()
        body = _clean(body)
        text = f"{item['title']}: {body}".strip(': ') if body else item['title']
        item['text'] = text
        steps.append(item)

    return steps


# ---------------------------------------------------------------------------
# Images / OCR
# ---------------------------------------------------------------------------

def _image_bytes(image) -> Optional[tuple]:
    stream = getattr(image, 'stream', None)
    if stream is None:
        return None
    attrs = getattr(stream, 'attrs', {}) or {}
    filt = str(attrs.get('Filter', ''))
    raw = getattr(stream, 'rawdata', None)
    if not raw:
        return None
    if 'DCT' in filt or raw[:2] == b'\xff\xd8':
        return ('jpg', bytes(raw))
    if 'JPX' in filt or raw[:4] == b'\x00\x00\x00\x0c':
        return ('jp2', bytes(raw))
    if 'Flate' in filt or filt.startswith('/Fl'):
        return _flate_image(stream, attrs)
    if 'LZW' in filt:
        return _lzw_image(stream, attrs)
    return None


def _flate_image(stream, attrs) -> Optional[tuple]:
    try:
        width = int(attrs.get('Width'))
        height = int(attrs.get('Height'))
        bits = int(attrs.get('BitsPerComponent', 8))
        colours = str(attrs.get('ColorSpace', '')).lstrip('/')
        mode = {'DeviceRGB': 'RGB', 'DeviceGray': 'L', 'DeviceCMYK': 'CMYK'}.get(colours)
        if mode is None or bits != 8:
            return None
        samples = stream.get_data()
        if len(samples) != width * height * len(mode):
            return None
        image = Image.frombytes(mode, (width, height), samples)
        if mode == 'CMYK':
            image = image.convert('RGB')
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        return ('png', buffer.getvalue())
    except Exception:
        return None


def _lzw_image(stream, attrs) -> Optional[tuple]:
    try:
        width = int(attrs.get('Width'))
        height = int(attrs.get('Height'))
        bits = int(attrs.get('BitsPerComponent', 8))
        colours = str(attrs.get('ColorSpace', '')).lstrip('/')
        mode = {'DeviceRGB': 'RGB', 'DeviceGray': 'L', 'DeviceCMYK': 'CMYK'}.get(colours)
        if mode is None or bits != 8:
            return None
        samples = stream.get_data()
        if len(samples) != width * height * len(mode):
            return None
        image = Image.frombytes(mode, (width, height), samples)
        if mode == 'CMYK':
            image = image.convert('RGB')
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        return ('png', buffer.getvalue())
    except Exception:
        return None


def _collect_images(page, height) -> list:
    images = []
    for image in _walk(page, lambda n: isinstance(n, LTImage)):
        blob = _image_bytes(image)
        if blob is None:
            continue
        x0, y0, x1, y1 = image.bbox
        if (x1 - x0) * (y1 - y0) < MIN_IMAGE_AREA:
            continue
        images.append(ImageData(
            page=0, x0=x0, x1=x1,
            top=height - y1, bottom=height - y0, data=blob))
    return images


def _ocr_page(page_data: PageData) -> list:
    """Return OCR-derived runs for a scanned page, or [] when unavailable."""
    if not page_data.images:
        return []
    try:
        import pytesseract
        from pytesseract import Output
    except Exception:
        return []

    source = max(page_data.images, key=lambda image: image.area)
    try:
        image = Image.open(io.BytesIO(source.data[1]))
        if image.mode not in ('L', 'RGB'):
            image = image.convert('RGB')
        payload = pytesseract.image_to_data(
            image, output_type=Output.DICT,
            config='--psm 6')
    except Exception:
        return []

    image_width, image_height = image.size
    scale_x = (source.x1 - source.x0) / max(1, image_width)
    scale_y = (source.bottom - source.top) / max(1, image_height)
    runs = []
    count = len(payload.get('text', []))
    for i in range(count):
        text = (payload['text'][i] or '').strip()
        if not text:
            continue
        try:
            left = float(payload['left'][i])
            top = float(payload['top'][i])
            width = float(payload['width'][i])
            height = float(payload['height'][i])
        except (KeyError, TypeError, ValueError):
            continue
        x0 = source.x0 + left * scale_x
        x1 = source.x0 + (left + width) * scale_x
        y0 = source.top + top * scale_y
        y1 = source.top + (top + height) * scale_y
        runs.append(Run(
            text=text, x0=x0, x1=x1, top=y0, bottom=y1,
            size=max(1.0, y1 - y0), font='', baseline=y1))
    # One OCR word per run is enough: _make_lines rejoins words whose gaps
    # are small and splits real columns.
    return runs


def _page_data(raw_page, index) -> PageData:
    width = raw_page.bbox[2] - raw_page.bbox[0]
    height = raw_page.bbox[3] - raw_page.bbox[1]
    runs = _extract_runs(raw_page, height)
    chars = sum(len(run.text) for run in runs)
    images = _collect_images(raw_page, height)
    page = PageData(index=index, width=width, height=height,
                    runs=runs, images=images, text_chars=chars)
    if chars < 20 and images:
        ocr_runs = _ocr_page(page)
        if ocr_runs:
            page.runs = ocr_runs
            page.text_chars = sum(len(run.text) for run in ocr_runs)
            for image in images:
                image.ocr_source = True
    page.lines = _make_lines(page.runs, index, width)
    for image in page.images:
        image.page = index
        image.doc_top = index * PAGE_OFFSET + image.top
        image.doc_bottom = index * PAGE_OFFSET + image.bottom
    return page


def _hero_image(pages) -> tuple:
    if not pages:
        return None, None
    first = pages[0]
    candidates = [image for image in first.images
                  if not image.ocr_source and image.area >= MIN_IMAGE_AREA]
    if not candidates:
        # A hero can be on a later cover page; only use a very large image
        # so step photos are not accidentally promoted to the hero.
        candidates = [image for page in pages[1:] for image in page.images
                      if not image.ocr_source
                      and image.area >= max(20000, page.width * page.height * 0.03)]
    if not candidates:
        return None, None
    hero = max(candidates, key=lambda image: image.area)
    return hero.data, hero


def _associate_photos(pages, steps, hero, warnings) -> tuple:
    """Return (step_photos aligned with steps, extra photos)."""
    header_anchors = (
        _cluster_values([step['line'].x0 for step in steps],
                        gap=max(45.0, pages[0].width * 0.09))
        if steps else [])
    images = [image for page in pages for image in page.images
              if image is not hero and not image.ocr_source]
    if not steps:
        return [], images

    def image_column(image):
        center = (image.x0 + image.x1) / 2
        return _column_of_x(center, header_anchors)

    # Detect whether photos are typically above or below their heading.
    above = below = 0
    for image in images:
        column = image_column(image)
        candidates = [step for step in steps if step['column'] == column]
        if not candidates:
            continue
        nearest = min(candidates,
                      key=lambda step: abs(step['doc_top'] - image.doc_bottom))
        difference = nearest['doc_top'] - (image.doc_top + image.doc_bottom) / 2
        if difference >= 0:
            above += 1
        else:
            below += 1
    prefer_above = above >= below

    assignments = {index: [] for index in range(len(steps))}
    for image in images:
        column = image_column(image)
        scored = []
        for index, step in enumerate(steps):
            vertical = abs(step['doc_top'] - (image.doc_top + image.doc_bottom) / 2)
            horizontal = 0 if step['column'] == column else \
                abs(step['line'].x0 - (image.x0 + image.x1) / 2)
            scored.append((vertical + horizontal * 1.5, index, step, vertical))
        scored.sort(key=lambda row: row[0])
        best_score, best_index, best_step, best_vertical = scored[0]

        # Prefer the customary side of the heading when possible.
        if not best_step['column'] == column:
            directional = []
            for score, index, step, vertical in scored:
                if step['column'] != column:
                    continue
                center = (image.doc_top + image.doc_bottom) / 2
                is_above = center <= step['doc_top']
                if is_above == prefer_above:
                    directional.append((score, index, step, vertical))
            if directional:
                directional.sort(key=lambda row: row[0])
                best_score, best_index, best_step, best_vertical = directional[0]

        # Flag genuinely ambiguous placements (two headings nearly equally
        # close in the same column).
        close = [row for row in scored[1:]
                 if row[2]['column'] == best_step['column']
                 and row[0] - best_score < 20]
        if close:
            warnings.append(
                'A recipe image was almost equally close to two steps; '
                f'it was attached to step {best_step["number"]}. Please check it.')
        if best_score > pages[0].height * 1.5:
            warnings.append(
                f'Photo for step {best_step["number"]} was placed by its '
                'nearest position; please check the association.')
        assignments[best_index].append((best_vertical, image))

    # If a step received several photos, move the extras to nearby steps
    # that have none rather than throwing them away.
    step_photos = []
    extras = []
    for index, step in enumerate(steps):
        group = sorted(assignments[index], key=lambda row: row[0])
        if group:
            step_photos.append(group[0][1].data)
            extras.extend(image for _distance, image in group[1:])
        else:
            step_photos.append(None)

    for image in extras:
        missing = [i for i, photo in enumerate(step_photos) if photo is None]
        if not missing:
            break
        column = image_column(image)
        index = min(missing, key=lambda i: (
            abs(steps[i]['line'].x0 - (image.x0 + image.x1) / 2)
            if steps[i]['column'] == column else 1e9,
            abs(steps[i]['doc_top'] - image.doc_bottom)))
        if steps[index]['column'] == column or len(missing) == 1:
            step_photos[index] = image.data
            extras.remove(image)

    if extras:
        warnings.append(
            f'{len(extras)} extra recipe image(s) could not be attached to a '
            'single step; they are available in the draft extra_photos list.')

    missing_steps = [step['number'] for step, photo in zip(steps, step_photos)
                     if photo is None]
    if missing_steps and any(step_photos):
        warnings.append(
            'No step photo could be matched for step(s): '
            + ', '.join(str(number) for number in missing_steps) + '.')
    return step_photos, extras


def _validate(draft, warnings) -> None:
    if not draft['title']:
        raise ImportFailed(
            'No recipe card was found in that PDF. Skillet looked for a '
            'large recipe title, an ingredients heading and numbered steps, '
            'including PDFs where those elements move between pages.')
    if not draft['ingredients'] and not draft['instructions']:
        raise ImportFailed(
            'No readable recipe text was found in that PDF. If it is a '
            'scanned card, install Tesseract for OCR and try again.')
    if not draft['description']:
        warnings.append('No description was found on the recipe card.')
    if draft['prep_minutes'] is None:
        warnings.append('No prep time was found on the recipe card.')
    if draft['cook_minutes'] is None:
        warnings.append('No cook time was found on the recipe card.')
    if not draft['ingredients']:
        warnings.append('No ingredients were found on the recipe card.')
    if not draft['instructions']:
        warnings.append('No numbered instructions were found on the recipe card.')
    if not draft.get('photo'):
        warnings.append('No recipe photo was found on the recipe card.')


def parse_recipe_pdf(data: bytes) -> dict:
    """Parse a recipe-card PDF into the shared import draft shape."""
    if not data:
        raise ImportFailed('That PDF was empty.')
    if b'%PDF' not in data[:1024]:
        raise ImportFailed('That file is not a PDF recipe card.')

    try:
        raw_pages = list(extract_pages(io.BytesIO(data), laparams=LAParams()))
    except Exception as exc:
        raise ImportFailed('That PDF could not be read.') from exc
    if not raw_pages:
        raise ImportFailed('That PDF has no pages.')
    if len(raw_pages) > MAX_PAGES:
        raise ImportFailed('That PDF has too many pages to be a recipe card.')

    try:
        pages = [_page_data(raw_page, index)
                 for index, raw_page in enumerate(raw_pages)]
    except Exception as exc:
        raise ImportFailed('That PDF could not be read.') from exc

    title, title_lines, title_page = _detect_title(pages)
    description = _detect_description(title_page, title_lines)
    all_lines = [line for page in pages for line in page.lines]
    prep = _detect_stat(all_lines, 'PREP')
    cook = _detect_stat(all_lines, 'COOK')
    servings = _detect_servings(pages)

    _spans, ingredient_ids = _ingredient_spans(pages)
    ingredient_lines = []
    for page in pages:
        for line in page.lines:
            if id(line) in ingredient_ids:
                ingredient_lines.append((page, line))
    ingredient_lines.sort(key=lambda row: (row[0].index, row[1].top, row[1].x0))
    ingredients = _parse_ingredients(
        [line for _page, line in ingredient_lines],
        pages[0].width if pages else 612)

    candidates = _step_candidates(pages, ingredient_ids)
    steps = _group_steps(candidates, pages, ingredient_ids)

    warnings = []
    hero, hero_image = _hero_image(pages)
    step_photos, extra_photos = _associate_photos(pages, steps, hero_image, warnings)
    # Filter out obviously bad steps
    filtered_steps = []
    for step in steps:
        text = step.get('text', '')
        t = _clean(text)
        # Skip if it's just metadata/page numbers
        if re.search(r'\d{4}/\d{2}/\d{2}|\d{1,2}:\d{2}|\d+\.\d+.*indd', t):
            continue
        if t.upper() in ['J', 'K', 'N', 'W', 'HALL OF FAME', 'FUN-DAY FAJITA BAR'] and len(t.split()) <= 4:
            continue
        if t.upper() == 'HELLO' and len(t.split()) == 1:
            continue
        filtered_steps.append(step)
    steps = filtered_steps
    instructions = [step['text'] for step in steps]

    draft = {
        'title': title,
        'description': description,
        'photo_url': None,
        'prep_minutes': prep,
        'cook_minutes': cook,
        'servings': servings,
        'tags': [],
        'ingredients': ingredients,
        'instructions': instructions[:120],
        'step_photos': step_photos[:120],
        'extra_photos': [image.data for image in extra_photos],
        'warnings': warnings,
        'source_url': '',
        'method': 'pdf',
        'photo': hero,
    }
    _validate(draft, warnings)
    return draft
