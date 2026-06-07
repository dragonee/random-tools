"""Show per-user worklog totals for one or more Jira tasks or projects.

For each task (or whole project), fetch all worklogs and report how much
time each person has logged, in the form:

    TASK-1:
    - Person1: 12h
    - Person2: 5h

Usage:
    jira-task-users TASK... [options]

Arguments:
    TASK  An issue key (e.g. ABC-123) or a project key (e.g. ABC). When a
          project key is given, every issue in that project with logged time
          is included.

Options:
    -h, --help          Show this message.
    --version           Show version information.
    --no-group          Report each TASK separately instead of pooling them
                        into a single combined total.
    --target TIME       Target time per user (e.g. 40h, 1.5h, or a bare number
                        of hours like 40). Shows progress as [logged/target]
                        and how many hours are remaining against it.
    --missing-only      With --target, only show users below the target.
    --users FILE        Restrict the report to users listed in FILE, one per
                        line (emails or display names; blank lines and '#'
                        comments ignored). Each line is resolved to a Jira
                        account so emails match authors even when their email is
                        hidden. With --target, users from FILE with no logged
                        time are still shown as [0/TARGET].
    --json              Output JSON instead of formatted text.

Examples:
    jira-task-users ABC-123
    jira-task-users ABC-123 ABC-456 --no-group
    jira-task-users ABC --target 40h --missing-only
    jira-task-users ABC --users team.txt --target 40h --json
"""

import json
import re
import sys

from docopt import docopt
import requests
from requests.auth import HTTPBasicAuth

from .config.jira import JiraConfigFile
from .jira import parse_time_to_seconds

VERSION = '1.0'

RE_ISSUE_KEY = re.compile(r'^[A-Za-z][A-Za-z0-9_]*-\d+$')
RE_PROJECT_KEY = re.compile(r'^[A-Za-z][A-Za-z0-9_]*$')


# --- Time helpers ---

def format_duration(seconds):
    """Format seconds as 'Xh Ym'."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"


def hours_number(seconds):
    """Format seconds as a compact hour number (e.g. 40, 12.5)."""
    return f"{seconds / 3600:.2f}".rstrip('0').rstrip('.')


def parse_duration_to_seconds(text):
    """Parse a target duration. A bare number is treated as hours.

    Returns seconds, or None if it cannot be parsed.
    """
    text = text.strip()
    if re.match(r'^[0-9.]+$', text):
        try:
            return int(float(text) * 3600)
        except ValueError:
            return None
    seconds, _ = parse_time_to_seconds(text)
    return seconds


# --- Fetching (get worklogs) ---

def normalize_worklog(raw, issue_key):
    """Flatten a raw Jira worklog into the fields we care about."""
    author = raw.get('author', {})
    return {
        'id': raw.get('id'),
        'issue': issue_key,
        'accountId': author.get('accountId'),
        'displayName': author.get('displayName') or author.get('accountId') or 'Unknown',
        'emailAddress': author.get('emailAddress'),
        'timeSpentSeconds': raw.get('timeSpentSeconds', 0),
    }


def fetch_issue_worklogs(config, issue_key):
    """Fetch all worklogs (all authors) for a single issue."""
    url = f"{config.base_url}/rest/api/3/issue/{issue_key}/worklog"
    auth = HTTPBasicAuth(config.email, config.api_token)
    headers = {"Accept": "application/json"}

    worklogs = []
    start_at = 0

    while True:
        params = {"startAt": start_at, "maxResults": 100}
        try:
            response = requests.get(url, headers=headers, auth=auth, params=params)
        except requests.exceptions.RequestException as e:
            print(f"Error connecting to Jira API: {e}", file=sys.stderr)
            return worklogs

        if response.status_code != 200:
            print(f"Failed to fetch worklogs for {issue_key}. Status: {response.status_code}",
                  file=sys.stderr)
            return worklogs

        data = response.json()
        for raw in data.get('worklogs', []):
            worklogs.append(normalize_worklog(raw, issue_key))

        total = data.get('total', 0)
        if start_at + 100 >= total:
            break
        start_at += 100

    return worklogs


def fetch_project_issue_keys(config, project):
    """Find all issue keys in a project that have logged time."""
    jql = f"project = {project} AND timespent > 0"
    url = f"{config.base_url}/rest/api/3/search/jql"
    auth = HTTPBasicAuth(config.email, config.api_token)
    headers = {"Accept": "application/json"}

    keys = []
    next_page_token = None

    while True:
        params = {"jql": jql, "fields": "key", "maxResults": 100}
        if next_page_token:
            params["nextPageToken"] = next_page_token

        try:
            response = requests.get(url, headers=headers, auth=auth, params=params)
        except requests.exceptions.RequestException as e:
            print(f"Error connecting to Jira API: {e}", file=sys.stderr)
            return keys

        if response.status_code != 200:
            print(f"Failed to search issues for project {project}. Status: {response.status_code}",
                  file=sys.stderr)
            print(response.text, file=sys.stderr)
            return keys

        data = response.json()
        for issue in data.get('issues', []):
            keys.append(issue['key'])

        next_page_token = data.get('nextPageToken')
        if not next_page_token:
            break

    return keys


def fetch_task_worklogs(config, token):
    """Resolve a TASK argument to its worklogs (issue or whole project)."""
    token = token.upper()

    if RE_ISSUE_KEY.match(token):
        print(f"Fetching worklogs for {token}...", file=sys.stderr)
        return fetch_issue_worklogs(config, token)

    if RE_PROJECT_KEY.match(token):
        print(f"Discovering issues in project {token}...", file=sys.stderr)
        keys = fetch_project_issue_keys(config, token)
        print(f"Fetching worklogs for {len(keys)} issue(s) in {token}...", file=sys.stderr)
        worklogs = []
        for key in keys:
            worklogs.extend(fetch_issue_worklogs(config, key))
        return worklogs

    print(f"Skipping '{token}': not a valid issue or project key.", file=sys.stderr)
    return []


# --- Grouping (enhance + group) ---

def aggregate_users(worklogs):
    """Sum time per user, de-duplicating worklogs by id.

    Returns a dict keyed by account id (or display name) with
    {'name', 'email', 'account_id', 'seconds'} values.
    """
    seen_ids = set()
    users = {}

    for w in worklogs:
        wid = w['id']
        if wid is not None:
            if wid in seen_ids:
                continue
            seen_ids.add(wid)

        key = w['accountId'] or w['displayName']
        user = users.setdefault(key, {
            'name': w['displayName'],
            'email': w['emailAddress'],
            'account_id': w['accountId'],
            'seconds': 0,
        })
        user['seconds'] += w['timeSpentSeconds']

    return users


def match_resolved_users(aggregated, resolved_users, target_seconds):
    """Map aggregated worklog authors onto the requested user list.

    Matching is done by Jira account id first (always present on worklogs,
    unlike email), then by display-name / email alias as a fallback. Users in
    the list with no logged time are surfaced as zero entries when a target is
    set.
    """
    by_account = {r['account_id']: i for i, r in enumerate(resolved_users) if r['account_id']}
    by_alias = {}
    for i, r in enumerate(resolved_users):
        for alias in r['aliases']:
            by_alias.setdefault(alias, i)

    totals = [0] * len(resolved_users)
    matched = [False] * len(resolved_users)

    for user in aggregated.values():
        name_key = (user['name'] or '').lower()
        email_key = (user['email'] or '').lower()

        if user['account_id'] and user['account_id'] in by_account:
            idx = by_account[user['account_id']]
        elif name_key and name_key in by_alias:
            idx = by_alias[name_key]
        elif email_key and email_key in by_alias:
            idx = by_alias[email_key]
        else:
            continue

        totals[idx] += user['seconds']
        matched[idx] = True

    entries = []
    for i, r in enumerate(resolved_users):
        # Drop unmatched users unless a target makes their 0/target meaningful.
        if not matched[i] and target_seconds is None:
            continue
        entries.append({'name': r['name'], 'seconds': totals[i]})

    return entries


def build_group(label, worklogs, resolved_users, target_seconds, missing_only):
    """Turn a list of worklogs into a rendered group: {'task', 'users'}."""
    aggregated = aggregate_users(worklogs)

    if resolved_users is None:
        entries = [{'name': u['name'], 'seconds': u['seconds']} for u in aggregated.values()]
    else:
        entries = match_resolved_users(aggregated, resolved_users, target_seconds)

    if target_seconds is not None:
        for entry in entries:
            entry['remaining_seconds'] = max(0, target_seconds - entry['seconds'])
            entry['met'] = entry['seconds'] >= target_seconds
        if missing_only:
            entries = [e for e in entries if not e['met']]

    entries.sort(key=lambda e: (-e['seconds'], e['name'].lower()))

    return {'task': label, 'users': entries}


# --- Output (print) ---

def render_group_text(group, target_seconds):
    """Render a group as a list of text lines."""
    lines = [f"{group['task']}:"]

    if not group['users']:
        lines.append("- (no worklogs)")
        return lines

    for entry in group['users']:
        line = f"- {entry['name']}: {format_duration(entry['seconds'])}"
        if target_seconds is not None:
            line += f" [{hours_number(entry['seconds'])}/{hours_number(target_seconds)}]"
            if entry['remaining_seconds'] > 0:
                line += f" (remaining {format_duration(entry['remaining_seconds'])})"
            else:
                line += " (target met)"
        lines.append(line)

    return lines


def group_to_json(group, target_seconds):
    """Render a group as a JSON-serializable dict."""
    users = []
    for entry in group['users']:
        data = {
            'name': entry['name'],
            'seconds': entry['seconds'],
            'hours': round(entry['seconds'] / 3600, 2),
        }
        if target_seconds is not None:
            data['remaining_seconds'] = entry['remaining_seconds']
            data['remaining_hours'] = round(entry['remaining_seconds'] / 3600, 2)
            data['met'] = entry['met']
        users.append(data)

    return {'task': group['task'], 'users': users}


def load_users_file(path):
    """Read a line-separated user list, ignoring blanks and '#' comments."""
    with open(path) as f:
        return [
            line.strip()
            for line in f
            if line.strip() and not line.strip().startswith('#')
        ]


def lookup_jira_user(config, query):
    """Resolve an email (or name) to a Jira (account_id, display_name, email).

    Worklog authors rarely expose their email, so the file's emails can't be
    matched directly; resolving them here gives us the account id to match on.
    Returns (None, None, None) if the user can't be found.
    """
    url = f"{config.base_url}/rest/api/3/user/search"
    auth = HTTPBasicAuth(config.email, config.api_token)
    headers = {"Accept": "application/json"}

    try:
        response = requests.get(url, headers=headers, auth=auth, params={"query": query})
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Jira API: {e}", file=sys.stderr)
        return None, None, None

    if response.status_code != 200:
        return None, None, None

    users = response.json()
    if not users:
        return None, None, None

    needle = query.lower()
    for user in users:
        if (user.get('emailAddress', '') or '').lower() == needle \
                or (user.get('displayName', '') or '').lower() == needle:
            return user.get('accountId'), user.get('displayName'), user.get('emailAddress')

    first = users[0]
    return first.get('accountId'), first.get('displayName'), first.get('emailAddress')


def resolve_file_users(config, lines):
    """Resolve each user-file line to a Jira identity for reliable matching.

    Each resolved user is {'account_id', 'name', 'aliases'} where 'name' is the
    Jira display name used for output (falling back to the raw line) and
    'aliases' are lowercased strings worklog authors can be matched against.
    """
    resolved = []
    for line in lines:
        account_id, display_name, email = lookup_jira_user(config, line)

        aliases = {line.lower()}
        if display_name:
            aliases.add(display_name.lower())
        if email:
            aliases.add(email.lower())

        if account_id is None:
            print(f"Warning: could not resolve user '{line}' to a Jira account.",
                  file=sys.stderr)

        resolved.append({
            'account_id': account_id,
            'name': display_name or line,
            'aliases': aliases,
        })

    return resolved


def main():
    """Main entry point for jira-task-users command."""
    arguments = docopt(__doc__, version=VERSION)

    if arguments['--missing-only'] and not arguments['--target']:
        print("Error: --missing-only requires --target.", file=sys.stderr)
        return 1

    target_seconds = None
    if arguments['--target']:
        target_seconds = parse_duration_to_seconds(arguments['--target'])
        if target_seconds is None:
            print(f"Error: could not parse target time '{arguments['--target']}'.", file=sys.stderr)
            return 1

    file_lines = None
    if arguments['--users']:
        try:
            file_lines = load_users_file(arguments['--users'])
        except OSError as e:
            print(f"Error reading users file: {e}", file=sys.stderr)
            return 1

    try:
        config = JiraConfigFile()
    except Exception as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        print("Please create ~/.jira/config.ini with your Jira credentials", file=sys.stderr)
        return 1

    resolved_users = None
    if file_lines is not None:
        print(f"Resolving {len(file_lines)} user(s) from {arguments['--users']}...",
              file=sys.stderr)
        resolved_users = resolve_file_users(config, file_lines)

    # Pipeline: get worklogs (per task) -> group -> print.
    per_task = [(token.upper(), fetch_task_worklogs(config, token))
                for token in arguments['TASK']]

    if arguments['--no-group']:
        groups = [
            build_group(label, worklogs, resolved_users, target_seconds, arguments['--missing-only'])
            for label, worklogs in per_task
        ]
    else:
        combined_label = ', '.join(label for label, _ in per_task)
        combined = [w for _, worklogs in per_task for w in worklogs]
        groups = [build_group(combined_label, combined, resolved_users,
                              target_seconds, arguments['--missing-only'])]

    if arguments['--json']:
        output = {
            'target_seconds': target_seconds,
            'groups': [group_to_json(g, target_seconds) for g in groups],
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        blocks = ["\n".join(render_group_text(g, target_seconds)) for g in groups]
        print("\n\n".join(blocks))

    return 0


if __name__ == '__main__':
    exit(main())
