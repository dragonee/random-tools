"""
A console stopwatch with flag times, like a race control clock.

Usage:
    timer [options] TIME...
    timer [options] FILE
    timer -h | --help
    timer --version

Arguments:
    TIME    Up to four times, in this order: green, yellow, red, disqualify.
            Bare numbers are minutes, so `timer 10 12 15` counts 10, 12 and
            15 minutes. Units and combinations work too: 90s, 6m30s,
            "6m 30s", 1h5m, 12:30 (mm:ss) and 1:02:30 (hh:mm:ss).
    FILE    A settings file with the same times under a [flags] section:

                [flags]
                green = 12m
                yellow = 15m
                red = 18m
                disqualify = 22m

            Quoted values are fine as well, so a .toml file written that way
            reads the same. Only green, yellow, red and disqualify are known.

Options:
    -s, --start        Start counting as the program runs, not on Space.
    -n, --now          A synonym for --start.
    --no-notify        Do not post macOS notifications when a flag is passed.
    --no-caffeinate    Do not keep the machine awake while the timer runs.
    -h, --help         Show this screen.
    --version          Show version.

Keys:
    Space    start the timer, and pause or resume it afterwards
    q        quit (Ctrl-C works too)

The clock keeps running past the last flag, so an overrun stays visible.
If `caffeinate` is around the machine is kept awake for as long as the timer
lives, and on macOS each flag also raises a notification. That notification
carries Script Editor's icon, since `osascript` is what posts it; install
`terminal-notifier` and it is posted through that instead.

Examples:
    timer 12m 15m 18m 22m
    timer 10 12 15
    timer -s 6m30s
    timer settings.toml
"""

VERSION = '1.0'

import configparser
import math
import os
import re
import select
import shutil
import subprocess
import sys
import time

from docopt import docopt

PROG = os.path.basename(sys.argv[0]) or 'timer'

RESET = '\033[0m'
DIM = '\033[2m'
HIDE_CURSOR = '\033[?25l'
SHOW_CURSOR = '\033[?25h'
CLEAR_LINE = '\r\033[2K'

# name, emoji, colour, the word printed when it is passed
FLAGS = (
    ('green', '🟢', '\033[1;32m', 'GREEN FLAG'),
    ('yellow', '🟡', '\033[1;33m', 'YELLOW FLAG'),
    ('red', '🔴', '\033[1;31m', 'RED FLAG'),
    ('disqualify', '🏴', '\033[1;35m', 'DISQUALIFIED'),
)

FLAG_NAMES = [name for name, _, _, _ in FLAGS]

UNITS = {
    'h': 3600, 'hr': 3600, 'hrs': 3600, 'hour': 3600, 'hours': 3600,
    'm': 60, 'min': 60, 'mins': 60, 'minute': 60, 'minutes': 60,
    's': 1, 'sec': 1, 'secs': 1, 'second': 1, 'seconds': 1,
}

TOKEN = re.compile(r'(\d+(?:\.\d+)?)\s*([a-z]*)')


def die(message, code=1):
    sys.stderr.write("%s: %s\n" % (PROG, message))
    raise SystemExit(code)


def parse_duration(text):
    """Turn 12m, 6m30s, "6m 30s", 90s, 12:30 or a bare 10 into seconds."""
    text = text.strip().lower()

    if not text:
        raise ValueError("empty duration")

    if ':' in text:
        parts = text.split(':')
        if len(parts) > 3 or not all(re.match(r'^\d+(\.\d+)?$', p) for p in parts):
            raise ValueError("%s is not a time" % text)
        parts = [float(p) for p in parts]
        while len(parts) < 3:
            parts.insert(0, 0.0)
        return parts[0] * 3600 + parts[1] * 60 + parts[2]

    total = 0.0
    tokens = 0
    position = 0

    for match in TOKEN.finditer(text):
        if text[position:match.start()].strip():
            raise ValueError("%s is not a time" % text)

        amount, unit = match.groups()
        position = match.end()
        tokens += 1

        if unit == '':
            # A lone number is minutes; mixed in, the unit is missing.
            if match.start() != 0 or text[position:].strip():
                raise ValueError("%s is missing a unit" % text)
            total += float(amount) * 60
        elif unit in UNITS:
            total += float(amount) * UNITS[unit]
        else:
            raise ValueError("%s is not a unit I know" % unit)

    if not tokens or text[position:].strip():
        raise ValueError("%s is not a time" % text)

    return total


def format_time(seconds):
    seconds = int(seconds)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)

    if hours:
        return "%d:%02d:%02d" % (hours, minutes, seconds)

    return "%02d:%02d" % (minutes, seconds)


def read_settings(path):
    """Read the flag times out of a [flags] section."""
    try:
        with open(path) as handle:
            text = handle.read()
    except IOError as e:
        die("cannot read %s: %s" % (path, e.strerror))

    if not re.search(r'(?m)^\s*\[', text):
        text = "[flags]\n" + text

    parser = configparser.ConfigParser(inline_comment_prefixes=('#', ';'))

    try:
        parser.read_string(text, source=path)
    except configparser.Error as e:
        die("cannot parse %s: %s" % (path, e))

    if not parser.has_section('flags'):
        die("%s has no [flags] section" % path)

    times = {}

    for name, value in parser.items('flags'):
        name = name.strip().lower()

        if name not in FLAG_NAMES:
            die("%s: %s is not a flag, expected one of %s" % (
                path, name, ', '.join(FLAG_NAMES)))

        value = value.strip().strip('"').strip("'")

        try:
            times[name] = parse_duration(value)
        except ValueError as e:
            die("%s: %s = %s: %s" % (path, name, value, e))

    if not times:
        die("%s sets no flag times" % path)

    return times


def build_flags(times):
    """Pair the times given with their flag definitions, in clock order."""
    flags = [
        {'name': name, 'emoji': emoji, 'colour': colour, 'word': word,
         'at': times[name]}
        for name, emoji, colour, word in FLAGS
        if name in times
    ]

    return sorted(flags, key=lambda flag: flag['at'])


def colourise(text, colour, enabled):
    if not enabled or not colour:
        return text

    return "%s%s%s" % (colour, text, RESET)


class Notifier(object):
    """A macOS notification for each flag passed.

    They come out under Script Editor's icon, because a notification wears
    the icon of whoever posted it and `osascript` is what posts these. Short
    of shipping a signed application of our own there is no way round that:
    telling the terminal to display it still runs as Script Editor, and an
    applet built here is denied silently. `terminal-notifier` is such an
    application, and is used instead whenever it is installed.
    """

    def __init__(self, enabled=True):
        self.enabled = enabled and sys.platform == 'darwin'
        self.tool = shutil.which('terminal-notifier')
        self.osascript = shutil.which('osascript')

    @staticmethod
    def quoted(value):
        return '"%s"' % value.replace('\\', '\\\\').replace('"', '\\"')

    def post(self, title, message):
        if not self.enabled:
            return

        if self.tool:
            command = [self.tool, '-title', title, '-message', message,
                       '-sound', 'Glass']
        elif self.osascript:
            command = [self.osascript, '-e',
                       'display notification %s with title %s sound name "Glass"'
                       % (self.quoted(message), self.quoted(title))]
        else:
            return

        try:
            subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass


def start_caffeinate():
    """Keep the machine awake for as long as this process lives."""
    if not shutil.which('caffeinate'):
        return None

    try:
        return subprocess.Popen(
            ['caffeinate', '-dimsu', '-w', str(os.getpid())],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return None


class Keyboard(object):
    """Single keypresses off the terminal, without waiting for a newline."""

    def __init__(self):
        self.fd = None
        self.saved = None

    def __enter__(self):
        if not sys.stdin.isatty():
            return self

        try:
            import termios
            import tty
        except ImportError:
            return self

        self.fd = sys.stdin.fileno()
        self.saved = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)

        return self

    def __exit__(self, *exception):
        if self.saved is not None:
            import termios
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)

    @property
    def live(self):
        """Whether keys can be read at all."""
        return self.fd is not None

    def key(self, timeout):
        """The next key pressed within timeout seconds, or None."""
        if self.fd is None:
            time.sleep(timeout)
            return None

        ready, _, _ = select.select([self.fd], [], [], timeout)

        if not ready:
            return None

        return os.read(self.fd, 1).decode('utf-8', 'replace')


def run(keyboard, notifier, flags, start_now, colour):
    live = sys.stdout.isatty()
    erase = CLEAR_LINE if live else ''
    passed = []
    elapsed = 0.0
    started_at = None if not start_now else time.monotonic()
    shown = None

    def status():
        current = passed[-1] if passed else None
        clock = colourise(
            format_time(elapsed),
            current['colour'] if current else '',
            colour,
        )

        if started_at is None and not passed and elapsed == 0.0:
            state = colourise('press Space to start', DIM, colour)
        elif started_at is None:
            state = colourise('paused, Space to resume', DIM, colour)
        else:
            upcoming = [flag for flag in flags if flag not in passed]

            if upcoming:
                # Rounded up, so it never reads 00:00 before it fires.
                state = colourise('%s %s in %s' % (
                    upcoming[0]['emoji'],
                    upcoming[0]['name'],
                    format_time(math.ceil(upcoming[0]['at'] - elapsed)),
                ), DIM, colour)
            else:
                state = colourise('over time, q to quit', DIM, colour)

        return "%s  %s  %s" % (erase, clock, state)

    def announce(flag):
        line = "%s  %s  %s at %s" % (
            erase,
            flag['emoji'],
            colourise(flag['word'], flag['colour'], colour),
            format_time(flag['at']),
        )
        sys.stdout.write(line + ("\a\n" if live else "\n"))

        notifier.post(
            "%s %s" % (flag['emoji'], flag['word'].title()),
            "%s passed" % format_time(flag['at']),
        )

    try:
        if live:
            sys.stdout.write(HIDE_CURSOR)

        while True:
            if started_at is not None:
                elapsed = time.monotonic() - started_at

                for flag in flags:
                    if flag not in passed and elapsed >= flag['at']:
                        passed.append(flag)
                        announce(flag)
                        shown = None

            if live and shown != (int(elapsed), started_at is not None):
                shown = (int(elapsed), started_at is not None)
                sys.stdout.write(status())
                sys.stdout.flush()

            if not keyboard.live and len(passed) == len(flags):
                # Nothing can be pressed here, so the last flag ends it.
                break

            key = keyboard.key(0.1)

            if key is None:
                continue

            if key == ' ':
                if started_at is None:
                    started_at = time.monotonic() - elapsed
                else:
                    elapsed = time.monotonic() - started_at
                    started_at = None

                shown = None
            elif key in ('q', 'Q', '\x1b', '\x04'):
                break
    except KeyboardInterrupt:
        pass
    finally:
        if live:
            sys.stdout.write(SHOW_CURSOR)

    sys.stdout.write("%s  stopped at %s%s\n" % (
        erase,
        format_time(elapsed),
        (", %s passed" % ' '.join(flag['emoji'] for flag in passed)) if passed else '',
    ))


def main():
    arguments = docopt(__doc__, version=VERSION)
    given = arguments['TIME']

    if len(given) == 1 and (os.path.isfile(given[0])
                            or os.path.splitext(given[0])[1] in ('.toml', '.ini', '.cfg')):
        times = read_settings(given[0])
    else:
        if len(given) > len(FLAGS):
            die("at most %d times, one each for %s" % (
                len(FLAGS), ', '.join(FLAG_NAMES)))

        times = {}

        for name, value in zip(FLAG_NAMES, given):
            try:
                times[name] = parse_duration(value)
            except ValueError as e:
                die(str(e))

    flags = build_flags(times)
    colour = sys.stdout.isatty() and not os.environ.get('NO_COLOR')

    header = '  '.join(
        "%s %s %s" % (flag['emoji'], flag['name'], format_time(flag['at']))
        for flag in flags
    )
    print("%s  %s" % (colourise(PROG, DIM, colour), header))

    # --start and --now are two spellings of the one thing; with no
    # keyboard to press there is nothing to wait for either.
    start_now = arguments['--start'] or arguments['--now']

    caffeinate = None if arguments['--no-caffeinate'] else start_caffeinate()

    try:
        with Keyboard() as reader:
            run(
                reader,
                Notifier(enabled=not arguments['--no-notify']),
                flags,
                start_now=start_now or not reader.live,
                colour=colour,
            )
    finally:
        if caffeinate is not None and caffeinate.poll() is None:
            caffeinate.terminate()


if __name__ == '__main__':
    main()
