"""Check discrepancies between Jira worklogs and Harvest time entries.

Usage:
    jira-harvest-check JIRA_PROJECT HARVEST_PROJECT [-w [-Y] | -m [-Y] | -d DATE -D DATE] [--users USERS | --all-jira-users] [--exact]
    jira-harvest-check -h | --help
    jira-harvest-check --version

Arguments:
    JIRA_PROJECT        Jira project key (e.g. PROJ)
    HARVEST_PROJECT     Harvest project name (exact match, case-insensitive)

Options:
    -h --help           Show this message.
    --version           Show version.
    -w --week           Fetch for current week (Monday to Sunday). This is the default.
    -m --month          Fetch for current month (1st to last day).
    -Y --last           Use the previous period (last week with -w, last month with -m).
    -d DATE             Start date (YYYY-MM-DD).
    -D DATE             End date (YYYY-MM-DD).
    --users USERS       Comma-separated user emails. Defaults to Jira config email.
    --all-jira-users    Discover all users with worklogs in the Jira project for the period.
    --exact             Show all day-level discrepancies, even if the total balances out.

Configuration:
    Requires ~/.jira/config.ini (Jira credentials) and ~/.harvest/config.ini.

Examples:
    jira-harvest-check PROJ "My Project"
    jira-harvest-check PROJ "My Project" --all-jira-users
    jira-harvest-check PROJ "My Project" -d 2026-03-20 -D 2026-03-27
    jira-harvest-check PROJ "My Project" --users me@example.com,other@example.com
"""

import datetime
import sys
from collections import defaultdict

from docopt import docopt
import requests
from requests.auth import HTTPBasicAuth

from .config.jira import JiraConfigFile
from .config.harvest import HarvestConfigFile
from whosename import name_of

from .jira_harvest import (
    harvest_headers,
    find_harvest_project,
    find_project_worklogs,
    format_hours_as_duration,
)

VERSION = '1.0'


def find_all_worklog_authors(jira_config, project, start_date, end_date):
    """Find all unique account IDs that have worklogs in a project/date range."""
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')

    jql = f"project = {project} AND worklogDate >= '{start_str}' AND worklogDate <= '{end_str}'"

    url = f"{jira_config.base_url}/rest/api/3/search/jql"
    auth = HTTPBasicAuth(jira_config.email, jira_config.api_token)
    headers = {"Accept": "application/json"}

    issue_keys = []
    next_page_token = None

    while True:
        params = {"jql": jql, "fields": "key", "maxResults": 100}
        if next_page_token:
            params["nextPageToken"] = next_page_token

        response = requests.get(url, headers=headers, auth=auth, params=params)
        if response.status_code != 200:
            print(f"Failed to search Jira issues. Status: {response.status_code}", file=sys.stderr)
            return set()

        data = response.json()
        for issue in data.get('issues', []):
            issue_keys.append(issue['key'])

        next_page_token = data.get('nextPageToken')
        if not next_page_token:
            break

    account_ids = set()
    for issue_key in issue_keys:
        wl_url = f"{jira_config.base_url}/rest/api/3/issue/{issue_key}/worklog"
        start_at = 0

        while True:
            params = {"startAt": start_at, "maxResults": 100}
            response = requests.get(wl_url, headers=headers, auth=auth, params=params)
            if response.status_code != 200:
                break

            data = response.json()
            for worklog in data.get('worklogs', []):
                worklog_date = datetime.datetime.strptime(worklog['started'][:10], '%Y-%m-%d').date()
                if start_date <= worklog_date <= end_date:
                    aid = worklog.get('author', {}).get('accountId')
                    if aid:
                        account_ids.add(aid)

            if start_at + 100 >= data.get('total', 0):
                break
            start_at += 100

    return account_ids


def get_jira_user_by_account_id(jira_config, account_id):
    """Look up a Jira user's display name by account ID."""
    url = f"{jira_config.base_url}/rest/api/3/user"
    auth = HTTPBasicAuth(jira_config.email, jira_config.api_token)
    headers = {"Accept": "application/json"}

    response = requests.get(url, headers=headers, auth=auth, params={"accountId": account_id})
    if response.status_code != 200:
        return None

    return response.json().get('displayName')


def get_jira_user_info(jira_config, email):
    """Look up Jira user by email, return (account_id, display_name)."""
    url = f"{jira_config.base_url}/rest/api/3/user/search"
    auth = HTTPBasicAuth(jira_config.email, jira_config.api_token)
    headers = {"Accept": "application/json"}

    response = requests.get(url, headers=headers, auth=auth, params={"query": email})
    if response.status_code != 200:
        return None, None

    users = response.json()
    for user in users:
        if user.get('emailAddress', '').lower() == email.lower():
            return user['accountId'], user.get('displayName', email)

    if users:
        return users[0]['accountId'], users[0].get('displayName', email)

    return None, None


def get_all_harvest_entries_by_user(config, project_id, from_date, to_date):
    """Fetch all time entries for a project, grouped by user name.

    Returns: {user_name: {'user_id': id, 'hours_by_day': {date: hours}, 'count_by_day': {date: count}}}
    """
    url = "https://api.harvestapp.com/v2/time_entries"
    headers = harvest_headers(config)
    users = {}
    page = 1

    while True:
        params = {
            "project_id": project_id,
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
            "page": page,
            "per_page": 100,
        }
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

        for entry in data.get('time_entries', []):
            user_name = entry['user']['name']
            user_id = entry['user']['id']

            if user_name not in users:
                users[user_name] = {'user_id': user_id, 'hours_by_day': defaultdict(float), 'count_by_day': defaultdict(int)}

            date = datetime.date.fromisoformat(entry['spent_date'])
            users[user_name]['hours_by_day'][date] += entry['hours']
            users[user_name]['count_by_day'][date] += 1

        if page >= data.get('total_pages', 1):
            break
        page += 1

    return users


def find_harvest_user_by_id(harvest_users, harvest_id):
    """Find a Harvest user by ID in the harvest_users dict.

    Returns (harvest_user_name, harvest_user_data) or (None, None).
    """
    for name, data in harvest_users.items():
        if data['user_id'] == harvest_id:
            return name, data

    return None, None


def main():
    arguments = docopt(__doc__, version=VERSION)

    jira_config = JiraConfigFile()
    harvest_config = HarvestConfigFile()

    jira_project = arguments['JIRA_PROJECT']
    harvest_project_name = arguments['HARVEST_PROJECT']
    exact = arguments['--exact']

    # Determine date range
    if arguments['-d'] and arguments['-D']:
        start_date = datetime.date.fromisoformat(arguments['-d'])
        end_date = datetime.date.fromisoformat(arguments['-D'])
    elif arguments['--month']:
        import calendar
        today = datetime.date.today()
        if arguments['--last']:
            first = today.replace(day=1) - datetime.timedelta(days=1)
            start_date = first.replace(day=1)
            end_date = first
        else:
            start_date = today.replace(day=1)
            end_date = today.replace(day=calendar.monthrange(today.year, today.month)[1])
    else:
        today = datetime.date.today()
        start_date = today - datetime.timedelta(days=today.weekday())
        end_date = start_date + datetime.timedelta(days=6)
        if arguments['--last']:
            start_date -= datetime.timedelta(weeks=1)
            end_date -= datetime.timedelta(weeks=1)

    # Determine users — build list of (account_id, display_name)
    if arguments['--all-jira-users']:
        print(f"Discovering all worklog authors in {jira_project}...")
        account_ids = find_all_worklog_authors(jira_config, jira_project, start_date, end_date)
        user_infos = []
        for aid in account_ids:
            display_name = get_jira_user_by_account_id(jira_config, aid)
            if display_name:
                user_infos.append((aid, display_name))
            else:
                print(f"Warning: could not resolve display name for account {aid}, skipping.", file=sys.stderr)
        if not user_infos:
            print("No users found with worklogs in the given period.")
            return
        print(f"Found {len(user_infos)} user(s): {', '.join(sorted(name for _, name in user_infos))}")
    elif arguments['--users']:
        emails = [u.strip() for u in arguments['--users'].split(',')]
        user_infos = []
        for email in emails:
            account_id, display_name = get_jira_user_info(jira_config, email)
            if account_id:
                user_infos.append((account_id, display_name))
            else:
                print(f"Warning: could not resolve Jira user for {email}, skipping.", file=sys.stderr)
        if not user_infos:
            print("No valid users found.")
            return
    else:
        account_id, display_name = get_jira_user_info(jira_config, jira_config.email)
        if not account_id:
            print(f"Error: could not resolve Jira user for {jira_config.email}.", file=sys.stderr)
            sys.exit(1)
        user_infos = [(account_id, display_name)]

    # Find Harvest project
    harvest_project = find_harvest_project(harvest_config, harvest_project_name)
    if not harvest_project:
        print(f"Error: Harvest project '{harvest_project_name}' not found.", file=sys.stderr)
        sys.exit(1)

    project_id = harvest_project['id']

    # Fetch all Harvest entries once, grouped by user name
    harvest_by_user = get_all_harvest_entries_by_user(harvest_config, project_id, start_date, end_date)

    # Group Jira users by Harvest ID
    harvest_groups = defaultdict(list)  # harvest_id -> [(account_id, display_name)]
    for account_id, jira_display_name in user_infos:
        try:
            harvest_id = int(name_of(account_id, 'jira', 'harvest'))
        except Exception:
            print(f"Warning: no Harvest ID mapping for '{jira_display_name}', skipping.", file=sys.stderr)
            continue
        harvest_groups[harvest_id].append((account_id, jira_display_name))

    for harvest_id, jira_users in harvest_groups.items():
        # --- Jira side (aggregate all mapped accounts) ---
        all_account_ids = [aid for aid, _ in jira_users]
        jira_worklogs = find_project_worklogs(jira_config, jira_project, [], start_date, end_date, account_ids=all_account_ids)

        jira_by_day = defaultdict(float)
        jira_count_by_day = defaultdict(int)
        for wl in jira_worklogs:
            jira_by_day[wl['date']] += wl['timeSpentSeconds'] / 3600.0
            jira_count_by_day[wl['date']] += 1

        # --- Harvest side ---
        harvest_name, harvest_data = find_harvest_user_by_id(harvest_by_user, harvest_id)
        if not harvest_data:
            if jira_by_day:
                names = ', '.join(name for _, name in jira_users)
                print(f"Warning: no Harvest entries for '{names}' (ID {harvest_id}), skipping.", file=sys.stderr)
            continue

        harvest_by_day = dict(harvest_data['hours_by_day'])
        harvest_count_by_day = dict(harvest_data['count_by_day'])
        user_name = harvest_name

        # --- Compare ---
        all_days = sorted(set(jira_by_day.keys()) | set(harvest_by_day.keys()))

        mismatches = []
        total_jira = 0.0
        total_harvest = 0.0

        for day in all_days:
            jira_hours = jira_by_day.get(day, 0.0)
            harvest_hours = harvest_by_day.get(day, 0.0)
            total_jira += jira_hours
            total_harvest += harvest_hours

            if round(jira_hours, 2) != round(harvest_hours, 2):
                jira_count = jira_count_by_day.get(day, 0)
                harvest_count = harvest_count_by_day.get(day, 0)
                mismatches.append((day, harvest_hours, harvest_count, jira_hours, jira_count))

        total_diff = total_jira - total_harvest

        if mismatches and (exact or round(total_diff, 2) != 0):
            if round(total_diff, 2) == 0:
                diff_str = "(Neutral)"
            else:
                sign = '+' if total_diff > 0 else '-'
                diff_str = f"{sign}{format_hours_as_duration(abs(total_diff))}"
            j_total = format_hours_as_duration(total_jira)
            h_total = format_hours_as_duration(total_harvest)
            print(f"\033[1m{user_name}\033[0m (Jira/Harvest: {j_total}/{h_total}; Diff: {diff_str})")
            for day, harvest_hours, harvest_count, jira_hours, jira_count in mismatches:
                weekday = day.strftime('%A')
                h_str = format_hours_as_duration(harvest_hours)
                j_str = format_hours_as_duration(jira_hours)
                diff = jira_hours - harvest_hours
                sign = '+' if diff > 0 else '-'
                d_str = f"{sign}{format_hours_as_duration(abs(diff))}"
                print(f"- {weekday} {day.isoformat()}: Jira/Harvest: {j_str}/{h_str}; Worklogs: {jira_count}/{harvest_count}; Diff: {d_str}")
            print()
