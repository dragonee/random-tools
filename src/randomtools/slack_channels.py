"""Look up Slack channels by name pattern and show last message age.

Usage:
    slack-channels [options] PATTERN...

Options:
    -d, --days DAYS      Do not show channels with last message newer than DAYS days ago.
    -s, --sort ORDER     Sort by: newest, oldest, name [default: oldest].
    -p, --print FORMAT   Output format: ago, date [default: ago].
    --summary            Only list channel names.
    -h, --help           Show this message.
    --version            Show version information.

Examples:
    slack-channels general random
    slack-channels "proj-.*" --sort oldest
    slack-channels "team-" --days 30 --print date
"""

import re
import sys
import datetime

from docopt import docopt
import requests

from .config.slack import SlackConfigFile

VERSION = '1.1'


def fetch_channels(token):
    """Fetch all public channels using Slack conversations.list API with pagination.

    Requires a user token (xoxp-...) to see all channels the user has access to.
    """
    channels = []
    cursor = None
    url = 'https://slack.com/api/conversations.list'

    while True:
        params = {
            'types': 'public_channel,private_channel',
            'exclude_archived': 'true',
            'limit': 1000,
        }

        if cursor:
            params['cursor'] = cursor

        resp = requests.post(url, data=params, headers={
            'Authorization': f'Bearer {token}',
        })
        resp.raise_for_status()
        data = resp.json()

        if not data.get('ok'):
            print(f"Slack API error: {data.get('error', 'unknown')}", file=sys.stderr)
            sys.exit(1)

        channels.extend(data.get('channels', []))

        cursor = data.get('response_metadata', {}).get('next_cursor')
        if not cursor:
            break

    return channels


def fetch_last_message_ts(token, channel_id):
    """Fetch the timestamp of the last message in a channel."""
    resp = requests.post('https://slack.com/api/conversations.history', data={
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


def match_channels(channels, patterns):
    """Filter channels whose name matches any of the given regex patterns."""
    compiled = []
    for p in patterns:
        try:
            compiled.append(re.compile(p, re.IGNORECASE))
        except re.error as e:
            print(f"Invalid regex pattern '{p}': {e}", file=sys.stderr)
            sys.exit(1)

    return [
        ch for ch in channels
        if any(r.search(ch['name']) for r in compiled)
    ]


def sort_channels(channels, order):
    """Sort channels by the given order."""
    if order == 'newest':
        return sorted(channels, key=lambda ch: ch.get('last_message_ts') or 0, reverse=True)
    elif order == 'oldest':
        return sorted(channels, key=lambda ch: ch.get('last_message_ts') or 0)
    elif order == 'name':
        return sorted(channels, key=lambda ch: ch['name'])
    else:
        print(f"Unknown sort order: {order}", file=sys.stderr)
        sys.exit(1)


def format_age(ts, fmt):
    """Format a timestamp as age or date."""
    if ts is None:
        return 'no messages'

    dt = datetime.datetime.fromtimestamp(ts)

    if fmt == 'date':
        return dt.strftime('%Y-%m-%d')
    else:
        delta = datetime.datetime.now() - dt
        days = delta.days
        if days == 0:
            return 'today'
        elif days == 1:
            return '1 day ago'
        else:
            return f'{days} days ago'


def main():
    arguments = docopt(__doc__, version=VERSION)

    config = SlackConfigFile()

    patterns = arguments['PATTERN']
    days_filter = arguments['--days']
    sort_order = arguments['--sort']
    print_format = arguments['--print']
    summary = arguments['--summary']

    if days_filter is not None:
        try:
            days_filter = int(days_filter)
        except ValueError:
            print(f"--days must be an integer, got: {days_filter}", file=sys.stderr)
            sys.exit(1)

    channels = fetch_channels(config.token)
    matched = match_channels(channels, patterns)

    if not matched:
        print("No channels found.", file=sys.stderr)
        sys.exit(0)

    # Fetch last message timestamp for each matched channel
    for ch in matched:
        ch['last_message_ts'] = fetch_last_message_ts(config.token, ch['id'])

    if days_filter is not None:
        cutoff = datetime.datetime.now() - datetime.timedelta(days=days_filter)
        cutoff_ts = cutoff.timestamp()
        matched = [
            ch for ch in matched
            if ch.get('last_message_ts') is None or ch['last_message_ts'] <= cutoff_ts
        ]

    matched = sort_channels(matched, sort_order)

    if not matched:
        print("No channels found.", file=sys.stderr)
        sys.exit(0)

    for ch in matched:
        if summary:
            print(f"#{ch['name']}")
        else:
            age = format_age(ch.get('last_message_ts'), print_format)
            print(f"#{ch['name']} - {age}")
