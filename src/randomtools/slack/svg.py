"""Render a channel summary as SVG (and helpers to rasterize to PNG/JPG)."""

from __future__ import annotations

import base64
import io
import math
from xml.sax.saxutils import escape as xml_escape

import requests
from PIL import Image

PADDING = 16
BADGE_SIZE = 48
BADGE_GAP = 8
BADGES_PER_ROW = 7
AVATAR_PX = 96
TITLE_SIZE = 24
STATUS_SIZE = 14
TITLE_LINE_HEIGHT = 32
STATUS_LINE_HEIGHT = 20
HEADER_BADGE_GAP = 8
BADGE_STROKE = 2
FALLBACK_FILL = '#cbd5e0'


def _load_avatar_png(url: str | None) -> bytes | None:
    """Fetch *url* and return a PNG-encoded, square ``AVATAR_PX`` thumbnail."""
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
    except requests.RequestException:
        return None

    try:
        img = Image.open(io.BytesIO(resp.content)).convert('RGBA')
    except Exception:
        return None

    img = img.resize((AVATAR_PX, AVATAR_PX), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    return buf.getvalue()


def _avatar_data_uri(png_bytes: bytes) -> str:
    return 'data:image/png;base64,' + base64.b64encode(png_bytes).decode('ascii')


def render_channel_svg(channel_name: str,
                       status_line: str,
                       last_modified_line: str,
                       avatar_urls: list[str | None]) -> str:
    """Render a single-channel summary as an SVG document.

    Layout:
        - ``#channel-name`` at 24px
        - status / last-modified line at 14px
        - bordered circular avatars, ``BADGES_PER_ROW`` per row

    Args:
        channel_name: Without leading ``#``.
        status_line: Single string for the activity/status line (14px).
        last_modified_line: Short string prepended to the status line.
        avatar_urls: Slack profile image URLs (may contain ``None`` for users
            without a resolvable image). Order is preserved.

    Returns:
        str: SVG XML document.
    """
    n = len(avatar_urls)
    rows = max(1, math.ceil(n / BADGES_PER_ROW)) if n else 0

    width = PADDING * 2 + BADGES_PER_ROW * BADGE_SIZE + (BADGES_PER_ROW - 1) * BADGE_GAP
    badges_height = rows * BADGE_SIZE + max(0, rows - 1) * BADGE_GAP
    height = (PADDING
              + TITLE_LINE_HEIGHT
              + STATUS_LINE_HEIGHT
              + (HEADER_BADGE_GAP + badges_height if rows else 0)
              + PADDING)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<style>'
        'text { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", '
        'Helvetica, Arial, sans-serif; fill: #1a202c; }'
        '.title { font-size: 24px; font-weight: 600; }'
        '.status { font-size: 14px; fill: #4a5568; }'
        '</style>',
    ]

    title_y = PADDING + TITLE_SIZE  # baseline-ish
    parts.append(
        f'<text class="title" x="{PADDING}" y="{title_y}">'
        f'#{xml_escape(channel_name)}</text>'
    )

    status_y = title_y + STATUS_LINE_HEIGHT
    full_status = f'{last_modified_line}, {status_line}' if last_modified_line else status_line
    parts.append(
        f'<text class="status" x="{PADDING}" y="{status_y}">'
        f'{xml_escape(full_status)}</text>'
    )

    badges_top = PADDING + TITLE_LINE_HEIGHT + STATUS_LINE_HEIGHT + HEADER_BADGE_GAP
    radius = BADGE_SIZE / 2

    for idx, url in enumerate(avatar_urls):
        row, col = divmod(idx, BADGES_PER_ROW)
        x = PADDING + col * (BADGE_SIZE + BADGE_GAP)
        y = badges_top + row * (BADGE_SIZE + BADGE_GAP)
        cx, cy = x + radius, y + radius
        clip_id = f'clip{idx}'

        png = _load_avatar_png(url)
        parts.append(f'<clipPath id="{clip_id}"><circle cx="{cx}" cy="{cy}" r="{radius}"/></clipPath>')

        if png:
            parts.append(
                f'<image x="{x}" y="{y}" width="{BADGE_SIZE}" height="{BADGE_SIZE}" '
                f'clip-path="url(#{clip_id})" preserveAspectRatio="xMidYMid slice" '
                f'href="{_avatar_data_uri(png)}"/>'
            )
        else:
            parts.append(
                f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="{FALLBACK_FILL}"/>'
            )

        parts.append(
            f'<circle cx="{cx}" cy="{cy}" r="{radius - BADGE_STROKE / 2}" '
            f'fill="none" stroke="#ffffff" stroke-width="{BADGE_STROKE}"/>'
        )
        parts.append(
            f'<circle cx="{cx}" cy="{cy}" r="{radius}" '
            f'fill="none" stroke="#cbd5e0" stroke-width="1"/>'
        )

    parts.append('</svg>')
    return '\n'.join(parts)


def svg_to_png(svg: str) -> bytes:
    """Rasterize *svg* to PNG bytes using resvg (Rust, no system deps)."""
    import resvg_py
    return bytes(resvg_py.svg_to_bytes(svg_string=svg))


def svg_to_jpg(svg: str, quality: int = 90) -> bytes:
    """Rasterize *svg* to JPEG bytes (white background)."""
    png_bytes = svg_to_png(svg)
    img = Image.open(io.BytesIO(png_bytes)).convert('RGBA')
    background = Image.new('RGB', img.size, (255, 255, 255))
    background.paste(img, mask=img.split()[3])
    buf = io.BytesIO()
    background.save(buf, format='JPEG', quality=quality, optimize=True)
    return buf.getvalue()
