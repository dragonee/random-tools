"""Send a message or file to a Slack channel.

Usage:
    slack-send [options] CHANNEL [TEXT...]
    slack-send [options] CHANNEL -f FILE [TEXT...]

Options:
    -f FILE, --file FILE           Send FILE as a Slack file upload.
    -h, --help                     Show this message.
    --version                      Show version information.

Arguments:
    CHANNEL   Channel name or ID (e.g. general, #general, C01234ABCDE).
    TEXT      Message text. If omitted and no --file, reads from stdin.
              When used with --file, sent as the accompanying comment.

Examples:
    slack-send general "Hello, world!"
    slack-send '#dev' "Deploy complete"
    echo "Pipeline passed" | slack-send general
    slack-send general -f report.md
    slack-send general -f report.md "Weekly report"
    echo "See attached" | slack-send general -f report.md
"""

import sys
from pathlib import Path

from docopt import docopt

from ..config.slack import SlackConfigFile
from .channels import SlackAPIError, find_channel
from .files import upload_file
from .messages import post_message

VERSION = '1.0'


def main():
    """Main entry point for slack-send command."""
    arguments = docopt(__doc__, version=VERSION)

    channel = arguments['CHANNEL']
    text_parts = arguments['TEXT']
    file_path = arguments['--file']

    # Resolve text from args or stdin
    if text_parts:
        text = ' '.join(text_parts)
    elif not sys.stdin.isatty():
        text = sys.stdin.read().strip() or None
    else:
        text = None

    if not file_path and not text:
        print("No text provided.", file=sys.stderr)
        return 1

    try:
        config = SlackConfigFile()
    except KeyError as e:
        print(str(e), file=sys.stderr)
        return 1

    try:
        channel_id, _ = find_channel(config.token, channel)
    except SlackAPIError as e:
        print(str(e), file=sys.stderr)
        return 1

    try:
        if file_path:
            p = Path(file_path)
            if not p.exists():
                print(f"File not found: {file_path}", file=sys.stderr)
                return 1
            upload_file(
                config.token, channel_id,
                p.name, p.read_bytes(),
                initial_comment=text,
                title=p.stem,
            )
            print(f"Uploaded {p.name} to #{channel}", file=sys.stderr)
        if text and not file_path:
            post_message(config.token, channel_id, text)
            print(f"Message sent to #{channel}", file=sys.stderr)
    except SlackAPIError as e:
        print(str(e), file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    exit(main())
