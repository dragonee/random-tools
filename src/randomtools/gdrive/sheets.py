"""Google Sheets, read through the Sheets API so every tab comes along."""

import csv
import io

from . import markdown

XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


class Spreadsheet:
    def __init__(self, title, sheets):
        self.title = title
        self.sheets = sheets  # list of (sheet title, rows)


def fetch(sheets_service, file_id):
    """Every tab of a spreadsheet, as it is formatted in the browser."""

    meta = sheets_service.spreadsheets().get(
        spreadsheetId=file_id,
        fields='properties/title,sheets/properties(title,index)',
    ).execute()

    titles = [sheet['properties']['title'] for sheet in meta.get('sheets', [])]

    if not titles:
        return Spreadsheet(meta['properties']['title'], [])

    result = sheets_service.spreadsheets().values().batchGet(
        spreadsheetId=file_id,
        ranges=["'{}'".format(title.replace("'", "''")) for title in titles],
        valueRenderOption='FORMATTED_VALUE',
    ).execute()

    ranges = result.get('valueRanges', [])

    return Spreadsheet(meta['properties']['title'], [
        (title, ranges[i].get('values', []) if i < len(ranges) else [])
        for i, title in enumerate(titles)
    ])


def to_markdown(spreadsheet, level=1):
    """One markdown document, a table per tab."""

    parts = [markdown.heading(spreadsheet.title, level)]

    for title, rows in spreadsheet.sheets:
        if len(spreadsheet.sheets) > 1:
            parts.append(markdown.heading(title, level + 1))

        parts.append(markdown.table(rows) if rows else '*(empty)*')

    return '\n\n'.join(parts) + '\n'


def to_csv(rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    width = max((len(row) for row in rows), default=0)

    for row in rows:
        writer.writerow(list(row) + [''] * (width - len(row)))

    return buffer.getvalue()
