"""
Create one-line summary of all documents in a directory with links.

Usage:
    onelinesummary [options] PATH

Options:
    -p, --pattern PATTERN  Pattern to match files [default: *.md]
    -h, --help  Show this message.
    --version   Show version information.
"""

from pathlib import Path

from docopt import docopt

import os

IGNORED_ITEMS = [
    'README.md',
]

def main():
    arguments = docopt(__doc__, version='1.0.1')

    path = Path(arguments['PATH']).resolve(strict=True)
    cwd = Path.cwd().resolve(strict=True)

    rel = path.relative_to(cwd)

    for item in sorted(rel.glob(arguments['--pattern'])):
        if item.name in IGNORED_ITEMS:
            continue

        print("- [{}]({})".format(str(item.name), str(item)))