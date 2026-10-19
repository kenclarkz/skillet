"""Build small synthetic recipe-card PDFs for the PDF importer tests.

No binary fixtures are committed; the cards are generated here with the
standard PDF Type1 fonts so pdfminer can read them without embedding.
"""
from __future__ import annotations

import io


def jpeg_bytes() -> bytes:
    from PIL import Image
    buffer = io.BytesIO()
    Image.new('RGB', (16, 16), (200, 40, 40)).save(buffer, format='JPEG')
    return buffer.getvalue()


class _Pdf:
    def __init__(self, width=612, height=792):
        self.width = width
        self.height = height
        self.objects = []

    def add(self, body: bytes) -> int:
        self.objects.append(body)
        return len(self.objects)

    def stream(self, data: bytes, extra: str = '') -> int:
        body = (f'<< {extra} /Length {len(data)} >>\nstream\n'.encode()
                + data + b'\nendstream')
        return self.add(body)

    def page(self, parent: int, content: int, resources: str) -> int:
        return self.add(
            ('<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] '
             '/Contents %d 0 R /Resources %s >>'
             % (parent, self.width, self.height, content, resources)).encode()
        )

    def build(self, catalog: int) -> bytes:
        out = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
        offsets = [0] * (len(self.objects) + 1)
        for number, body in enumerate(self.objects, start=1):
            offsets[number] = len(out)
            out += b'%d 0 obj\n' % number + body + b'\nendobj\n'
        xref = len(out)
        out += b'xref\n0 %d\n' % (len(self.objects) + 1)
        out += b'0000000000 65535 f \n'
        for number in range(1, len(self.objects) + 1):
            out += b'%010d 00000 n \n' % offsets[number]
        out += (b'trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n'
                % (len(self.objects) + 1, catalog, xref))
        return bytes(out)


def _text(font, size, x, y, string):
    escaped = string.replace('\\', r'\\').replace('(', r'\(').replace(')', r'\)')
    return f'BT /{font} {size} Tf {x} {y} Td ({escaped}) Tj ET\n'.encode()


def _image(name, width, height, x, y):
    return f'q {width} 0 0 {height} {x} {y} cm /{name} Do Q\n'.encode()


INGREDIENT_CELLS = [
    [('1', '2', 'Apple'), ('1/2', '1', 'Banana'), ('2 cups', '4 cups', 'Rice')],
    [('1', '2', 'Onion'), ('1', '2', 'Lime'), ('1/4 oz', '1/2 oz', 'Cilantro')],
    [('10 oz', '20 oz', 'Chicken'), ('2 TBSP', '4 TBSP', 'Crema'), ('1', '2', 'Paste')],
]

STEP_TITLES = ['1 COOK RICE', '2 PREP', '3 MAKE SALSA', '4 COOK VEGGIES',
               '5 COOK CHICKEN', '6 FINISH']


def front_content() -> bytes:
    content = b''
    content += _text('F2', 18, 60, 740, 'TEST CHICKEN BOWLS')
    content += _text('F1', 12, 60, 715, 'with Test Toppings')
    content += _text('F2', 11, 60, 690, 'INGREDIENTS')
    content += _text('F2', 6, 60, 672, '2 PERSON | 4 PERSON')
    columns = [60, 160, 260]
    for row, cells in enumerate(INGREDIENT_CELLS):
        qty_y = 650 - row * 30
        name_y = qty_y - 8
        for col, (two, four, name) in enumerate(cells):
            x = columns[col]
            content += _text('F2', 7, x, qty_y, two)
            content += _text('F2', 7, x + 30, qty_y, four)
            content += _text('F1', 7, x, name_y, name)
    content += _text('F2', 11, 60, 560, 'PREP: 10 MIN')
    content += _text('F2', 11, 200, 560, 'COOK: 25 MIN')
    content += _image('ImHero', 250, 200, 320, 330)
    return content


def back_content() -> bytes:
    content = b''
    columns = [60, 250, 440]
    for row in range(2):
        header_y = 700 - row * 300
        for col in range(3):
            title = STEP_TITLES[row * 3 + col]
            x = columns[col]
            content += _text('F2', 10, x, header_y, title)
            content += _text('F1', 9, x, header_y - 32,
                             'Step %d body text.' % (row * 3 + col + 1))
            content += _image('ImStep', 100, 60, x, header_y + 20)
    return content


def build_recipe_pdf() -> bytes:
    pdf = _Pdf()
    catalog = pdf.add(b'placeholder')
    pages = pdf.add(b'placeholder')
    content1 = pdf.stream(front_content())
    content2 = pdf.stream(back_content())
    font1 = pdf.add(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
    font2 = pdf.add(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>')

    image = (b'/Type /XObject /Subtype /Image /Width 16 /Height 16 '
             b'/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode')
    hero = pdf.stream(jpeg_bytes(), image.decode())
    step = pdf.stream(jpeg_bytes(), image.decode())

    res1 = ('<< /Font << /F1 %d 0 R /F2 %d 0 R >> /XObject << /ImHero %d 0 R >> >>'
            % (font1, font2, hero))
    res2 = ('<< /Font << /F1 %d 0 R /F2 %d 0 R >> /XObject << /ImStep %d 0 R >> >>'
            % (font1, font2, step))

    page1 = pdf.page(pages, content1, res1)
    page2 = pdf.page(pages, content2, res2)
    pdf.objects[catalog - 1] = ('<< /Type /Catalog /Pages %d 0 R >>' % pages).encode()
    pdf.objects[pages - 1] = (
        '<< /Type /Pages /Kids [%d 0 R %d 0 R] /Count 2 >>' % (page1, page2)
    ).encode()
    return pdf.build(catalog)


def build_blank_pdf() -> bytes:
    """A valid two-page PDF with no recipe-card content."""
    pdf = _Pdf()
    catalog = pdf.add(b'placeholder')
    pages = pdf.add(b'placeholder')
    content = pdf.stream(_text('F1', 10, 72, 720, 'Just a note.'))
    font1 = pdf.add(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
    res = '<< /Font << /F1 %d 0 R >> >>' % font1
    page1 = pdf.page(pages, content, res)
    page2 = pdf.page(pages, content, res)
    pdf.objects[catalog - 1] = ('<< /Type /Catalog /Pages %d 0 R >>' % pages).encode()
    pdf.objects[pages - 1] = (
        '<< /Type /Pages /Kids [%d 0 R %d 0 R] /Count 2 >>' % (page1, page2)
    ).encode()
    return pdf.build(catalog)


def _wrap(text, width):
    words = text.split()
    lines = []
    current = ''
    for word in words:
        candidate = (current + ' ' + word).strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or ['']


class _CardBuilder:
    """Assemble a variable recipe-card PDF with the same visual template."""

    def __init__(self):
        self.pages = []
        self.new_page()

    def new_page(self):
        self.pages.append({'content': bytearray(), 'images': set()})

    def text(self, font, size, x, y, string):
        self.pages[-1]['content'] += _text(font, size, x, y, string)

    def image(self, width, height, x, y):
        self.pages[-1]['content'] += _image('ImStep', width, height, x, y)
        self.pages[-1]['images'].add('ImStep')

    def hero(self, width, height, x, y):
        self.pages[-1]['content'] += _image('ImHero', width, height, x, y)
        self.pages[-1]['images'].add('ImHero')

    def build(self):
        pdf = _Pdf()
        catalog = pdf.add(b'placeholder')
        pages = pdf.add(b'placeholder')
        font1 = pdf.add(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
        font2 = pdf.add(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>')
        image = (b'/Type /XObject /Subtype /Image /Width 16 /Height 16 '
                 b'/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode')
        hero = pdf.stream(jpeg_bytes(), image.decode())
        step = pdf.stream(jpeg_bytes(), image.decode())
        kids = []
        for page in self.pages:
            content = pdf.stream(bytes(page['content']))
            xobjects = ''
            if 'ImHero' in page['images']:
                xobjects += ' /ImHero %d 0 R' % hero
            if 'ImStep' in page['images']:
                xobjects += ' /ImStep %d 0 R' % step
            resources = ('<< /Font << /F1 %d 0 R /F2 %d 0 R >>'
                         ' /XObject << %s >> >>' % (font1, font2, xobjects.strip()))
            kids.append(pdf.page(pages, content, resources))
        pdf.objects[catalog - 1] = ('<< /Type /Catalog /Pages %d 0 R >>' % pages).encode()
        pdf.objects[pages - 1] = (
            '<< /Type /Pages /Kids [%s] /Count %d >>'
            % (' '.join('%d 0 R' % kid for kid in kids), len(kids))
        ).encode()
        return pdf.build(catalog)


def build_custom_recipe_pdf(*, title, description='', prep=None, cook=None,
                            servings_label='2 PERSON | 4 PERSON',
                            ingredients=(), steps=(), ingredient_breaks=(),
                            step_breaks=(), step_columns=3,
                            image_mode='above', step_images=None,
                            hero=True):
    """Build a card with the same headings but variable amounts of content.

    ``ingredients`` is a list of ``(two_person_qty, four_person_qty, name)``
    tuples and ``steps`` is a list of ``(title, body)`` tuples.  Page breaks
    are given as the index of the item that should start a new page.
    """
    builder = _CardBuilder()
    y = 740
    title_lines = _wrap(title, 26)
    for line in title_lines:
        builder.text('F2', 18, 60, y, line)
        y -= 23
    for line in _wrap(description, 44)[:5]:
        builder.text('F1', 11, 60, y, line)
        y -= 15
    y -= 14
    builder.text('F2', 11, 60, y, 'INGREDIENTS')
    y -= 18
    builder.text('F2', 6, 60, y, servings_label)
    y -= 24

    columns = [60, 160, 260]
    column = 0
    for index, (two, four, name) in enumerate(ingredients):
        if index in ingredient_breaks:
            builder.new_page()
            y = 720
            builder.text('F2', 11, 60, y, 'INGREDIENTS')
            y -= 30
            column = 0
        x = columns[column % 3]
        builder.text('F2', 7, x, y, two)
        builder.text('F2', 7, x + 30, y, four)
        name_lines = _wrap(name, 18)
        for offset, line in enumerate(name_lines):
            builder.text('F1', 7, x, y - 9 - offset * 8, line)
        if hero and index == 0:
            builder.hero(230, 180, 350, max(320, y - 160))
        if column % 3 == 2:
            y -= 32 + max(0, len(name_lines) - 1) * 8
        column += 1

    if hero and not ingredients:
        builder.hero(230, 180, 350, 500)

    y -= 18 if column % 3 == 0 else 32
    if prep is not None:
        builder.text('F2', 11, 60, y, 'PREP: %d MIN' % prep)
    if cook is not None:
        builder.text('F2', 11, 200, y, 'COOK: %d MIN' % cook)

    builder.new_page()
    y = 720
    columns_x = {1: [60], 2: [60, 320], 3: [60, 250, 440]}[step_columns]
    image_side = 0
    index = 0
    while index < len(steps):
        if index in step_breaks and index > 0:
            builder.new_page()
            y = 720
        row = []
        for col in range(step_columns):
            if index >= len(steps):
                break
            row.append((index, steps[index]))
            index += 1
            if index in step_breaks:
                break
        body_lines = [_wrap(body, 30) for _i, (_t, body) in row]
        row_height = max(150, max(len(lines) for lines in body_lines) * 12 + 90)
        if y - row_height < 55:
            builder.new_page()
            y = 720
        for col, (step_index, (step_title, body)) in enumerate(row):
            x = columns_x[col]
            header_y = y
            show_image = step_images is None or step_index in step_images
            mode = image_mode
            if mode == 'mixed':
                mode = 'above' if image_side % 2 == 0 else 'below'
                image_side += 1
            if show_image and mode == 'above':
                builder.image(85, 50, x, header_y + 18)
            builder.text('F2', 10, x, header_y, '%d %s' % (step_index + 1, step_title))
            body_y = header_y - 28
            if show_image and mode == 'below':
                builder.image(85, 40, x, header_y - 52)
                body_y = header_y - 68
            for line in _wrap(body, 30):
                builder.text('F1', 9, x, body_y, line)
                body_y -= 12
        y -= row_height
    return builder.build()


VARIANTS = [
    {
        'title': 'GARLIC BUTTER SHRIMP',
        'description': 'Quick weeknight shrimp with lemon.',
        'prep': 10,
        'cook': 15,
        'ingredients': [
            ('12 oz', '24 oz', 'Shrimp'), ('2', '4', 'Garlic Cloves'),
            ('2 TBSP', '4 TBSP', 'Butter'), ('1', '2', 'Lemon'),
            ('1/4 tsp', '1/2 tsp', 'Red Pepper Flakes'),
        ],
        'steps': [
            ('PREP', 'Peel the shrimp and mince the garlic.'),
            ('COOK SHRIMP', 'Sear the shrimp in butter until pink.'),
            ('FINISH', 'Add lemon juice and serve hot.'),
        ],
        'step_columns': 3,
        'image_mode': 'above',
    },
    {
        'title': 'SLOW ROASTED TOMATO AND BASIL SOUP WITH GRILLED CHEESE CROUTONS',
        'description': ('A long, cozy description that wraps over several lines '
                        'because the source card has plenty to say about the '
                        'tomatoes, the basil, and the toasted croutons.'),
        'prep': 20,
        'cook': 55,
        'ingredients': [
            ('2 lbs', '4 lbs', 'Slow Roasted Roma Tomatoes'), ('1', '2', 'Yellow Onion'),
            ('4 cloves', '8 cloves', 'Garlic'), ('2 cups', '4 cups', 'Vegetable Stock'),
            ('1 bunch', '2 bunches', 'Fresh Basil'), ('4 slices', '8 slices', 'Sourdough'),
            ('2 TBSP', '4 TBSP', 'Olive Oil'), ('1 tsp', '2 tsp', 'Salt'),
        ],
        'steps': [
            ('ROAST TOMATOES', 'Toss the tomatoes, onion, and garlic with olive oil. '
             'Roast until the edges are deeply caramelized and the kitchen smells amazing.'),
            ('SIMMER SOUP', 'Add the stock and simmer gently, then blend until smooth.'),
            ('TOAST BREAD', 'Brush the sourdough with olive oil and toast until crisp.'),
            ('SERVE', 'Ladle the soup into bowls and top with basil and croutons.'),
        ],
        'step_breaks': (2,),
        'step_columns': 2,
        'image_mode': 'above',
    },
    {
        'title': 'RAINBOW VEGGIE TACOS',
        'description': 'Colorful tacos with a smoky crema.',
        'prep': 25,
        'cook': 20,
        'ingredients': [
            ('1', '2', 'Red Bell Pepper'), ('1', '2', 'Yellow Squash'),
            ('1', '2', 'Red Onion'), ('2', '4', 'Corn Tortillas'),
            ('1 can', '2 cans', 'Black Beans'), ('1/2 cup', '1 cup', 'Sour Cream'),
            ('1', '2', 'Lime'), ('1 tsp', '2 tsp', 'Smoked Paprika'),
            ('1/4 cup', '1/2 cup', 'Cotija Cheese'), ('1', '2', 'Avocado'),
            ('2 TBSP', '4 TBSP', 'Cilantro'), ('1', '2', 'Jalapeno'),
        ],
        'steps': [
            ('PREP VEGGIES', 'Slice the peppers, squash, onion, and jalapeno into even strips.'),
            ('MAKE CREMA', 'Stir the sour cream with lime juice and smoked paprika.'),
            ('CHAR VEGGIES', 'Cook the vegetables in a hot skillet until lightly charred. '
             'Work in batches so the pan stays hot and the vegetables brown instead of steam.'),
            ('WARM TORTILLAS', 'Warm the tortillas in the same skillet.'),
            ('BUILD TACOS', 'Fill each tortilla with beans, vegetables, and crema.'),
            ('GARNISH', 'Top with avocado, cotija, and cilantro.'),
            ('CHECK SEASONING', 'Taste and add salt or lime as needed.'),
            ('SERVE', 'Serve immediately while everything is still warm.'),
        ],
        'ingredient_breaks': (6,),
        'step_breaks': (4,),
        'step_columns': 3,
        'image_mode': 'below',
    },
    {
        'title': 'LEMONY HERB PASTA',
        'description': 'Bright pasta for two.',
        'prep': 5,
        'cook': 12,
        'ingredients': [
            ('6 oz', '12 oz', 'Spaghetti'), ('1', '2', 'Lemon'),
            ('2 TBSP', '4 TBSP', 'Parmesan'),
        ],
        'steps': [
            ('BOIL PASTA', 'Cook the spaghetti in salted water until al dente.'),
            ('TOSS', 'Toss with lemon, herbs, and parmesan.'),
        ],
        'step_columns': 1,
        'image_mode': 'mixed',
    },
    {
        'title': 'SHEET PAN CHICKEN DINNER',
        'description': 'One pan, very little cleanup.',
        'prep': 15,
        'cook': 40,
        'ingredients': [
            ('4', '8', 'Chicken Thighs'), ('1 lb', '2 lbs', 'Tiny Golden Baby Potatoes'),
            ('2', '4', 'Carrots'), ('1', '2', 'Red Onion'),
            ('3 TBSP', '6 TBSP', 'Olive Oil'), ('1', '2', 'Rosemary Sprig'),
        ],
        'steps': [
            ('HEAT OVEN', 'Heat the oven to 425 degrees.'),
            ('PREP VEGETABLES', 'Chop the potatoes, carrots, and onion into bite-sized pieces.'),
            ('SEASON CHICKEN', 'Rub the chicken with olive oil, salt, pepper, and rosemary.'),
            ('ARRANGE PAN', 'Spread the vegetables on a sheet pan and nestle the chicken on top.'),
            ('ROAST', 'Roast until the chicken is cooked through and the vegetables are tender, '
             'about forty minutes, rotating the pan halfway through for even browning.'),
            ('REST', 'Let the chicken rest for five minutes before serving.'),
            ('GARNISH', 'Scatter with extra rosemary and serve.'),
            ('STORE', 'Store leftovers in the refrigerator for up to three days.'),
            ('REHEAT', 'Reheat gently in a covered pan with a splash of water.'),
            ('SERVE', 'Divide between plates and enjoy.'),
        ],
        'ingredient_breaks': (3,),
        'step_breaks': (5,),
        'step_columns': 2,
        'image_mode': 'above',
        'step_images': {0, 2, 4, 6, 8},
    },
]


def build_variant_pdf(index):
    return build_custom_recipe_pdf(**VARIANTS[index])


def build_split_step_pdf():
    """A card where the body of step 1 continues on the next page."""
    builder = _CardBuilder()
    builder.text('F2', 18, 60, 740, 'SPLIT STEP CARD')
    builder.text('F1', 11, 60, 715, 'A recipe whose first step crosses a page.')
    builder.text('F2', 11, 60, 685, 'INGREDIENTS')
    builder.text('F2', 7, 60, 665, '1 Onion')
    builder.text('F2', 7, 160, 665, '2 Carrots')
    builder.hero(200, 160, 350, 430)
    builder.new_page()
    builder.text('F2', 10, 60, 700, '1 CHOP VEGETABLES')
    builder.text('F1', 9, 60, 670, 'Chop the onion and carrots into small pieces.')
    builder.text('F1', 9, 60, 658, 'Keep the pieces roughly the same size so they')
    builder.new_page()
    builder.text('F1', 9, 60, 700, 'cook at the same rate and turn out tender.')
    builder.text('F2', 10, 60, 640, '2 COOK')
    builder.text('F1', 9, 60, 610, 'Cook the vegetables until soft.')
    return builder.build()


def build_wrapped_title_pdf():
    """A card whose first step title wraps onto a second visual line."""
    builder = _CardBuilder()
    builder.text('F2', 18, 60, 740, 'WRAPPED TITLE CARD')
    builder.text('F1', 11, 60, 715, 'A card with a very long step heading.')
    builder.text('F2', 11, 60, 685, 'INGREDIENTS')
    builder.text('F2', 7, 60, 665, '1 Onion')
    builder.hero(200, 160, 350, 430)
    builder.new_page()
    builder.text('F2', 10, 60, 700, '1 SIMMER THE TOMATOES')
    builder.text('F2', 10, 60, 686, 'UNTIL THEY ARE TENDER')
    builder.text('F1', 9, 60, 660, 'Let the tomatoes bubble gently.')
    builder.text('F2', 10, 60, 600, '2 SERVE')
    builder.text('F1', 9, 60, 570, 'Season and serve.')
    return builder.build()
