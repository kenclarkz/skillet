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
