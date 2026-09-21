"""
Make workbenches for agents: directories of links to the places they need.

Usage:
    workbench use [DIR...]
    workbench add [PATH...]
    workbench remove PATH...
    workbench list
    workbench init [WORKBENCH] [--from=FILE] [--theme=SCHEME]
    workbench destroy [WORKBENCH] [--keep]
    workbench -h | --help
    workbench --version

Commands:
    use       Offer every subdirectory of DIR for linking; the current
              directory when no DIR is given.
    add       Offer PATH itself, a file or a directory.
    remove    Stop offering PATH, whichever of the two put it there.
    list      Show what is on offer.
    init      Pick what to link into WORKBENCH, the current directory by
              default, and link it. The picks are written to .workbench.toml
              there, so running init again opens them for editing.
    destroy   Remove the links init made, and .workbench.toml with them.

Options:
    --from=FILE       Start from the picks of another workbench: its
                      .workbench.toml, or the directory it is in.
    --theme=SCHEME    auto, dark, light or ansi. auto asks the terminal which
                      one it is [default: auto].
    -k, --keep        Keep .workbench.toml, so init can make the links again.
    -h, --help        Show this screen.
    --version         Show version.

Picking:
    typing        narrows the list; every word typed has to match
    Up, Down      move through the list
    Enter         pick or unpick the highlighted place (Space, in the list)
    Ctrl+T        show only what is picked
    F2            switch between the light and dark colours
    Ctrl+S        save: make and remove links to match the picks
    Esc           leave without changing anything

What is on offer is kept in ~/.workbench/config.toml, or wherever
$WORKBENCH_CONFIG says. Links are named after what they point to; when two
names clash the parent directory's name goes in front, as in `api-docs`.
They point at absolute paths, so a workbench can be moved around.

destroy removes a link only while it still points where init made it point.
Everything else in the workbench, a link changed by hand included, is left
alone.

Examples:
    workbench use ~/Kod
    workbench add ~/notes/agents.md
    workbench init ~/benches/billing
    workbench init ~/benches/invoices --from ~/benches/billing
    workbench destroy ~/benches/billing
"""

VERSION = '1.0'

import collections
import itertools
import os
import re
import select
import subprocess
import sys
import time

try:
    import tomllib
except ImportError:  # Python 3.10 and older
    import tomli as tomllib

from docopt import docopt
from textual import on
from textual.app import App
from textual.binding import Binding
from textual.color import Color
from textual.content import Content
from textual.theme import Theme
from textual.widgets import Footer, Input, SelectionList, Static
from textual.widgets.selection_list import Selection

PROG = os.path.basename(sys.argv[0]) or 'workbench'

WORKBENCH_FILE = '.workbench.toml'
DEFAULT_CONFIG = '~/.workbench/config.toml'
SCHEMES = ('auto', 'dark', 'light', 'ansi')

# makimo.com's colours, as the panel in that repository takes them from
# theme/src/styles/_variables.scss: the red, the beige, the olive and the
# near-black.
MAKIMO_RED = '#ef3f4a'
MAKIMO_BEIGE = '#fff9f4'
MAKIMO_OLIVE = '#756112'
MAKIMO_BLACK = '#1d1d1b'

# `rgb:` and one to four hex digits a channel, the way terminals answer OSC 10
# and 11: xterm with four (rgb:1d1d/1d1d/1b1b), others with two.
OSC_COLOUR = re.compile(
    rb'rgb:([0-9a-f]{1,4})/([0-9a-f]{1,4})/([0-9a-f]{1,4})', re.IGNORECASE)

# COLORFGBG background indices that mean a light window: light grey and white.
LIGHT_ANSI_BACKGROUNDS = ('7', '15')

TerminalColours = collections.namedtuple(
    'TerminalColours', 'dark background foreground')


def die(message, code=1):
    sys.stderr.write("%s: %s\n" % (PROG, message))
    raise SystemExit(code)


def warn(message):
    sys.stderr.write("%s: %s\n" % (PROG, message))


def count(number, one, many):
    return "%d %s" % (number, one if number == 1 else many)


def absolute(path, relative_to=None):
    path = os.path.expanduser(path)

    if relative_to is not None:
        path = os.path.join(relative_to, path)

    return os.path.abspath(path)


def tilde(path):
    """A path the way it is shown, with the home directory as ~."""
    home = os.path.expanduser('~').rstrip(os.sep)

    if path == home:
        return '~'

    if home and path.startswith(home + os.sep):
        return '~' + path[len(home):]

    return path


def overlaps(path, directory):
    """Whether either one is inside the other, or they are the same."""
    path = os.path.realpath(path)
    directory = os.path.realpath(directory)

    return (path == directory
            or path.startswith(directory.rstrip(os.sep) + os.sep)
            or directory.startswith(path.rstrip(os.sep) + os.sep))


# TOML ------------------------------------------------------------------------

def read_toml(path):
    try:
        with open(path, 'rb') as handle:
            return tomllib.load(handle)
    except OSError as e:
        die("cannot read %s: %s" % (tilde(path), e.strerror))
    except tomllib.TOMLDecodeError as e:
        die("cannot parse %s: %s" % (tilde(path), e))


def toml_string(text):
    """A TOML basic string, escaping quotes, backslashes and control characters."""
    escaped = []

    for char in text:
        if char in '"\\':
            escaped.append('\\' + char)
        elif char != '\t' and (ord(char) < 0x20 or ord(char) == 0x7f):
            escaped.append('\\u%04x' % ord(char))
        else:
            escaped.append(char)

    return '"%s"' % ''.join(escaped)


def toml_list(key, values):
    if not values:
        return "%s = []\n" % key

    return "%s = [\n%s]\n" % (
        key, ''.join("    %s,\n" % toml_string(value) for value in values))


def write_file(path, text):
    """Replace path with text in one step, so a failed write keeps the old file."""
    temporary = path + '.tmp'

    try:
        with open(temporary, 'w', encoding='utf-8') as handle:
            handle.write(text)
        os.replace(temporary, path)
    except OSError as e:
        if os.path.exists(temporary):
            os.remove(temporary)
        die("cannot write %s: %s" % (tilde(path), e.strerror))


# What is on offer ------------------------------------------------------------

def config_path():
    return absolute(os.environ.get('WORKBENCH_CONFIG') or DEFAULT_CONFIG)


def load_config():
    """The places on offer, {'use': [...], 'add': [...]}, as absolute paths."""
    path = config_path()
    config = {'use': [], 'add': []}

    if not os.path.exists(path):
        return config

    data = read_toml(path)

    for key in config:
        values = data.get(key, [])

        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            die("%s: %s should be a list of paths" % (tilde(path), key))

        for value in values:
            value = absolute(value, os.path.dirname(path))
            if value not in config[key]:
                config[key].append(value)

    return config


def save_config(config):
    path = config_path()

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError as e:
        die("cannot create %s: %s" % (tilde(os.path.dirname(path)), e.strerror))

    write_file(path, (
        "# The places `workbench init` offers to link. `workbench use`, `add` and\n"
        "# `remove` rewrite this file, so comments added to it are not kept.\n"
        "\n"
        "# Every subdirectory of these is offered.\n"
        "%s"
        "\n"
        "# Each of these is offered itself, file or directory.\n"
        "%s"
    ) % (toml_list('use', config['use']), toml_list('add', config['add'])))


def subdirectories(directory):
    """The directories in directory, hidden ones left out."""
    try:
        names = os.listdir(directory)
    except OSError:
        return []

    return sorted(
        os.path.join(directory, name) for name in names
        if not name.startswith('.') and os.path.isdir(os.path.join(directory, name))
    )


def offered(config):
    places = set(config['add'])

    for directory in config['use']:
        places.update(subdirectories(directory))

    return places


def command_use(directories):
    config = load_config()
    changed = failed = False

    for directory in map(absolute, directories or ['.']):
        if not os.path.isdir(directory):
            warn("%s is not a directory; `%s add` takes files" % (tilde(directory), PROG))
            failed = True
        elif directory in config['use']:
            print("  %s is used already" % tilde(directory))
        else:
            config['use'].append(directory)
            changed = True
            print("+ %s, %s" % (tilde(directory), count(
                len(subdirectories(directory)), 'subdirectory', 'subdirectories')))

    if changed:
        save_config(config)

    if failed:
        raise SystemExit(1)


def command_add(paths):
    config = load_config()
    changed = failed = False

    for path in map(absolute, paths or ['.']):
        if not os.path.exists(path):
            warn("%s does not exist" % tilde(path))
            failed = True
        elif path in config['add']:
            print("  %s is added already" % tilde(path))
        else:
            config['add'].append(path)
            changed = True
            print("+ %s" % tilde(path))

    if changed:
        save_config(config)

    if failed:
        raise SystemExit(1)


def command_remove(paths):
    config = load_config()
    changed = failed = False

    for path in map(absolute, paths):
        found = [key for key in ('use', 'add') if path in config[key]]
        parent = os.path.dirname(path)

        for key in found:
            config[key].remove(path)

        if found:
            changed = True
            print("- %s" % tilde(path))
        elif parent in config['use']:
            warn("%s is offered because %s is used; `%s remove %s` stops that"
                 % (tilde(path), tilde(parent), PROG, tilde(parent)))
            failed = True
        else:
            warn("%s is not on offer" % tilde(path))
            failed = True

    if changed:
        save_config(config)

    if failed:
        raise SystemExit(1)


def command_list():
    config = load_config()

    if not config['use'] and not config['add']:
        print("Nothing is on offer yet. `%s use DIR` offers every subdirectory "
              "of DIR,\n`%s add PATH` offers PATH itself." % (PROG, PROG))
        return

    print(tilde(config_path()))

    if config['use']:
        print("\nused, so every subdirectory is offered:")
        width = max(len(tilde(directory)) for directory in config['use'])

        for directory in config['use']:
            if os.path.isdir(directory):
                note = count(len(subdirectories(directory)), 'subdirectory', 'subdirectories')
            else:
                note = 'missing'
            print("  %-*s  %s" % (width, tilde(directory), note))

    if config['add']:
        print("\nadded:")

        for path in config['add']:
            print("  %s%s" % (tilde(path), '' if os.path.exists(path) else '  missing'))


# The workbench ---------------------------------------------------------------

def workbench_file(directory):
    return os.path.join(directory, WORKBENCH_FILE)


def load_links(path):
    """The [[link]] entries of a workbench file, as {'name', 'path'} dicts."""
    data = read_toml(path)
    entries = data.get('link', [])

    if not isinstance(entries, list):
        die("%s: link should be a list of [[link]] tables" % tilde(path))

    links = []

    for entry in entries:
        name = entry.get('name') if isinstance(entry, dict) else None
        target = entry.get('path') if isinstance(entry, dict) else None

        if not isinstance(name, str) or not isinstance(target, str):
            die("%s: every [[link]] needs a name and a path" % tilde(path))

        # A name is one entry in the workbench, never a way out of it.
        if name in ('', '.', '..') or os.sep in name or (os.altsep and os.altsep in name):
            die("%s: %s cannot name a link" % (tilde(path), toml_string(name)))

        links.append({'name': name, 'path': absolute(target, os.path.dirname(path))})

    return links


def save_links(directory, links):
    lines = [
        "# This directory is a workbench. `workbench init` made the links listed",
        "# here and edits them; `workbench destroy` removes them again.",
    ]

    for link in sorted(links, key=lambda link: link['name'].lower()):
        lines += [
            '',
            '[[link]]',
            'name = %s' % toml_string(link['name']),
            'path = %s' % toml_string(link['path']),
        ]

    write_file(workbench_file(directory), '\n'.join(lines) + '\n')


def points_at(place, target):
    """Whether place is the symlink to target that workbench makes."""
    try:
        return os.readlink(place) == target
    except OSError:
        return False


def unlink(directory, link):
    """Remove one link workbench made, and say what became of it."""
    place = os.path.join(directory, link['name'])

    if points_at(place, link['path']):
        try:
            os.unlink(place)
        except OSError as e:
            return "! %s: %s" % (link['name'], e.strerror)
        return "- %s" % link['name']

    if not os.path.lexists(place):
        return "- %s, gone already" % link['name']

    return "! %s left alone: it is no longer the link to %s" % (
        link['name'], tilde(link['path']))


def free_name(directory, target, taken, preferred=None):
    """A name for the link to target that nothing else in directory has.

    The target's own name first, then with its parent's name in front, then
    numbered. The filesystem may not care about case, so neither does this.
    """
    base = os.path.basename(target) or 'root'
    parent = os.path.basename(os.path.dirname(target))

    names = [base, '%s-%s' % (parent, base)] if parent else [base]

    if preferred:
        names.insert(0, preferred)

    for name in itertools.chain(names, ('%s-%d' % (base, n) for n in itertools.count(2))):
        place = os.path.join(directory, name)

        if name.lower() not in taken and (
                not os.path.lexists(place) or points_at(place, target)):
            return name


def relink(directory, links, picked):
    """Make the links in directory match the picked paths.

    Returns the links there are now and a line of report for each change.
    Unpicked links go first, so the names they free are there to be taken.
    """
    report = [unlink(directory, link) for link in links if link['path'] not in picked]
    current = []
    names = {}

    for link in links:
        if link['path'] not in picked:
            continue

        place = os.path.join(directory, link['name'])

        if points_at(place, link['path']):
            current.append(link)
        elif os.path.lexists(place):
            report.append("! %s is in the way of the link to %s, which gets another name"
                          % (link['name'], tilde(link['path'])))
        else:
            names[link['path']] = link['name']

    taken = set(link['name'].lower() for link in current)
    linked = set(link['path'] for link in current)

    for target in sorted(set(picked) - linked, key=tilde):
        if not os.path.exists(target):
            report.append("! %s does not exist, so it is not linked" % tilde(target))
            continue

        name = free_name(directory, target, taken, names.get(target))
        place = os.path.join(directory, name)

        if not points_at(place, target):
            try:
                os.symlink(target, place)
            except OSError as e:
                report.append("! %s: %s" % (name, e.strerror))
                continue

        report.append("+ %s -> %s" % (name, tilde(target)))
        current.append({'name': name, 'path': target})
        taken.add(name.lower())

    return current, report


def command_init(target, source, scheme):
    if scheme not in SCHEMES:
        die("--theme is one of %s, not %s" % (', '.join(SCHEMES), scheme))

    directory = absolute(target or '.')

    if os.path.exists(directory) and not os.path.isdir(directory):
        die("%s is not a directory" % tilde(directory))

    existing = workbench_file(directory)
    links = load_links(existing) if os.path.isfile(existing) else []
    linked = set(link['path'] for link in links)
    picked = set(linked)

    if source:
        source = absolute(source)

        if os.path.isdir(source):
            source = workbench_file(source)

        if not os.path.isfile(source):
            die("%s is not a workbench file" % tilde(source))

        picked.update(link['path'] for link in load_links(source)
                      if not overlaps(link['path'], directory))

    # A workbench linked into itself, or into something inside it, is a loop.
    places = set(place for place in offered(load_config())
                 if not overlaps(place, directory))
    places.update(picked)

    if not places:
        die("nothing is on offer yet: `%s use DIR` offers every subdirectory of "
            "DIR, `%s add PATH` offers PATH itself" % (PROG, PROG))

    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        die("init picks what to link on a terminal, and this is not one")

    # Before the app starts: the question needs the terminal in raw mode for a
    # moment, which is not something to do underneath a running Textual.
    colours = detect_colours()

    picks = Picker(directory, places, picked, linked, bool(links) or os.path.isfile(existing),
                   colours, scheme).run()

    if picks is None:
        print("Nothing changed.")
        return

    try:
        os.makedirs(directory, exist_ok=True)
    except OSError as e:
        die("cannot create %s: %s" % (tilde(directory), e.strerror))

    current, report = relink(directory, links, picks)
    save_links(directory, current)

    for line in report:
        print(line)

    print("%s: %s, listed in %s" % (
        tilde(directory), count(len(current), 'link', 'links'), WORKBENCH_FILE))

    if any(line.startswith('!') for line in report):
        raise SystemExit(1)


def command_destroy(target, keep):
    directory = absolute(target or '.')
    existing = workbench_file(directory)

    if not os.path.isfile(existing):
        die("%s is not a workbench: there is no %s in it" % (tilde(directory), WORKBENCH_FILE))

    report = [unlink(directory, link) for link in load_links(existing)]

    if not keep:
        try:
            os.remove(existing)
            report.append("- %s" % WORKBENCH_FILE)
        except OSError as e:
            report.append("! %s: %s" % (WORKBENCH_FILE, e.strerror))

    for line in report:
        print(line)

    if any(line.startswith('!') for line in report):
        raise SystemExit(1)


# Colours ---------------------------------------------------------------------

def detect_colours(timeout=0.15):
    """Whether the terminal is dark, and in what colours when it says.

    Asked the way makimo.com's panel asks: OSC 11 and 10 for the background
    and foreground, which most terminals answer with an actual colour; then
    COLORFGBG, which only tells light from dark; then the macOS appearance,
    which the terminal may or may not follow. Failing all three it is dark,
    as Textual assumes too.
    """
    background, foreground = query_colours(timeout)

    if background is not None:
        red, green, blue = background
        return TerminalColours(
            dark=(0.299 * red + 0.587 * green + 0.114 * blue) < 128,
            background='#%02x%02x%02x' % background,
            foreground='#%02x%02x%02x' % foreground if foreground else None,
        )

    fgbg = os.environ.get('COLORFGBG', '').split(';')[-1].strip()

    if fgbg.isdigit():
        return TerminalColours(fgbg not in LIGHT_ANSI_BACKGROUNDS, None, None)

    if sys.platform == 'darwin':
        try:
            # The key is not there at all in light mode.
            result = subprocess.run(
                ['defaults', 'read', '-g', 'AppleInterfaceStyle'],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                universal_newlines=True, timeout=1.0,
            )
            return TerminalColours('dark' in result.stdout.lower(), None, None)
        except (OSError, subprocess.SubprocessError):
            pass

    return TerminalColours(True, None, None)


def query_colours(timeout):
    """Background and foreground as (r, g, b), or None when not answered.

    Both are asked for before either answer is read, so a terminal that
    answers costs one round trip, and one that does not costs one timeout.
    """
    try:
        import termios
        import tty
    except ImportError:
        return None, None

    try:
        handle = open('/dev/tty', 'r+b', buffering=0)
    except OSError:
        return None, None

    reply = b''

    with handle:
        descriptor = handle.fileno()

        try:
            saved = termios.tcgetattr(descriptor)
        except termios.error:
            return None, None

        try:
            tty.setraw(descriptor)
            handle.write(b'\x1b]11;?\x07\x1b]10;?\x07')
            deadline = time.monotonic() + timeout

            while len(OSC_COLOUR.findall(reply)) < 2:
                remaining = deadline - time.monotonic()

                if remaining <= 0 or not select.select([descriptor], [], [], remaining)[0]:
                    break

                chunk = os.read(descriptor, 128)

                if not chunk:
                    break

                reply += chunk
        except (OSError, termios.error):
            pass
        finally:
            termios.tcsetattr(descriptor, termios.TCSADRAIN, saved)

    # The answers come back in the order asked: background, then foreground.
    found = [scale_channels(groups) for groups in OSC_COLOUR.findall(reply)]

    return (found[0] if found else None), (found[1] if len(found) > 1 else None)


def scale_channels(groups):
    """rgb: channels are a fraction of their own width, so ff and ffff are both full."""
    return tuple(int(round(int(group, 16) * 255 / (16 ** len(group) - 1)))
                 for group in groups)


def steps(background, dark):
    """Surface and panel, stepped away from the background.

    Derived rather than fixed, so the edges stay visible whatever the
    terminal's own colour turned out to be. Black and white are at the end of
    their range, so they are stepped a little further.
    """
    colour = Color.parse(background)

    if dark:
        amounts = (0.06, 0.12) if colour.brightness < 0.02 else (0.05, 0.11)
        return tuple(colour.lighten(amount).hex for amount in amounts)

    amounts = (0.04, 0.09) if colour.brightness > 0.98 else (0.03, 0.08)
    return tuple(colour.darken(amount).hex for amount in amounts)


def build_themes(colours):
    """makimo.com's dark and light schemes, in that order.

    The terminal's own background and foreground go only into the scheme that
    matches it, so F2 still gives a usable window. The accents stay fixed,
    once for each scheme: a hue that reads on black washes out on beige.
    """
    dark_background = (colours.dark and colours.background) or MAKIMO_BLACK
    dark_foreground = (colours.dark and colours.foreground) or '#e8e4e0'
    light_background = (not colours.dark and colours.background) or MAKIMO_BEIGE
    light_foreground = (not colours.dark and colours.foreground) or MAKIMO_BLACK

    dark_surface, dark_panel = steps(dark_background, dark=True)
    light_surface, light_panel = steps(light_background, dark=False)

    dark = Theme(
        name='makimo-dark',
        dark=True,
        background=dark_background,
        surface=dark_surface,
        panel=dark_panel,
        foreground=dark_foreground,
        primary=MAKIMO_RED,
        secondary='#c9a227',  # the olive, lifted until it reads on black
        accent=MAKIMO_RED,
        warning='#d9a441',
        error='#ff6b6b',  # lighter than the brand red, so an error is not the brand
        success='#4ebf71',
    )

    light = Theme(
        name='makimo-light',
        dark=False,
        background=light_background,
        surface=light_surface,
        panel=light_panel,
        foreground=light_foreground,
        primary='#d92b36',  # the brand red, darkened to hold contrast on beige
        secondary=MAKIMO_OLIVE,
        accent='#d92b36',
        warning='#8a6d1f',
        error='#b3222b',
        success='#2f8f4e',
    )

    return dark, light


# Picking ---------------------------------------------------------------------

class PlaceList(SelectionList):
    """The places on offer. The list has no use for letters, so typing here
    goes on in the search box."""

    def on_key(self, event):
        search = self.app.query_one('#search', Input)

        if event.key == 'backspace':
            search.focus()
            search.cursor_position = len(search.value)
            search.action_delete_left()
        elif event.is_printable and event.character and event.character != ' ':
            search.focus()
            search.cursor_position = len(search.value)
            search.insert_text_at_cursor(event.character)
        else:
            return

        event.stop()
        event.prevent_default()


class Picker(App):
    """A search box over the places on offer, each with a checkbox.

    Runs to the set of picked paths, or to None when left without saving.
    """

    ENABLE_COMMAND_PALETTE = False

    CSS = """
    #where {
        height: 1;
        margin: 1 2 0 2;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }

    #search {
        margin: 1 1 0 1;
    }

    #places {
        height: 1fr;
        margin: 0 1;
    }

    #status {
        height: 1;
        margin: 0 2;
        color: $text-muted;
    }
    """

    BINDINGS = [
        # Priority, so Enter picks from the search box as well as the list.
        Binding('enter', 'pick', 'Pick', priority=True),
        Binding('ctrl+s', 'save', 'Save', priority=True),
        Binding('escape', 'cancel', 'Cancel', priority=True),
        Binding('ctrl+c', 'cancel', 'Cancel', priority=True, show=False),
        Binding('ctrl+t', 'picked_only', 'Picked only', priority=True),
        Binding('f2', 'toggle_scheme', 'Light/dark', priority=True),
        # Only reached from the search box; the list has its own.
        Binding('up', "move('cursor_up')", show=False),
        Binding('down', "move('cursor_down')", show=False),
        Binding('pageup', "move('page_up')", show=False),
        Binding('pagedown', "move('page_down')", show=False),
    ]

    def __init__(self, directory, places, picked, linked, existing, colours, scheme):
        super().__init__()
        self.directory = directory
        self.places = sorted(places, key=lambda place: tilde(place).lower())
        self.picked = set(picked)
        self.linked = set(linked)
        self.existing = existing
        self.colours = colours
        self.scheme = scheme
        self.picked_only = False
        self.shown = len(self.places)

        # Directories end in a slash, the way ls -F shows them.
        self.labels = {
            place: tilde(place) + (os.sep if os.path.isdir(place) else '')
            for place in self.places
        }
        self.missing = set(place for place in self.places if not os.path.exists(place))

    def compose(self):
        yield Static(id='where')
        yield Input(placeholder='Search: every word has to match', id='search')
        yield PlaceList(id='places')
        yield Static(id='status')
        yield Footer()

    def on_mount(self):
        self.dark_theme, self.light_theme = build_themes(self.colours)

        for theme in (self.dark_theme, self.light_theme):
            self.register_theme(theme)

        if self.scheme == 'ansi':
            # Textual's pass-through themes, every colour the terminal's own.
            self.theme = 'ansi-dark' if self.colours.dark else 'ansi-light'
        elif self.scheme == 'dark' or (self.scheme == 'auto' and self.colours.dark):
            self.theme = self.dark_theme.name
        else:
            self.theme = self.light_theme.name

        self.query_one('#where', Static).update(Content.assemble(
            ('Linking into ', '$text-muted'),
            (tilde(self.directory), 'bold $primary'),
            ('  %s' % (count(len(self.linked), 'link', 'links') if self.existing
                       else 'a new workbench'), '$text-muted'),
        ))

        self.refill()
        self.query_one('#search', Input).focus()

    def prompt(self, place, terms):
        label = self.labels[place]
        cut = label.rstrip(os.sep).rfind(os.sep) + 1
        prompt = Content.assemble((label[:cut], '$text-muted'), label[cut:])

        for term in terms:
            prompt = prompt.highlight_regex(
                re.compile(re.escape(term), re.IGNORECASE), style='bold underline')

        if place in self.missing:
            prompt = Content.assemble(prompt, ('  missing', '$error'))

        return prompt

    def highlighted_place(self):
        places = self.query_one(PlaceList)

        if places.highlighted is None:
            return None

        return places.get_option_at_index(places.highlighted).value

    def refill(self):
        """Show the places that match the search, keeping the highlight."""
        places = self.query_one(PlaceList)
        terms = self.query_one('#search', Input).value.lower().split()
        keep = self.highlighted_place()

        shown = [
            place for place in self.places
            if all(term in self.labels[place].lower() for term in terms)
            and (place in self.picked or not self.picked_only)
        ]

        places.clear_options()
        places.add_options(
            Selection(self.prompt(place, terms), place, place in self.picked)
            for place in shown
        )

        if shown:
            places.highlighted = shown.index(keep) if keep in shown else 0

        self.shown = len(shown)
        self.update_status()

    def update_status(self):
        parts = ["%d picked" % len(self.picked)]

        added = len(self.picked - self.linked)
        dropped = len(self.linked - self.picked)

        if added or dropped:
            parts.append("+%d -%d to save" % (added, dropped))

        if self.shown == len(self.places):
            parts.append(count(len(self.places), 'place', 'places'))
        else:
            parts.append("%d of %d shown" % (self.shown, len(self.places)))

        if self.picked_only:
            parts.append("picked only")

        self.query_one('#status', Static).update(' · '.join(parts))

    @on(Input.Changed, '#search')
    def search_changed(self, event):
        self.refill()

    @on(SelectionList.SelectionToggled)
    def toggled(self, event):
        place = event.selection.value

        if place in self.picked:
            self.picked.discard(place)
        else:
            self.picked.add(place)

        self.update_status()

    def action_pick(self):
        places = self.query_one(PlaceList)

        if places.highlighted is not None:
            places.toggle(places.get_option_at_index(places.highlighted))

    def action_move(self, action):
        getattr(self.query_one(PlaceList), 'action_' + action)()

    def action_picked_only(self):
        self.picked_only = not self.picked_only
        self.refill()

    def action_toggle_scheme(self):
        """Flip light and dark, for when the terminal was guessed wrong."""
        if self.theme == 'ansi-dark':
            self.theme = 'ansi-light'
        elif self.theme == 'ansi-light':
            self.theme = 'ansi-dark'
        elif self.theme == self.dark_theme.name:
            self.theme = self.light_theme.name
        else:
            self.theme = self.dark_theme.name

    def action_save(self):
        self.exit(set(self.picked))

    def action_cancel(self):
        self.exit(None)


def main():
    arguments = docopt(__doc__, version=VERSION)

    if arguments['use']:
        command_use(arguments['DIR'])
    elif arguments['add']:
        command_add(arguments['PATH'])
    elif arguments['remove']:
        command_remove(arguments['PATH'])
    elif arguments['list']:
        command_list()
    elif arguments['init']:
        command_init(arguments['WORKBENCH'], arguments['--from'], arguments['--theme'])
    elif arguments['destroy']:
        command_destroy(arguments['WORKBENCH'], arguments['--keep'])


if __name__ == '__main__':
    main()
