"""Slack file upload via the 3-step external upload flow."""

from __future__ import annotations

import requests

from .channels import SlackAPIError


def upload_file(token: str, channel_id: str, filename: str, content: bytes,
                initial_comment: str | None = None, title: str | None = None) -> dict:
    """Upload a file to a Slack channel.

    Uses the 3-step external upload flow:
    ``getUploadURLExternal`` -> PUT content -> ``completeUploadExternal``.

    Args:
        token (str): Slack API token.
        channel_id (str): Channel ID to share the file to.
        filename (str): Display name for the file (e.g. ``"report.md"``).
        content (bytes): File content.
        initial_comment (str | None): Optional message posted alongside the file.
        title (str | None): File title shown in Slack. Defaults to *filename*.

    Returns:
        dict: Slack API response data.

    Raises:
        SlackAPIError: If any step of the upload flow fails.
    """
    headers = {'Authorization': f'Bearer {token}'}

    # Step 1: Get upload URL
    resp = requests.get('https://slack.com/api/files.getUploadURLExternal', params={
        'filename': filename,
        'length': len(content),
    }, headers=headers)
    resp.raise_for_status()
    data = resp.json()

    if not data.get('ok'):
        raise SlackAPIError('files.getUploadURLExternal', data.get('error', 'unknown'))

    upload_url = data['upload_url']
    file_id = data['file_id']

    # Step 2: Upload file content
    resp = requests.post(upload_url, data=content, headers={
        'Content-Type': 'application/octet-stream',
    })
    resp.raise_for_status()

    # Step 3: Complete upload and share to channel
    complete_payload = {
        'files': [{'id': file_id, 'title': title or filename}],
        'channel_id': channel_id,
    }
    if initial_comment:
        complete_payload['initial_comment'] = initial_comment

    resp = requests.post('https://slack.com/api/files.completeUploadExternal',
                         json=complete_payload, headers={
                             **headers,
                             'Content-Type': 'application/json',
                         })
    resp.raise_for_status()
    data = resp.json()

    if not data.get('ok'):
        raise SlackAPIError('files.completeUploadExternal', data.get('error', 'unknown'))

    return data
