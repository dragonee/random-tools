"""Internal HTTP helpers for the Slack client.

Centralizes rate-limit handling so callers never have to think about 429s.
On Slack-style ``429 Too Many Requests`` responses, ``slack_get`` honors the
``Retry-After`` header and otherwise falls back to capped exponential backoff.
"""

from __future__ import annotations

import sys
import time

import requests

DEFAULT_MAX_RETRIES = 5
DEFAULT_BASE_BACKOFF = 1.0
MAX_BACKOFF = 60.0


def _parse_retry_after(header_value: str | None, attempt: int) -> float:
    """Pick a sleep duration: honor Retry-After, else exponential backoff."""
    if header_value:
        try:
            return min(float(header_value), MAX_BACKOFF)
        except ValueError:
            pass
    return min(DEFAULT_BASE_BACKOFF * (2 ** attempt), MAX_BACKOFF)


def slack_get(url: str, *,
              params: dict | None = None,
              headers: dict | None = None,
              max_retries: int = DEFAULT_MAX_RETRIES) -> requests.Response:
    """GET *url* with retry-on-429 honoring ``Retry-After``.

    Sleeps according to Slack's ``Retry-After`` header on 429 responses, or
    exponential backoff (1s, 2s, 4s, ...) capped at ``MAX_BACKOFF`` if the
    header is absent or unparseable. Up to ``max_retries`` attempts before
    re-raising via ``raise_for_status``.

    Args:
        url: Full URL.
        params: Query string params.
        headers: Request headers (Authorization etc.).
        max_retries: How many times to retry after a 429 before giving up.

    Returns:
        requests.Response: A successful (non-429, 2xx) response.

    Raises:
        requests.HTTPError: After exhausting retries, or on any non-429 4xx/5xx.
    """
    attempt = 0
    while True:
        resp = requests.get(url, params=params, headers=headers)

        if resp.status_code != 429:
            resp.raise_for_status()
            return resp

        if attempt >= max_retries:
            resp.raise_for_status()

        delay = _parse_retry_after(resp.headers.get('Retry-After'), attempt)
        print(f'slack: rate limited, sleeping {delay:.1f}s '
              f'(retry {attempt + 1}/{max_retries})',
              file=sys.stderr)
        time.sleep(delay)
        attempt += 1
