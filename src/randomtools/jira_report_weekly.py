"""Generate and distribute weekly Jira report.

Runs jira-report --week -L2, saves to ~/.jira/reports/weekly/<sunday>.md,
opens EDITOR for comments, then sends to Slack and journals the entry.

Usage:
    jira-report-weekly [options]

Options:
    -h, --help              Show this message.
    --version               Show version information.
    -c, --channel CHANNEL   Slack channel to post to (overrides config).
    -Y, --last              Use previous week instead of current.
    -f, --force             Overwrite report file even if it already exists.
"""

import datetime
import os
import subprocess
import sys
from pathlib import Path

from docopt import docopt

from .config.slack import SlackConfigFile
from .slack import find_channel, upload_file, SlackAPIError

VERSION = '1.0'

REPORTS_DIR = Path.home() / '.jira' / 'reports' / 'weekly'


def get_sunday(last=False):
    """Return the Sunday (last day) of the current or previous week."""
    today = datetime.date.today()
    # Monday = 0, Sunday = 6
    monday = today - datetime.timedelta(days=today.weekday())
    if last:
        monday = monday - datetime.timedelta(weeks=1)
    sunday = monday + datetime.timedelta(days=6)
    return sunday


def generate_report(last=False):
    """Run jira-report --week -L2 and return its stdout."""
    cmd = ['jira-report', '--week', '-L2']
    if last:
        cmd.append('-Y')
    result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)
    if result.returncode != 0:
        return None
    return result.stdout


def open_editor(filepath):
    """Open file in EDITOR. Return True if editor exited successfully."""
    editor = os.environ.get('EDITOR', 'vi')
    result = subprocess.run([editor, str(filepath)])
    return result.returncode == 0


def run_journal(sunday, filepath):
    """Run journal -t Weekly --date <date> -f <filepath>."""
    date_str = sunday.strftime('%Y-%m-%d')
    result = subprocess.run([
        'journal', '-t', 'Weekly',
        '--date', date_str,
        '-f', str(filepath),
        '--force',
    ])
    return result.returncode == 0


def main():
    """Main entry point for jira-report-weekly command."""
    arguments = docopt(__doc__, version=VERSION)

    last = arguments['--last']
    force = arguments['--force']
    sunday = get_sunday(last=last)
    date_str = sunday.strftime('%Y-%m-%d')

    # Ensure reports directory exists
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    filepath = REPORTS_DIR / f'{date_str}.md'

    # Step 1: Generate report (don't overwrite existing unless --force)
    if filepath.exists() and not force:
        print(f"Report already exists: {filepath}", file=sys.stderr)
    else:
        print(f"Generating report for week ending {date_str}...", file=sys.stderr)
        report = generate_report(last=last)
        if report is None:
            print("Failed to generate report.", file=sys.stderr)
            return 1
        filepath.write_text(report)
        print(f"Saved to {filepath}", file=sys.stderr)

    # Step 2: Open editor for comments
    if not open_editor(filepath):
        print("Editor exited with error, aborting.", file=sys.stderr)
        return 1

    # Step 3a: Send to Slack
    try:
        slack_config = SlackConfigFile()
    except KeyError as e:
        print(f"Slack configuration error: {e}", file=sys.stderr)
        return 1

    channel = arguments['--channel'] or slack_config.weekly_report_channel
    if not channel:
        print("No Slack channel configured. Set [Weekly Report] channel in ~/.slack/config.ini or use --channel.", file=sys.stderr)
        return 1

    try:
        channel_id, _ = find_channel(slack_config.token, channel)
        upload_file(
            slack_config.token, channel_id,
            filepath.name, filepath.read_bytes(),
            initial_comment='Podsumowanie tygodnia',
            title=filepath.stem,
        )
        print(f"Sent weekly report to #{channel}", file=sys.stderr)
    except SlackAPIError as e:
        print(str(e), file=sys.stderr)
        return 1

    # Step 3b: Journal the entry
    if not run_journal(sunday, filepath):
        print("journal command failed.", file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    exit(main())
