"""Extract a recipe from a HelloFresh-style two-page recipe-card PDF.

The card layout is fixed: the front carries the title, the subtitle and
the 2-person/4-person ingredient grid; the back carries numbered steps
grouped in columns, each step usually with its own photo.

The parser works from glyph geometry (position, size, font weight)
rather than plain text order, because a naive text dump interleaves the
columns. It returns the same draft shape the URL importer produces so
the existing review-and-save flow can be reused, plus a ``photo`` entry
holding the hero image bytes and a list of step-photo bytes.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Optional

from pdfminer.high_level import extract_pages
from pdfminer.layout import LAParams, LTChar, LTImage, LTTextBox
from PIL import Image

from app.lib.importer import ImportFailed

MAX_PAGES = 8
MIN_PHOTO_AREA = 20000
GRID_STOP_GAP = 90
WRAP_GAP = 12
COLUMN_TOLERANCE = 30

_STEP_HEADER = re.compile(r'^(\d+)\s*([A-Z][^a-z]*)$')

FRACTION_CHARS = {
    '\u00bc': '1/4', '\u00bd': '1/2', '\u00be': '3/4',
    '\u2153': '1/3', '\u2154': '2/3',
    '\u215b': '1/8', '\u215c': '3/8', '\u215d': '5/8', '\u215e': '7/8',
    '\u2044': '/',
}


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
    """All the runs printed on one baseline."""
    runs: list

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
        return any('bold' in r.font.lower() for r in self.runs)


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


def _lines(runs) -> list:
    buckets = {}
    for run in runs:
        buckets.setdefault(run.baseline, []).append(run)
    lines = []
    for group in buckets.values():
        group.sort(key=lambda r: r.x0)
        lines.append(Line(group))
    lines.sort(key=lambda line: line.top)
    return lines


def _merge_intervals(intervals, gap) -> list:
    clusters = []
    for x0, x1 in sorted(intervals):
        if clusters and x0 - clusters[-1][1] <= gap:
            clusters[-1][1] = max(clusters[-1][1], x1)
        else:
            clusters.append([x0, x1])
    return clusters


def _x_clusters(runs, gap) -> list:
    return _merge_intervals(((r.x0, r.x1) for r in runs), gap)


def _nearest_column(x0, columns, tolerance):
    best = None
    best_distance = None
    for i, (left, _right) in enumerate(columns):
        distance = abs(x0 - left)
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best = i
    if best_distance is not None and best_distance <= tolerance:
        return best
    return None


def _column_of(run, columns) -> int:
    best = 0
    best_score = None
    for i, (left, right) in enumerate(columns):
        overlap = min(run.x1, right) - max(run.x0, left)
        score = overlap if overlap > 0 else -min(abs(run.x0 - right), abs(left - run.x1))
        if best_score is None or score > best_score:
            best_score = score
            best = i
    return best


def _ascii_fractions(text: str) -> str:
    for char, replacement in FRACTION_CHARS.items():
        text = text.replace(char, replacement)
    return text


# ---------------------------------------------------------------------------
# Front page: title, subtitle, ingredient grid
# ---------------------------------------------------------------------------

def _parse_front(page) -> dict:
    width = page.bbox[2] - page.bbox[0]
    height = page.bbox[3] - page.bbox[1]
    runs = _extract_runs(page, height)
    lines = _lines(runs)

    title = ''
    title_line = None
    if lines:
        title_line = max(lines, key=lambda line: line.size)
        if title_line.size >= 14:
            title = title_line.text[:200]

    description = None
    if title_line is not None:
        below = [line for line in lines
                 if line.top > title_line.bottom and 10 <= line.size <= 16]
        if below:
            candidate = min(below, key=lambda line: line.top)
            if candidate.top - title_line.bottom <= 25:
                description = candidate.text[:1000] or None

    heading = next((line for line in lines
                    if re.search(r'INGREDIENTS', line.text, re.I)), None)
    ingredients = _parse_ingredients(runs, width, heading) if heading else []

    servings = 4
    if any(re.search(r'\b2\s*person', line.text, re.I) for line in lines):
        servings = 2

    return {
        'title': title,
        'description': description,
        'ingredients': ingredients,
        'servings': servings,
        'prep_minutes': _stat_minutes(runs, 'PREP'),
        'cook_minutes': _stat_minutes(runs, 'COOK'),
        'photo': _hero_image(page, height),
    }


def _stat_minutes(runs, label) -> Optional[int]:
    label_run = next(
        (r for r in runs if re.match(r'^%s\b' % label, r.text.upper())), None
    )
    if label_run is None:
        return None
    inline = re.search(r'(\d+)\s*MIN', label_run.text, re.I)
    if inline:
        return int(inline.group(1))
    nearby = [r for r in runs
              if abs(r.top - label_run.top) <= 8 and r.x0 > label_run.x0
              and re.fullmatch(r'\d+', r.text)]
    if nearby:
        return int(min(nearby, key=lambda r: r.x0).text)
    return None


def _parse_ingredients(runs, width, heading) -> list:
    grid = [r for r in runs
            if 5.5 <= r.size <= 8.0
            and r.top > heading.bottom
            and r.x0 < width * 0.6
            and 'PERSON' not in r.text.upper()]
    if not grid:
        return []

    selected = []
    prev_top = None
    for line in _lines(grid):
        if prev_top is not None and line.top - prev_top > GRID_STOP_GAP:
            break
        selected.append(line)
        prev_top = line.top

    columns = _x_clusters([r for line in selected for r in line.runs], gap=16)
    cells = [[] for _ in columns]
    for line in selected:
        groups = {}
        for run in line.runs:
            groups.setdefault(_column_of(run, columns), []).append(run)
        for ci, group in groups.items():
            group.sort(key=lambda r: r.x0)
            cells[ci].append(Line(group))

    ingredients = []
    for ci, column in enumerate(cells):
        column.sort(key=lambda line: line.top)
        for entry in _column_cells(column):
            entry['column'] = ci
            ingredients.append(entry)
    ingredients.sort(key=lambda e: (round(e['top']), e['column']))
    return [_ascii_fractions(e['text']) for e in ingredients]


def _column_cells(column) -> list:
    cells = []
    i = 0
    while i < len(column):
        line = column[i]
        if not line.bold:
            i += 1
            continue
        qty = sorted(line.runs, key=lambda r: r.x0)[0].text if line.runs else ''
        names = []
        note = None
        prev_top = line.top
        j = i + 1
        while j < len(column) and column[j].top - prev_top <= WRAP_GAP \
                and column[j].top - line.top < 40:
            nxt = column[j]
            if nxt.size < 6.4:
                if note is None:
                    note = nxt.text
            elif not nxt.bold:
                names.append(nxt.text)
            else:
                break
            prev_top = nxt.top
            j += 1
        name = ' '.join(names).strip()
        if name:
            text = f'{qty} {name}'.strip() if qty else name
            if note:
                text += f' ({note})'
            cells.append({'top': line.top, 'text': text})
        i = j if j > i else i + 1
    return cells


# ---------------------------------------------------------------------------
# Back page: numbered steps and their photos
# ---------------------------------------------------------------------------

def _parse_back(page) -> list:
    """Steps live in columns on the back page. pdfminer's layout analysis
    already stitches the inline ingredient callouts into readable
    paragraphs, so we work from its text boxes and just group them by the
    numbered heading they sit under."""
    height = page.bbox[3] - page.bbox[1]

    def top(box):
        return height - box.bbox[3]

    boxes = [child for child in page if isinstance(child, LTTextBox)]
    headers = [b for b in boxes if _header_match(b)]
    if not headers:
        return []

    columns = _merge_intervals(((b.bbox[0], b.bbox[2]) for b in headers), gap=60)

    body = {}
    for box in boxes:
        column = _nearest_column(box.bbox[0], columns, COLUMN_TOLERANCE)
        if column is not None:
            body.setdefault(column, []).append(box)

    steps = []
    for ci, group in body.items():
        group.sort(key=lambda b: (top(b), b.bbox[0]))
        header_idxs = [i for i, b in enumerate(group) if _header_match(b)]
        for k, hi in enumerate(header_idxs):
            header = group[hi]
            match = _header_match(header)
            end = top(group[header_idxs[k + 1]]) if k + 1 < len(header_idxs) else None
            region = [b for b in group[hi + 1:] if end is None or top(b) < end]
            body_text = _clean(' '.join(_box_text(b) for b in region))
            steps.append({
                'num': int(match.group(1)),
                'title': match.group(2).strip(),
                'text': f"{match.group(2).strip()}: {body_text}".strip(': '),
                'column': ci,
                'header_top': top(header),
            })

    _attach_photos(page, height, columns, steps)
    return steps


def _clean(text) -> str:
    text = re.sub(r'\s*•\s*', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def _header_match(box):
    return _STEP_HEADER.match(_box_text(box))


def _box_text(box) -> str:
    return re.sub(r'\s+', ' ', box.get_text()).strip()


def _attach_photos(page, height, columns, steps):
    centers = [(left + right) / 2 for left, right in columns]
    photos = []
    for image in _walk(page, lambda n: isinstance(n, LTImage)):
        blob = _image_bytes(image)
        if blob is None:
            continue
        x0, y0, x1, y1 = image.bbox
        cx = (x0 + x1) / 2
        column = min(range(len(centers)), key=lambda i: abs(cx - centers[i]))
        photos.append({'bytes': blob, 'top': height - y1,
                       'bottom': height - y0, 'column': column})

    for step in steps:
        candidates = [p for p in photos
                      if p['column'] == step['column']
                      and p['bottom'] <= step['header_top'] + 2]
        if candidates:
            best = max(candidates, key=lambda p: p['bottom'])
            step['_photo'] = best['bytes']


def _hero_image(page, height):
    best = None
    best_area = MIN_PHOTO_AREA
    for image in _walk(page, lambda n: isinstance(n, LTImage)):
        x0, y0, x1, y1 = image.bbox
        area = (x1 - x0) * (y1 - y0)
        if area < best_area:
            continue
        blob = _image_bytes(image)
        if blob is None:
            continue
        best = blob
        best_area = area
    return best


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
    if 'Flate' in filt or filt.startswith('/Fl'):
        return _flate_image(stream, attrs)
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
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        return ('png', buffer.getvalue())
    except Exception:
        return None


def parse_recipe_pdf(data: bytes) -> dict:
    """Parse a recipe-card PDF into the shared import draft shape."""
    if not data:
        raise ImportFailed('That PDF was empty.')
    if b'%PDF' not in data[:1024]:
        raise ImportFailed('That file is not a PDF recipe card.')

    try:
        pages = list(extract_pages(io.BytesIO(data), laparams=LAParams()))
    except Exception as exc:
        raise ImportFailed('That PDF could not be read.') from exc
    if not pages:
        raise ImportFailed('That PDF has no pages.')
    if len(pages) > MAX_PAGES:
        raise ImportFailed('That PDF has too many pages to be a recipe card.')

    try:
        front = _parse_front(pages[0])
    except Exception as exc:
        raise ImportFailed('That PDF could not be read.') from exc

    if not front['title']:
        raise ImportFailed(
            'No recipe card was found in that PDF. Skillet understands the '
            'two-page card layout: a big title, a 2/4 person ingredient grid '
            'and numbered steps.'
        )

    instructions = []
    step_photos = []
    if len(pages) > 1:
        try:
            steps = _parse_back(pages[1])
        except Exception:
            steps = []
        for step in sorted(steps, key=lambda s: s['num']):
            instructions.append(step['text'])
            step_photos.append(step.get('_photo'))

    return {
        'title': front['title'],
        'description': front['description'],
        'photo_url': None,
        'prep_minutes': front['prep_minutes'],
        'cook_minutes': front['cook_minutes'],
        'servings': front['servings'],
        'tags': [],
        'ingredients': front['ingredients'],
        'instructions': instructions[:60],
        'step_photos': step_photos[:60],
        'source_url': '',
        'method': 'pdf',
        'photo': front['photo'],
    }
