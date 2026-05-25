"""Slack user lookups."""

from __future__ import annotations

from ._http import slack_get
from .channels import SlackAPIError


def _pick_display_name(user: dict) -> str:
    """Pick the best human-readable name from a Slack user object.

    Prefers ``profile.display_name`` (the name a user explicitly sets),
    falls back to ``profile.real_name``, then top-level ``real_name``,
    then ``name`` (the legacy username), then the user ID.
    """
    profile = user.get('profile') or {}
    for candidate in (profile.get('display_name'),
                      profile.get('real_name'),
                      user.get('real_name'),
                      user.get('name')):
        if candidate:
            return candidate
    return user['id']


def _iter_users(token: str):
    """Yield raw user objects from a paginated ``users.list`` call."""
    headers = {'Authorization': f'Bearer {token}'}
    cursor = None

    while True:
        params = {'limit': 1000}
        if cursor:
            params['cursor'] = cursor

        resp = slack_get('https://slack.com/api/users.list',
                         params=params, headers=headers)
        data = resp.json()

        if not data.get('ok'):
            raise SlackAPIError('users.list', data.get('error', 'unknown'))

        for user in data.get('members', []):
            if user.get('deleted'):
                continue
            yield user

        cursor = data.get('response_metadata', {}).get('next_cursor')
        if not cursor:
            break


def fetch_all_users(token: str) -> dict[str, str]:
    """Fetch every user in the workspace and return ``{user_id: display_name}``.

    Single paginated ``users.list`` call. Cheaper than per-member
    ``users.info`` when resolving members across multiple channels.

    Args:
        token (str): Slack API token.

    Returns:
        dict[str, str]: Map from Slack user ID to a human-readable name.

    Raises:
        SlackAPIError: On Slack API errors.
    """
    return {u['id']: _pick_display_name(u) for u in _iter_users(token)}


def fetch_all_users_detailed(token: str) -> dict[str, dict]:
    """Fetch every user with display name and avatar URL.

    Args:
        token (str): Slack API token.

    Returns:
        dict[str, dict]: Map from user ID to ``{'name': str, 'image_url': str | None}``.
        ``image_url`` is the smallest reliably-present profile image (72px).

    Raises:
        SlackAPIError: On Slack API errors.
    """
    detailed: dict[str, dict] = {}
    for user in _iter_users(token):
        profile = user.get('profile') or {}
        detailed[user['id']] = {
            'name': _pick_display_name(user),
            'image_url': profile.get('image_72') or profile.get('image_48'),
        }
    return detailed
