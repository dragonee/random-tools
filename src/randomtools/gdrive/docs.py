"""Google Docs, and anything else Drive will only hand over as bytes."""

import io

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

MARKDOWN = 'text/markdown'
PLAIN = 'text/plain'


def export_text(drive, file_id, mime_type=MARKDOWN):
    """Export a Google Doc as markdown, falling back to plain text."""

    try:
        data = drive.files().export(fileId=file_id, mimeType=mime_type).execute()
    except HttpError as error:
        if mime_type == MARKDOWN and error.resp.status in (400, 404, 415):
            data = drive.files().export(fileId=file_id, mimeType=PLAIN).execute()
        else:
            raise

    if isinstance(data, bytes):
        data = data.decode('utf-8', 'replace')

    return data.replace('\r\n', '\n')


def export_bytes(drive, file_id, mime_type):
    """Export a Google file into a binary format, e.g. a spreadsheet as xlsx."""

    return download(drive.files().export_media(fileId=file_id, mimeType=mime_type))


def download_bytes(drive, file_id):
    """Download a file that is already stored in its own format."""

    return download(drive.files().get_media(fileId=file_id, supportsAllDrives=True))


def download(request):
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False

    while not done:
        _, done = downloader.next_chunk()

    return buffer.getvalue()
