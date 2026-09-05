"""Turn Google Drive links (or bare file ids) into file ids."""

import re
import sys
from pathlib import Path

import yaml

ID = r'[A-Za-z0-9_-]{10,}'

BARE_ID = re.compile(r'\A' + ID + r'\Z')

# /forms/d/e/<id>/viewform carries the published id, which the API rejects.
PUBLISHED_FORM = re.compile(r'/forms/d/e/' + ID)

PATTERNS = tuple(re.compile(pattern) for pattern in (
    r'/(?:document|spreadsheets|presentation|forms)/d/(' + ID + ')',
    r'/file/d/(' + ID + ')',
    r'/folders/(' + ID + ')',
    r'[?&]id=(' + ID + ')',
))


class LinkError(ValueError):
    pass


class Link:
    """A link to dump, with the name the caller would like it filed under."""

    def __init__(self, url, name=None):
        self.url = url
        self.name = name
        self.file_id = file_id(url)

    def __repr__(self):
        return 'Link({!r}, name={!r})'.format(self.url, self.name)


def file_id(link):
    """Extract the Drive file id out of anything the user may paste."""

    link = (link or '').strip()

    if not link:
        raise LinkError("empty link")

    if BARE_ID.match(link):
        return link

    if PUBLISHED_FORM.search(link):
        raise LinkError(
            "{} is a published form link, which the API cannot read. "
            "Open the form for editing and use its /forms/d/<id>/edit link.".format(link)
        )

    for pattern in PATTERNS:
        match = pattern.search(link)

        if match:
            return match.group(1)

    raise LinkError("not a Google Drive link: {}".format(link))


def links_from_lines(lines):
    """One link per line, blank lines and # comments ignored."""

    for line in lines:
        line = line.strip()

        if line and not line.startswith('#'):
            yield Link(line)


def links_from_yaml(data):
    """A list of links, a list of {name, link} maps, or a name -> link map.

    A top-level `links:` key is unwrapped first, so both shapes below work:

        links:
          - https://docs.google.com/document/d/ID/edit
          - name: Retro notes
            link: https://docs.google.com/document/d/ID/edit
    """

    if isinstance(data, dict):
        if 'links' in data:
            data = data['links']
        else:
            data = [{'name': name, 'link': link} for name, link in data.items()]

    if not isinstance(data, list):
        raise LinkError("expected a list of links, got {}".format(type(data).__name__))

    for entry in data:
        if isinstance(entry, str):
            yield Link(entry)
            continue

        if not isinstance(entry, dict):
            raise LinkError("expected a link or a map of them, got {!r}".format(entry))

        url = entry.get('link') or entry.get('url') or entry.get('id')

        if not url:
            raise LinkError("no link/url/id key in {!r}".format(entry))

        yield Link(url, name=entry.get('name') or entry.get('title'))


def links_from_file(path):
    if str(path) == '-':
        return list(links_from_lines(sys.stdin))

    path = Path(path).expanduser()
    text = path.read_text(encoding='utf-8')

    if path.suffix.lower() in ('.yml', '.yaml'):
        return list(links_from_yaml(yaml.safe_load(text) or []))

    return list(links_from_lines(text.splitlines()))


def collect(urls, input_file=None, stdin=None):
    """Links from the command line, from --input, or from a pipe."""

    stdin = sys.stdin if stdin is None else stdin

    links = [Link(url) for url in urls]

    if input_file:
        links += links_from_file(input_file)
    elif not links and not stdin.isatty():
        links += list(links_from_lines(stdin))

    return links
