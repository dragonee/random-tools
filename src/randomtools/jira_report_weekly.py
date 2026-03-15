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

import requests
from docopt import docopt

from .config.slack import SlackConfigFile

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


def resolve_channel_id(token, channel):
    """Resolve a channel name to its ID. Returns the input if already an ID."""
    if channel.startswith('C') and channel[1:].isalnum():
        return channel

    headers = {'Authorization': f'Bearer {token}'}
    cursor = None

    while True:
        params = {'limit': 200, 'types': 'public_channel,private_channel'}
        if cursor:
            params['cursor'] = cursor

        resp = requests.get('https://slack.com/api/conversations.list',
                            params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        if not data.get('ok'):
            print(f"Slack error (conversations.list): {data.get('error', 'unknown')}", file=sys.stderr)
            return None

        for ch in data.get('channels', []):
            if ch['name'] == channel:
                return ch['id']

        cursor = data.get('response_metadata', {}).get('next_cursor')
        if not cursor:
            break

    print(f"Slack channel '{channel}' not found.", file=sys.stderr)
    return None


def send_to_slack(token, channel, filepath):
    """Upload a file to a Slack channel with an accompanying message."""
    headers = {'Authorization': f'Bearer {token}'}

    channel_id = resolve_channel_id(token, channel)
    if not channel_id:
        return False

    content = filepath.read_bytes()

    # Step 1: Get upload URL
    resp = requests.get('https://slack.com/api/files.getUploadURLExternal', params={
        'filename': filepath.name,
        'length': len(content),
    }, headers=headers)
    resp.raise_for_status()
    data = resp.json()

    if not data.get('ok'):
        print(f"Slack error (getUploadURL): {data.get('error', 'unknown')}", file=sys.stderr)
        return False

    upload_url = data['upload_url']
    file_id = data['file_id']

    # Step 2: Upload file content
    resp = requests.post(upload_url, data=content, headers={
        'Content-Type': 'application/octet-stream',
    })
    resp.raise_for_status()

    # Step 3: Complete upload and share to channel
    resp = requests.post('https://slack.com/api/files.completeUploadExternal', json={
        'files': [{'id': file_id, 'title': filepath.stem}],
        'channel_id': channel_id,
        'initial_comment': 'Podsumowanie tygodnia',
    }, headers={
        **headers,
        'Content-Type': 'application/json',
    })
    resp.raise_for_status()
    data = resp.json()

    if not data.get('ok'):
        print(f"Slack error (completeUpload): {data.get('error', 'unknown')}", file=sys.stderr)
        return False

    print(f"Sent weekly report to #{channel}", file=sys.stderr)
    return True


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

    if not send_to_slack(slack_config.token, channel, filepath):
        return 1

    # Step 3b: Journal the entry
    if not run_journal(sunday, filepath):
        print("journal command failed.", file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    exit(main())
