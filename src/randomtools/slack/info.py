"""Report activity tier, last message, and members for Slack channels.

Reads channel names (one per line) from a file or stdin and prints, for each
channel, an activity tier (dead/quiet/active/firehose) based on a recent
message-count sample, the time of the last message, and the channel members'
display names.

Usage:
    slack-channel-info [options]
    slack-channel-info [options] -f FILE
    slack-channel-info -h | --help
    slack-channel-info --version

Options:
    -f FILE, --file FILE    Read channel names from FILE (default: stdin).
    -d DAYS, --days DAYS    Window in days for activity sampling [default: 7].
    -l N, --limit N         Max members listed per channel [default: 25].
    --all-users             Include members with no resolvable display name
                            (bots, integrations, Slack Connect users). By
                            default these are skipped.
    --format FORMAT         Output format: text, svg, png, jpg [default: text].
                            For text, prints all channels to stdout.
                            For svg/png/jpg, writes <channel-name>.<ext> per
                            channel into --out-dir (default: current dir).
    -o DIR, --out-dir DIR   Output directory for image formats [default: .].
    --force                 Regenerate output files even if they already exist
                            (image formats only). By default, channels whose
                            output file is present are skipped entirely (no
                            API calls).
    -h, --help              Show this message.
    --version               Show version information.

Activity tiers (over the sample window):
    dead      - no messages
    quiet     - 1 to 10 messages
    active    - 11 to 100 messages
    firehose  - more than 100 messages (or response truncated)

Examples:
    echo -e "general\\ndev" | slack-channel-info
    slack-channel-info -f channels.txt --days 30 --limit 50
    slack-channel-info -f channels.txt --format svg -o ./out
    slack-channel-info -f channels.txt --format png
"""

from __future__ import annotations

import datetime
import re
import sys
from pathlib import Path

from docopt import docopt

from ..config.slack import SlackConfigFile
from .channels import (
    ChannelNotFoundError,
    SlackAPIError,
    count_messages_since,
    fetch_channel_members,
    fetch_last_message_ts,
    find_channel,
)
from .users import fetch_all_users_detailed

VERSION = '1.1'

VALID_FORMATS = ('text', 'svg', 'png', 'jpg')


def read_channel_names(path: str | None) -> list[str]:
    """Read channel names from a file path or stdin, one per line."""
    if path:
        with open(path) as f:
            raw = f.read()
    else:
        raw = sys.stdin.read()

    return [line.strip() for line in raw.splitlines() if line.strip()]


def classify(count: int, has_more: bool) -> str:
    """Bucket a message count into an activity tier."""
    if has_more or count > 100:
        return 'firehose'
    if count == 0:
        return 'dead'
    if count <= 10:
        return 'quiet'
    return 'active'


def format_age(ts: float | None) -> str:
    """Human-readable age of a Unix timestamp ('today', '3 days ago', ...)."""
    if ts is None:
        return 'never'
    delta = datetime.datetime.now() - datetime.datetime.fromtimestamp(ts)
    days = delta.days
    if days == 0:
        return 'today'
    if days == 1:
        return '1 day ago'
    return f'{days} days ago'


def format_count(count: int, has_more: bool, days: int) -> str:
    """Format the message-count line, indicating truncation when present."""
    suffix = f'last {days} days'
    if has_more:
        return f'>{count} messages, {suffix}'
    if count == 1:
        return f'1 message, {suffix}'
    return f'{count} messages, {suffix}'


def render_channel_text(name: str,
                        count: int, has_more: bool, days: int,
                        last_ts: float | None,
                        member_names: list[str],
                        limit: int) -> str:
    """Build the multi-line text output block for one channel."""
    tier = classify(count, has_more)
    lines = [
        f'#{name}',
        f'- {tier} ({format_count(count, has_more, days)})',
        f'- last message {format_age(last_ts)}',
    ]

    shown = member_names[:limit]
    for n in shown:
        lines.append(f'- {n}')

    remaining = len(member_names) - len(shown)
    if remaining > 0:
        lines.append(f'- … and {remaining} more')

    return '\n'.join(lines)


def slugify(name: str) -> str:
    """Filesystem-safe slug of a channel name."""
    s = re.sub(r'[^A-Za-z0-9._-]+', '-', name).strip('-')
    return s or 'channel'


def main():
    arguments = docopt(__doc__, version=VERSION)

    try:
        days = int(arguments['--days'])
    except ValueError:
        print(f"--days must be an integer, got: {arguments['--days']}", file=sys.stderr)
        return 1

    try:
        limit = int(arguments['--limit'])
    except ValueError:
        print(f"--limit must be an integer, got: {arguments['--limit']}", file=sys.stderr)
        return 1

    fmt = arguments['--format'].lower()
    if fmt not in VALID_FORMATS:
        print(f"--format must be one of {', '.join(VALID_FORMATS)}, got: {fmt}",
              file=sys.stderr)
        return 1

    out_dir = Path(arguments['--out-dir'])
    if fmt != 'text':
        out_dir.mkdir(parents=True, exist_ok=True)

    names = read_channel_names(arguments['--file'])
    if not names:
        print("No channel names provided.", file=sys.stderr)
        return 1

    try:
        config = SlackConfigFile()
    except KeyError as e:
        print(str(e), file=sys.stderr)
        return 1

    try:
        users = fetch_all_users_detailed(config.token)
    except SlackAPIError as e:
        print(str(e), file=sys.stderr)
        return 1

    if fmt != 'text':
        from . import svg as svg_mod

    oldest_ts = (datetime.datetime.now() - datetime.timedelta(days=days)).timestamp()
    force = arguments['--force']

    text_blocks = []
    for raw_name in names:
        if fmt != 'text' and not force:
            cached_path = out_dir / f'{slugify(raw_name.lstrip("#"))}.{fmt}'
            if cached_path.exists():
                print(f'skip {cached_path} (exists, use --force to regenerate)',
                      file=sys.stderr)
                continue

        try:
            channel_id, resolved = find_channel(config.token, raw_name)
        except ChannelNotFoundError as e:
            print(f"# {raw_name}: {e.error}", file=sys.stderr)
            continue
        except SlackAPIError as e:
            print(f"# {raw_name}: {e}", file=sys.stderr)
            continue

        display_name = resolved or raw_name.lstrip('#')

        try:
            count, has_more, latest_in_window = count_messages_since(
                config.token, channel_id, oldest_ts,
            )
            last_ts = latest_in_window
            if last_ts is None:
                last_ts = fetch_last_message_ts(config.token, channel_id)

            member_ids = fetch_channel_members(config.token, channel_id)
        except SlackAPIError as e:
            print(f"# {display_name}: {e}", file=sys.stderr)
            continue

        if arguments['--all-users']:
            members = [(uid, users.get(uid, {'name': uid, 'image_url': None}))
                       for uid in member_ids]
        else:
            members = [(uid, users[uid]) for uid in member_ids if uid in users]

        members.sort(key=lambda pair: pair[1]['name'].lower())
        capped = members[:limit]

        if fmt == 'text':
            text_blocks.append(render_channel_text(
                display_name, count, has_more, days, last_ts,
                [m['name'] for _, m in members], limit,
            ))
            continue

        status_line = f'{classify(count, has_more)} ({format_count(count, has_more, days)})'
        last_line = f'updated {format_age(last_ts)}'
        avatar_urls = [m['image_url'] for _, m in capped]

        svg_text = svg_mod.render_channel_svg(
            display_name, status_line, last_line, avatar_urls,
        )

        slug = slugify(display_name)
        out_path = out_dir / f'{slug}.{fmt}'

        if fmt == 'svg':
            out_path.write_text(svg_text, encoding='utf-8')
        elif fmt == 'png':
            out_path.write_bytes(svg_mod.svg_to_png(svg_text))
        elif fmt == 'jpg':
            out_path.write_bytes(svg_mod.svg_to_jpg(svg_text))

        print(f'wrote {out_path}', file=sys.stderr)

    if fmt == 'text':
        print('\n\n'.join(text_blocks))
    return 0


if __name__ == '__main__':
    sys.exit(main())
