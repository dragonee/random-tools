"""List the git repositories in a directory that have unstaged changes.

Usage:
    dirty [options] [DIR]
    dirty -h | --help
    dirty --version

Arguments:
    DIR    The directory holding the repositories (default: .).

Options:
    -d, --depth N       How many levels below DIR to look for repositories [default: 1].
    -n, --no-untracked  Do not count untracked files as changes.
    -s, --staged        Count staged changes too, so anything uncommitted shows.
    -v, --verbose       List the changed files under each repository.
    -h, --help          Show this message.
    --version           Show version information.

A repository has unstaged changes when a tracked file differs from what is
staged, or when it has untracked files. DIR counts itself when it is a
repository, and no repository is searched for repositories inside it.

Repositories are printed one per line, as paths under DIR, so the list can be
fed to other commands:

    for repo in $(dirty ~/Kod); do git -C "$repo" diff --stat; done
"""
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from docopt import docopt

VERSION = '1.0'


def find_repositories(directory, depth):
    """Yield DIRECTORY if it is a repository, or else the repositories below it."""
    if (directory / '.git').exists():
        yield directory
        return

    if depth <= 0:
        return

    try:
        children = sorted(directory.iterdir(), key=lambda path: path.name.lower())
    except OSError:
        return

    for child in children:
        if child.is_dir() and not child.name.startswith('.'):
            yield from find_repositories(child, depth - 1)


def status(repository, untracked):
    """Return the short status lines of REPOSITORY and git's error, if any."""
    result = subprocess.run(
        ['git', '--no-optional-locks', 'status', '--porcelain',
         '--untracked-files=' + ('normal' if untracked else 'no')],
        cwd=repository,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return [], result.stderr.strip() or f'git status exited with {result.returncode}'
    return result.stdout.splitlines(), None


def is_change(line, staged):
    """Whether a porcelain status line counts: XY is index and work tree state."""
    index, worktree = line[0], line[1]
    return worktree != ' ' or (staged and index not in ' ?')


def main():
    args = docopt(__doc__, version=VERSION)

    directory = Path(args['DIR'] or '.')
    if not directory.is_dir():
        sys.exit(f'dirty: {directory} is not a directory')

    try:
        depth = int(args['--depth'])
    except ValueError:
        sys.exit(f"dirty: --depth takes a number, not {args['--depth']!r}")

    repositories = list(find_repositories(directory, depth))
    untracked = not args['--no-untracked']

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = pool.map(lambda repository: status(repository, untracked), repositories)

        for repository, (lines, error) in zip(repositories, results):
            if error:
                print(f'dirty: {repository}: {error}', file=sys.stderr)
                continue

            changes = [line for line in lines if is_change(line, args['--staged'])]
            if not changes:
                continue

            print(repository)
            if args['--verbose']:
                for line in changes:
                    print(f'    {line}')


if __name__ == '__main__':
    main()
