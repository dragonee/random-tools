"""Slack message sending via chat.postMessage."""

from __future__ import annotations

import requests

from .channels import SlackAPIError


def post_message(token: str, channel_id: str, text: str) -> dict:
    """Send a text message to a Slack channel via ``chat.postMessage``.

    Args:
        token (str): Slack API token.
        channel_id (str): Channel ID to post to.
        text (str): Message text (supports Slack mrkdwn formatting).

    Returns:
        dict: Slack API response data.

    Raises:
        SlackAPIError: If the Slack API returns an error.
    """
    resp = requests.post('https://slack.com/api/chat.postMessage', json={
        'channel': channel_id,
        'text': text,
    }, headers={
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    })
    resp.raise_for_status()
    data = resp.json()

    if not data.get('ok'):
        raise SlackAPIError('chat.postMessage', data.get('error', 'unknown'))

    return data
