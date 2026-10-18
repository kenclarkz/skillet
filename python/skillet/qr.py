"""Server-side QR code rendering (segno, SVG only — no PIL needed)."""

from __future__ import annotations

import io
import re

import segno


def qr_svg(value: str, size: int = 160) -> str:
    """Render a QR code as a fixed-size inline SVG string."""
    qr = segno.make(value, error="m")
    buffer = io.BytesIO()
    qr.save(buffer, kind="svg", border=1, dark="#241c15", light=None)
    svg = buffer.getvalue().decode("utf-8")
    svg = re.sub(r'<\?xml[^>]*\?>\s*', "", svg)
    svg = re.sub(r'width="\d+"', f'width="{size}"', svg, count=1)
    svg = re.sub(r'height="\d+"', f'height="{size}"', svg, count=1)
    return svg.strip()
