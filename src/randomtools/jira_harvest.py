"""Sync Jira worklogs to Harvest time entries.

Usage:
    jira-harvest JIRA_PROJECT HARVEST_PROJECT [-w | -d DATE -D DATE] [--users USERS]
    jira-harvest -h | --help
    jira-harvest --version

Arguments:
    JIRA_PROJECT        Jira project key (e.g. PROJ)
    HARVEST_PROJECT     Harvest project name (exact match, case-insensitive)

Options:
    -h --help           Show this message.
    --version           Show version.
    -w --week           Fetch worklogs for current week (Monday to today). This is the default.
    -d DATE             Start date (YYYY-MM-DD).
    -D DATE             End date (YYYY-MM-DD).
    --users USERS       Comma-separated user emails. Defaults to Jira config email.

Configuration:
    Requires ~/.jira/config.ini (Jira credentials) and ~/.harvest/config.ini:

        [Harvest]
        personal_token = your_harvest_personal_access_token
        account_id = your_harvest_account_id

    Issue-to-task mappings are cached in ~/.harvest/mappings/.

Examples:
    jira-harvest PROJ "My Project"
    jira-harvest PROJ "My Project" -w
    jira-harvest PROJ "My Project" -d 2026-03-20 -D 2026-03-27
    jira-harvest PROJ "My Project" --users me@example.com,other@example.com
"""

import json
import datetime
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from docopt import docopt
import requests
from requests.auth import HTTPBasicAuth

from .config.jira import JiraConfigFile
from .config.harvest import HarvestConfigFile
from .jira import extract_text_from_adf

VERSION = '1.0'

MAPPINGS_DIR = Path.home() / '.harvest' / 'mappings'


# --- Harvest API ---

def harvest_headers(config):
    return {
        "Authorization": f"Bearer {config.personal_token}",
        "Harvest-Account-Id": config.account_id,
        "Content-Type": "application/json",
        "User-Agent": "jira-harvest",
    }


def find_harvest_project(config, name):
    """Find a Harvest project by exact name (case-insensitive)."""
    url = "https://api.harvestapp.com/v2/projects"
    headers = harvest_headers(config)
    page = 1

    while True:
        response = requests.get(url, headers=headers, params={"page": page, "per_page": 100, "is_active": "true"})
        response.raise_for_status()
        data = response.json()

        for project in data.get('projects', []):
            if project['name'].lower() == name.lower():
                return project

        if page >= data.get('total_pages', 1):
            break
        page += 1

    return None


def get_task_assignments(config, project_id):
    """Get all active task assignments for a Harvest project."""
    url = f"https://api.harvestapp.com/v2/projects/{project_id}/task_assignments"
    headers = harvest_headers(config)
    tasks = []
    page = 1

    while True:
        response = requests.get(url, headers=headers, params={"page": page, "per_page": 100, "is_active": "true"})
        response.raise_for_status()
        data = response.json()

        for ta in data.get('task_assignments', []):
            tasks.append({
                'id': ta['task']['id'],
                'name': ta['task']['name'],
            })

        if page >= data.get('total_pages', 1):
            break
        page += 1

    return tasks


def get_current_user_id(config):
    """Get the authenticated Harvest user's ID."""
    url = "https://api.harvestapp.com/v2/users/me"
    headers = harvest_headers(config)
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()['id']


def get_existing_entries(config, project_id, from_date, to_date, user_id=None):
    """Get existing Harvest time entries for duplicate detection."""
    url = "https://api.harvestapp.com/v2/time_entries"
    headers = harvest_headers(config)
    entries = []
    page = 1

    while True:
        params = {
            "project_id": project_id,
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
            "page": page,
            "per_page": 100,
        }
        if user_id:
            params["user_id"] = user_id
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

        for entry in data.get('time_entries', []):
            entries.append({
                'id': entry['id'],
                'task_id': entry['task']['id'],
                'task_name': entry['task']['name'],
                'spent_date': entry['spent_date'],
                'hours': entry['hours'],
                'notes': entry.get('notes', ''),
            })

        if page >= data.get('total_pages', 1):
            break
        page += 1

    return entries


def create_time_entry(config, project_id, task_id, spent_date, hours, notes):
    """Create a Harvest time entry."""
    url = "https://api.harvestapp.com/v2/time_entries"
    headers = harvest_headers(config)

    body = {
        "project_id": project_id,
        "task_id": task_id,
        "spent_date": spent_date,
        "hours": hours,
        "notes": notes,
    }

    response = requests.post(url, headers=headers, json=body)
    response.raise_for_status()
    return response.json()


# --- Jira worklog fetching ---

def find_account_id(jira_config, email):
    """Look up a Jira account ID by email address."""
    url = f"{jira_config.base_url}/rest/api/3/user/search"
    auth = HTTPBasicAuth(jira_config.email, jira_config.api_token)
    headers = {"Accept": "application/json"}

    response = requests.get(url, headers=headers, auth=auth, params={"query": email})
    if response.status_code != 200:
        print(f"Failed to look up user {email}. Status: {response.status_code}", file=sys.stderr)
        return None

    users = response.json()
    for user in users:
        if user.get('emailAddress', '').lower() == email.lower():
            return user['accountId']

    if users:
        return users[0]['accountId']

    print(f"Warning: no Jira user found for {email}", file=sys.stderr)
    return None


def find_project_worklogs(jira_config, project, users, start_date, end_date):
    """Find worklogs for a Jira project, filtered by users and date range."""
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')

    # Resolve all users to account IDs (needed for both JQL and client-side filtering)
    account_id_set = set()
    for email in users:
        aid = find_account_id(jira_config, email)
        if aid:
            account_id_set.add(aid)

    if not account_id_set:
        print("Error: could not resolve any user account IDs.", file=sys.stderr)
        return []

    if len(users) == 1 and users[0] == jira_config.email:
        author_clause = "worklogAuthor = currentUser()"
    else:
        quoted = ', '.join(f'"{aid}"' for aid in account_id_set)
        author_clause = f"worklogAuthor in ({quoted})"

    jql = f"project = {project} AND {author_clause} AND worklogDate >= '{start_str}' AND worklogDate <= '{end_str}'"

    url = f"{jira_config.base_url}/rest/api/3/search/jql"
    auth = HTTPBasicAuth(jira_config.email, jira_config.api_token)
    headers = {"Accept": "application/json"}

    all_issues = []
    next_page_token = None

    while True:
        params = {
            "jql": jql,
            "fields": "key,summary",
            "maxResults": 100,
        }
        if next_page_token:
            params["nextPageToken"] = next_page_token

        response = requests.get(url, headers=headers, auth=auth, params=params)

        if response.status_code != 200:
            print(f"Failed to search Jira issues. Status: {response.status_code}", file=sys.stderr)
            print(response.text, file=sys.stderr)
            return []

        data = response.json()

        for issue in data.get('issues', []):
            all_issues.append({
                'key': issue['key'],
                'summary': issue['fields']['summary'],
            })

        next_page_token = data.get('nextPageToken')
        if not next_page_token:
            break

    # Fetch detailed worklogs for each issue
    worklogs = []
    for issue in all_issues:
        issue_worklogs = get_issue_worklogs(
            jira_config, issue['key'], account_id_set, start_date, end_date
        )
        for wl in issue_worklogs:
            wl['issue'] = issue['key']
            wl['summary'] = issue['summary']
            worklogs.append(wl)

    return worklogs


def get_issue_worklogs(jira_config, issue_key, account_id_set, start_date, end_date):
    """Get worklogs for a specific issue, filtered by account IDs and date range."""
    url = f"{jira_config.base_url}/rest/api/3/issue/{issue_key}/worklog"
    auth = HTTPBasicAuth(jira_config.email, jira_config.api_token)
    headers = {"Accept": "application/json"}

    all_worklogs = []
    start_at = 0

    while True:
        params = {"startAt": start_at, "maxResults": 100}
        response = requests.get(url, headers=headers, auth=auth, params=params)

        if response.status_code != 200:
            print(f"Failed to fetch worklogs for {issue_key}. Status: {response.status_code}", file=sys.stderr)
            return []

        data = response.json()

        for worklog in data.get('worklogs', []):
            worklog_date = datetime.datetime.strptime(worklog['started'][:10], '%Y-%m-%d').date()
            author_id = worklog.get('author', {}).get('accountId', '')

            if start_date <= worklog_date <= end_date and author_id in account_id_set:
                comment_text = extract_text_from_adf(worklog.get('comment', ''))
                all_worklogs.append({
                    'timeSpent': worklog['timeSpent'],
                    'timeSpentSeconds': worklog['timeSpentSeconds'],
                    'comment': comment_text,
                    'started': worklog['started'],
                    'date': worklog_date,
                })

        total = data.get('total', 0)
        if start_at + 100 >= total:
            break
        start_at += 100

    return all_worklogs


# --- Mapping cache ---

def load_mappings(harvest_project):
    """Load issue-to-task mappings from cache."""
    MAPPINGS_DIR.mkdir(parents=True, exist_ok=True)
    path = MAPPINGS_DIR / f"{harvest_project}.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def save_mappings(harvest_project, mappings):
    """Save issue-to-task mappings to cache."""
    MAPPINGS_DIR.mkdir(parents=True, exist_ok=True)
    path = MAPPINGS_DIR / f"{harvest_project}.json"
    with open(path, 'w') as f:
        json.dump(mappings, f, indent=2)


def map_issues_to_tasks(worklogs, tasks, mappings):
    """Interactively map unmapped Jira issues to Harvest tasks. Returns updated mappings."""
    # Collect unique issues
    issues = {}
    for wl in worklogs:
        key = wl['issue']
        if key not in issues:
            issues[key] = wl['summary']

    for issue_key, summary in sorted(issues.items()):
        if issue_key in mappings:
            # Verify the mapped task still exists
            task_id = mappings[issue_key]['task_id']
            if any(t['id'] == task_id for t in tasks):
                continue
            print(f"Warning: mapped task for {issue_key} no longer exists, re-mapping.", file=sys.stderr)

        print(f"\n{issue_key}: {summary}")
        print("Select Harvest task:")
        for i, task in enumerate(tasks, 1):
            print(f"  {i}) {task['name']}")

        while True:
            try:
                choice = input("> ").strip()
                idx = int(choice) - 1
                if 0 <= idx < len(tasks):
                    mappings[issue_key] = {
                        'task_id': tasks[idx]['id'],
                        'task_name': tasks[idx]['name'],
                    }
                    break
                print(f"Enter a number between 1 and {len(tasks)}.")
            except (ValueError, EOFError):
                print(f"Enter a number between 1 and {len(tasks)}.")

    return mappings


# --- Duration parsing ---

def format_duration(seconds):
    """Format seconds as human-readable duration (e.g. 1h 30m)."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    return ' '.join(parts) or '0m'


def parse_duration_to_hours(duration_str):
    """Parse a duration string like '1h 30m', '2h', '45m' into decimal hours."""
    duration_str = duration_str.strip()

    # Try combined format: 1h30m or 1h 30m
    match = re.match(r'^(\d+)h\s*(\d+)m$', duration_str)
    if match:
        return int(match.group(1)) + int(match.group(2)) / 60.0

    # Hours only: 2h
    match = re.match(r'^(\d+(?:\.\d+)?)h$', duration_str)
    if match:
        return float(match.group(1))

    # Minutes only: 45m
    match = re.match(r'^(\d+)m$', duration_str)
    if match:
        return int(match.group(1)) / 60.0

    raise ValueError(f"Cannot parse duration: '{duration_str}'")


# --- Vim template ---

def generate_template(worklogs_by_task, existing_entries):
    """Generate the Vim-editable template grouped by Harvest task."""
    lines = []

    # Index existing entries by (task_name, date, notes_fragment) for display
    existing_by_task = {}
    for entry in existing_entries:
        task_name = entry['task_name']
        existing_by_task.setdefault(task_name, []).append(entry)

    for task_name in sorted(worklogs_by_task.keys()):
        task_worklogs = worklogs_by_task.get(task_name, [])
        if not task_worklogs:
            continue

        lines.append(f"# {task_name}")
        lines.append("")

        for wl in sorted(task_worklogs, key=lambda w: (w['date'], w['issue'])):
            date_str = wl['date'].isoformat()
            duration = format_duration(wl['timeSpentSeconds'])
            comment = wl['comment'] or wl['summary']
            lines.append(f"- [{date_str}] ({duration}) {wl['issue']}: {comment}")

        # Already logged entries for this task
        task_existing = existing_by_task.get(task_name, [])
        if task_existing:
            lines.append("")
            lines.append("## Already logged")
            for entry in sorted(task_existing, key=lambda e: e['spent_date']):
                hours_display = format_hours_as_duration(entry['hours'])
                notes = entry.get('notes', '')
                lines.append(f"# - [{entry['spent_date']}] ({hours_display}) {notes}")

        lines.append("")

    return '\n'.join(lines)


def format_hours_as_duration(hours):
    """Convert decimal hours to display format (e.g. 1.5 -> 1h 30m)."""
    total_minutes = round(hours * 60)
    h = total_minutes // 60
    m = total_minutes % 60
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    return ' '.join(parts) or '0m'


def parse_template(content, tasks_by_name):
    """Parse the edited template back into time entries to create.

    Returns list of dicts: {task_id, task_name, spent_date, hours, notes}
    """
    entries = []
    current_task = None
    in_already_logged = False

    line_re = re.compile(r'^- \[(\d{4}-\d{2}-\d{2})\] \(([^)]+)\) (.+)$')

    for line in content.splitlines():
        line = line.rstrip()

        # Task heading
        if line.startswith('# ') and not line.startswith('# -'):
            heading = line[2:].strip()
            if heading == 'Already logged' or heading.startswith('Already logged'):
                continue
            current_task = heading
            in_already_logged = False
            continue

        # Already logged section
        if line.startswith('## Already logged'):
            in_already_logged = True
            continue

        # Skip commented lines
        if line.startswith('#'):
            continue

        # Empty line resets already-logged section on new task
        if not line.strip():
            continue

        if in_already_logged:
            continue

        match = line_re.match(line)
        if match and current_task:
            date_str, duration_str, notes = match.groups()

            if current_task not in tasks_by_name:
                print(f"Warning: unknown task '{current_task}', skipping entry.", file=sys.stderr)
                continue

            try:
                hours = parse_duration_to_hours(duration_str)
            except ValueError as e:
                print(f"Warning: {e}, skipping entry.", file=sys.stderr)
                continue

            entries.append({
                'task_id': tasks_by_name[current_task],
                'task_name': current_task,
                'spent_date': date_str,
                'hours': hours,
                'notes': notes,
            })

    return entries


def open_in_editor(content):
    """Write content to a temp file, open in Vim, return edited content."""
    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.md', delete=False, prefix='jira-harvest-'
    ) as f:
        f.write(content)
        tmppath = f.name

    try:
        result = subprocess.run(['vim', tmppath])
        if result.returncode != 0:
            raise Exception("Editor exited with non-zero status")
        with open(tmppath) as f:
            return f.read()
    finally:
        Path(tmppath).unlink(missing_ok=True)


# --- Dedup ---

def filter_new_worklogs(worklogs_by_task, existing_entries):
    """Remove worklogs that already have matching Harvest entries.

    Match by: date, task, and issue key prefix in notes.
    """
    existing_keys = set()
    for entry in existing_entries:
        # Extract issue key from notes if present (e.g. "PROJ-123: ...")
        notes = entry.get('notes', '')
        issue_match = re.match(r'^([A-Z]+-\d+)', notes)
        issue_key = issue_match.group(1) if issue_match else None
        existing_keys.add((entry['spent_date'], entry['task_id'], issue_key))

    filtered = {}
    for task_name, worklogs in worklogs_by_task.items():
        new_worklogs = []
        for wl in worklogs:
            issue_key = wl['issue']
            date_str = wl['date'].isoformat()
            task_id = wl.get('_task_id')
            key = (date_str, task_id, issue_key)
            if key not in existing_keys:
                new_worklogs.append(wl)
        if new_worklogs:
            filtered[task_name] = new_worklogs

    return filtered


# --- Main ---

def main():
    arguments = docopt(__doc__, version=VERSION)

    jira_config = JiraConfigFile()
    harvest_config = HarvestConfigFile()

    jira_project = arguments['JIRA_PROJECT']
    harvest_project_name = arguments['HARVEST_PROJECT']

    # Determine date range
    if arguments['-d'] and arguments['-D']:
        start_date = datetime.date.fromisoformat(arguments['-d'])
        end_date = datetime.date.fromisoformat(arguments['-D'])
    else:
        # Default: current week (Monday to Sunday)
        today = datetime.date.today()
        start_date = today - datetime.timedelta(days=today.weekday())
        end_date = start_date + datetime.timedelta(days=6)

    # Determine users
    if arguments['--users']:
        users = [u.strip() for u in arguments['--users'].split(',')]
    else:
        users = [jira_config.email]

    print(f"Period: {start_date} to {end_date}")
    print(f"Users: {', '.join(users)}")

    # Step 1: Find Harvest project
    print(f"\nLooking up Harvest project '{harvest_project_name}'...")
    harvest_project = find_harvest_project(harvest_config, harvest_project_name)
    if not harvest_project:
        print(f"Error: Harvest project '{harvest_project_name}' not found.", file=sys.stderr)
        sys.exit(1)

    project_id = harvest_project['id']
    print(f"Found: {harvest_project['name']} (id: {project_id})")

    # Step 2: Get Harvest tasks
    tasks = get_task_assignments(harvest_config, project_id)
    if not tasks:
        print("Error: No active tasks found for this Harvest project.", file=sys.stderr)
        sys.exit(1)

    tasks_by_name = {t['name']: t['id'] for t in tasks}

    # Step 3: Fetch Jira worklogs
    print(f"\nFetching Jira worklogs for {jira_project}...")
    worklogs = find_project_worklogs(jira_config, jira_project, users, start_date, end_date)
    if not worklogs:
        print("No worklogs found for the given period.")
        return

    print(f"Found {len(worklogs)} worklog(s) across {len(set(w['issue'] for w in worklogs))} issue(s).")

    # Step 4: Map issues to Harvest tasks
    mappings = load_mappings(harvest_project_name)
    mappings = map_issues_to_tasks(worklogs, tasks, mappings)
    save_mappings(harvest_project_name, mappings)

    # Group worklogs by Harvest task
    worklogs_by_task = {}
    for wl in worklogs:
        mapping = mappings.get(wl['issue'])
        if not mapping:
            print(f"Warning: no mapping for {wl['issue']}, skipping.", file=sys.stderr)
            continue
        task_name = mapping['task_name']
        wl['_task_id'] = mapping['task_id']
        worklogs_by_task.setdefault(task_name, []).append(wl)

    # Step 5: Detect existing entries
    print("\nChecking for existing Harvest entries...")
    harvest_user_id = get_current_user_id(harvest_config)
    existing_entries = get_existing_entries(harvest_config, project_id, start_date, end_date, user_id=harvest_user_id)

    # Filter out already-logged worklogs
    new_worklogs_by_task = filter_new_worklogs(worklogs_by_task, existing_entries)

    if not new_worklogs_by_task and not existing_entries:
        print("Nothing to log.")
        return

    if not new_worklogs_by_task:
        print("All worklogs are already logged on Harvest.")
        return

    skipped = sum(len(wls) for wls in worklogs_by_task.values()) - sum(len(wls) for wls in new_worklogs_by_task.values())
    if skipped:
        print(f"Skipping {skipped} already-logged worklog(s).")

    # Step 6: Generate template
    template = generate_template(new_worklogs_by_task, existing_entries)

    # Step 7: Open in Vim
    edited = open_in_editor(template)

    # Step 8: Parse edited template
    entries = parse_template(edited, tasks_by_name)

    if not entries:
        print("No entries to log.")
        return

    # Step 9: Log to Harvest
    print(f"\nLogging {len(entries)} entry/entries to Harvest...")
    success = 0
    for entry in entries:
        try:
            create_time_entry(
                harvest_config,
                project_id,
                entry['task_id'],
                entry['spent_date'],
                entry['hours'],
                entry['notes'],
            )
            print(f"  OK: [{entry['spent_date']}] {entry['hours']:.2f}h - {entry['task_name']}: {entry['notes']}")
            success += 1
        except requests.exceptions.HTTPError as e:
            print(f"  FAIL: [{entry['spent_date']}] {entry['notes']}: {e}", file=sys.stderr)

    print(f"\nDone. {success}/{len(entries)} entries logged successfully.")
