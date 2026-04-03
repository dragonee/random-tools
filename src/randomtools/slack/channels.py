"""Slack channel operations: lookup, listing, members."""

from __future__ import annotations

import requests


class SlackAPIError(Exception):
    """Raised when a Slack API call returns ok=false."""

    def __init__(self, method: str, error: str):
        self.method = method
        self.error = error
        super().__init__(f"Slack API error ({method}): {error}")


class ChannelNotFoundError(SlackAPIError):
    """Raised when a channel name cannot be resolved to an ID."""

    def __init__(self, channel_name: str):
        self.channel_name = channel_name
        super().__init__('conversations.list', f"Channel '{channel_name}' not found")


def find_channel(token: str, channel_name: str) -> tuple[str, str | None]:
    """Find a Slack channel by name and return ``(channel_id, channel_name)``.

    Strips leading ``#`` from *channel_name*. If the input already looks like
    a channel ID (starts with ``C``, rest alphanumeric), it is returned
    directly as ``(channel_id, None)`` without making an API call.

    Args:
        token (str): Slack API token.
        channel_name (str): Channel name (e.g. ``"general"``, ``"#general"``)
            or channel ID (e.g. ``"C01234ABCDE"``).

    Returns:
        tuple[str, str | None]: ``(channel_id, channel_name)``; *channel_name*
        is ``None`` when a raw ID was passed in.

    Raises:
        ChannelNotFoundError: If no channel matches the given name.
        SlackAPIError: On other Slack API errors.
    """
    channel_name = channel_name.lstrip('#')

    if channel_name.startswith('C') and channel_name[1:].isalnum() and len(channel_name) > 1:
        return channel_name, None

    headers = {'Authorization': f'Bearer {token}'}
    cursor = None

    while True:
        params = {
            'types': 'public_channel,private_channel',
            'exclude_archived': 'true',
            'limit': 1000,
        }
        if cursor:
            params['cursor'] = cursor

        resp = requests.get('https://slack.com/api/conversations.list',
                            params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        if not data.get('ok'):
            raise SlackAPIError('conversations.list', data.get('error', 'unknown'))

        for ch in data.get('channels', []):
            if ch['name'] == channel_name:
                return ch['id'], ch['name']

        cursor = data.get('response_metadata', {}).get('next_cursor')
        if not cursor:
            break

    raise ChannelNotFoundError(channel_name)


def fetch_all_channels(token: str, exclude_archived: bool = True) -> list[dict]:
    """Fetch all accessible channels (public and private).

    Args:
        token (str): Slack API token.
        exclude_archived (bool): Skip archived channels. Defaults to ``True``.

    Returns:
        list[dict]: Channel objects as returned by the Slack API.

    Raises:
        SlackAPIError: On Slack API errors.
    """
    channels = []
    headers = {'Authorization': f'Bearer {token}'}
    cursor = None

    while True:
        params = {
            'types': 'public_channel,private_channel',
            'exclude_archived': 'true' if exclude_archived else 'false',
            'limit': 1000,
        }
        if cursor:
            params['cursor'] = cursor

        resp = requests.get('https://slack.com/api/conversations.list',
                            params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        if not data.get('ok'):
            raise SlackAPIError('conversations.list', data.get('error', 'unknown'))

        channels.extend(data.get('channels', []))

        cursor = data.get('response_metadata', {}).get('next_cursor')
        if not cursor:
            break

    return channels


def fetch_channel_members(token: str, channel_id: str) -> list[str]:
    """Fetch all member user IDs from a Slack channel.

    Args:
        token (str): Slack API token.
        channel_id (str): Channel ID.

    Returns:
        list[str]: Slack user IDs of channel members.

    Raises:
        SlackAPIError: On Slack API errors.
    """
    members = []
    headers = {'Authorization': f'Bearer {token}'}
    cursor = None

    while True:
        params = {
            'channel': channel_id,
            'limit': 1000,
        }
        if cursor:
            params['cursor'] = cursor

        resp = requests.get('https://slack.com/api/conversations.members',
                            params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        if not data.get('ok'):
            raise SlackAPIError('conversations.members', data.get('error', 'unknown'))

        members.extend(data.get('members', []))

        cursor = data.get('response_metadata', {}).get('next_cursor')
        if not cursor:
            break

    return members


def fetch_last_message_ts(token: str, channel_id: str) -> float | None:
    """Fetch the timestamp of the last message in a channel.

    Args:
        token (str): Slack API token.
        channel_id (str): Channel ID.

    Returns:
        float | None: Unix timestamp of the last message, or ``None`` if the
        channel has no messages or the API call fails.
    """
    resp = requests.get('https://slack.com/api/conversations.history', params={
        'channel': channel_id,
        'limit': 1,
    }, headers={
        'Authorization': f'Bearer {token}',
    })
    resp.raise_for_status()
    data = resp.json()

    if not data.get('ok'):
        return None

    messages = data.get('messages', [])
    if not messages:
        return None

    return float(messages[0]['ts'])
