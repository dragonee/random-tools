"""Small markdown helpers shared by the dumpers."""

import re
import unicodedata

TRANSLITERATIONS = str.maketrans({
    'ł': 'l', 'Ł': 'L', 'ß': 'ss', 'æ': 'ae', 'Æ': 'AE', 'ø': 'o', 'Ø': 'O',
})


def slug(text, fallback='untitled'):
    """A lowercase, dash-separated file name stem."""

    text = unicodedata.normalize('NFKD', (text or '').translate(TRANSLITERATIONS))
    text = text.encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^A-Za-z0-9]+', '-', text).strip('-').lower()

    return text[:80] or fallback


def cell(value):
    """One table cell: never empty, never breaking the row it sits in."""

    text = '' if value is None else str(value)

    return text.replace('|', r'\|').replace('\r\n', '\n').replace('\n', '<br>').strip()


def table(rows):
    """Render rows (the first one being the header) as a markdown table."""

    rows = [[cell(value) for value in row] for row in rows]
    rows = [row for row in rows if row]

    if not rows:
        return ''

    width = max(len(row) for row in rows)
    rows = [row + [''] * (width - len(row)) for row in rows]

    header, body = rows[0], rows[1:]
    widths = [max(3, *(len(row[i]) for row in rows)) for i in range(width)]

    def line(row):
        return '| ' + ' | '.join(value.ljust(widths[i]) for i, value in enumerate(row)) + ' |'

    lines = [line(header), '| ' + ' | '.join('-' * w for w in widths) + ' |']
    lines += [line(row) for row in body]

    return '\n'.join(lines)


def heading(text, level=1):
    return '{} {}'.format('#' * level, text)
