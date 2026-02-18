"""Jira worklog management tool with shell-like interface.

Usage:
    jira [options]

Options:
    -h, --help       Show this message.
    --version        Show version information.
    -l, --list       Print worklogs and exit.
    -Y, --yesterday  With -l, show yesterday's worklogs.
    --date DATE      With -l, show worklogs for DATE (YYYY-MM-DD or relative).

Commands in shell:
    list                     - Show current day's worklogs and saved issues
    save ISSUE              - Add issue to saved list
    exclude ISSUE           - Add issue to excluded list
    remove ISSUE            - Remove issue from both saved and excluded lists
    create PROJECT DESC     - Create new issue in project
    update [DAYS]           - Refresh issues cache (defaults to 7 days)
    calendar ARGS           - Create calendar event (calls jira-calendar with args)
    set DATE                - Set working date (YYYY-MM-DD, 'Mon', '3 days ago')
    reset                   - Reset to today's date
    help                    - Show this help
    
Issue logging:
    ISSUE TIME [DESC]       - Log time to issue (e.g., "ABC-123 2h" or "DEV-456 1.5h Fixed login bug")
    
Quit by pressing Ctrl+D or Ctrl+C.
"""

import json
import os
import datetime
import re
import subprocess
from pathlib import Path
from collections.abc import Iterable

from docopt import docopt
import requests
from requests.auth import HTTPBasicAuth
from more_itertools import repeatfunc, consume
import shlex
import sys
import dateparser

try:
    import readline
    READLINE_AVAILABLE = True
except ImportError:
    READLINE_AVAILABLE = False

from .config.jira import JiraConfigFile

VERSION = '1.0'

# Storage paths
CACHE_DIR = Path.home() / '.jira' / 'cache'
SAVED_ISSUES_FILE = CACHE_DIR / 'saved_issues.json'
EXCLUDED_ISSUES_FILE = CACHE_DIR / 'excluded_issues.json'
RECENT_ISSUES_FILE = CACHE_DIR / 'recent_issues.json'
HISTORY_FILE = CACHE_DIR / 'history'

# Global variable to track current working date
current_date = None

# Track time of last worklog entry
last_worklog_time = None

def ensure_cache_dir():
    """Ensure cache directory exists."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

def setup_readline():
    """Setup readline with history file."""
    if not READLINE_AVAILABLE:
        return
    
    ensure_cache_dir()
    
    # Set up history file
    history_file = str(HISTORY_FILE)
    
    try:
        # Load existing history
        readline.read_history_file(history_file)
    except FileNotFoundError:
        # History file doesn't exist yet, that's okay
        pass
    except Exception:
        # Other errors reading history, continue without it
        pass
    
    # Set maximum history size
    readline.set_history_length(1000)
    
    # Save history on exit
    import atexit
    atexit.register(save_readline_history, history_file)

def save_readline_history(history_file):
    """Save readline history to file."""
    if not READLINE_AVAILABLE:
        return
    
    try:
        readline.write_history_file(history_file)
    except Exception:
        # Ignore errors when saving history
        pass

def load_json_set(file_path):
    """Load a set from JSON file."""
    if file_path.exists():
        try:
            with open(file_path, 'r') as f:
                return set(json.load(f))
        except (json.JSONDecodeError, FileNotFoundError):
            return set()
    return set()

def save_json_set(file_path, data_set):
    """Save a set to JSON file."""
    ensure_cache_dir()
    with open(file_path, 'w') as f:
        json.dump(list(data_set), f, indent=2)

def get_input_until(predicate, prompt=None):
    text = None
    
    while text is None or not predicate(text):
        text = input(prompt)
    
    return text


HELP = """
Available commands:
{commands}

Issue logging format:
  ISSUE TIME - Log time to issue (e.g., "ABC-123 2h", "DEV-456 1.5h")

Quit by pressing Ctrl+D or Ctrl+C.
"""

def list_to_points(lst):
    """Convert list to bullet points."""
    return "\n".join([f"  {item}" for item in lst])

def help_command(*args):
    """Show help message."""
    print(HELP.format(commands=list_to_points(commands.keys())))

def find_issues_with_worklogs_in_period(config, start_date, end_date):
    """Find issues that have worklogs by the current user in the specified date range."""
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')

    # JQL to find issues where current user has logged work in the date range
    jql = f"worklogAuthor = currentUser() AND worklogDate >= '{start_str}' AND worklogDate <= '{end_str}'"

    url = f"{config.base_url}/rest/api/3/search/jql"
    auth = HTTPBasicAuth(config.email, config.api_token)
    headers = {"Accept": "application/json"}

    all_issues = []
    next_page_token = None
    max_results = 100

    try:
        while True:
            params = {
                "jql": jql,
                "fields": "key,summary",
                "maxResults": max_results
            }

            if next_page_token:
                params["nextPageToken"] = next_page_token

            response = requests.get(url, headers=headers, auth=auth, params=params)

            if response.status_code == 200:
                data = response.json()

                for issue in data.get('issues', []):
                    all_issues.append({
                        'key': issue['key'],
                        'summary': issue['fields']['summary']
                    })

                # Check if we have more results using nextPageToken
                next_page_token = data.get('nextPageToken')
                if not next_page_token:
                    break
            else:
                print(f"Failed to search for issues. Status: {response.status_code}")
                return []

        return all_issues

    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Jira API: {e}")
        return []

def get_issue_worklogs_in_period(config, issue_key, start_date, end_date):
    """Get worklogs for a specific issue in the specified date range."""
    url = f"{config.base_url}/rest/api/3/issue/{issue_key}/worklog"
    auth = HTTPBasicAuth(config.email, config.api_token)
    headers = {"Accept": "application/json"}
    
    all_worklogs = []
    start_at = 0
    max_results = 100
    
    try:
        while True:
            params = {
                "startAt": start_at,
                "maxResults": max_results
            }
            
            response = requests.get(url, headers=headers, auth=auth, params=params)
            
            if response.status_code == 200:
                data = response.json()
                
                for worklog in data.get('worklogs', []):
                    worklog_date = datetime.datetime.strptime(worklog['started'][:10], '%Y-%m-%d').date()
                    
                    # Filter by date range and current user
                    if (start_date <= worklog_date <= end_date and 
                        worklog.get('author', {}).get('emailAddress') == config.email):
                        
                        # Extract comment text from ADF format
                        comment_text = extract_text_from_adf(worklog.get('comment', ''))
                        
                        all_worklogs.append({
                            'timeSpent': worklog['timeSpent'],
                            'timeSpentSeconds': worklog['timeSpentSeconds'],
                            'comment': comment_text,
                            'started': worklog['started'],
                            'date': worklog_date
                        })
                
                # Check if we have more results
                total = data.get('total', 0)
                if start_at + max_results >= total:
                    break
                
                start_at += max_results
            else:
                print(f"Failed to fetch worklogs for {issue_key}. Status: {response.status_code}")
                return []
        
        return all_worklogs
            
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Jira API: {e}")
        return []

def get_timelogs_for_time_period(config, start_date, end_date):
    """Get worklogs for a specific time period."""
    # First, find all issues with worklogs in the period
    issues = find_issues_with_worklogs_in_period(config, start_date, end_date)
    
    worklogs = []
    
    # Then, get detailed worklogs for each issue
    for issue in issues:
        issue_worklogs = get_issue_worklogs_in_period(config, issue['key'], start_date, end_date)
        
        # Add issue info to each worklog
        for worklog in issue_worklogs:
            worklog.update({
                'issue': issue['key'],
                'summary': issue['summary']
            })
            worklogs.append(worklog)
    
    return worklogs

def get_daily_worklogs(config, date=None):
    """Get worklogs for a specific date (defaults to working date)."""
    if date is None:
        date = get_working_date()
    
    return get_timelogs_for_time_period(config, date, date)

def get_weekly_worklogs(config, start_date=None):
    """Get worklogs for a week (defaults to current week)."""
    if start_date is None:
        today = datetime.date.today()
        # Get Monday of current week
        start_date = today - datetime.timedelta(days=today.weekday())
    
    end_date = start_date + datetime.timedelta(days=6)
    return get_timelogs_for_time_period(config, start_date, end_date)

def load_cached_issues():
    """Load cached recent issues from file."""
    if not RECENT_ISSUES_FILE.exists():
        return None
    
    try:
        with open(RECENT_ISSUES_FILE, 'r') as f:
            cache_data = json.load(f)
        return cache_data
    except (json.JSONDecodeError, FileNotFoundError):
        return None

def extract_text_from_adf(adf_content):
    """Extract plain text from Atlassian Document Format.
    
    Args:
        adf_content: Can be a string (already plain text) or dict (ADF structure)
    
    Returns:
        str: Plain text content
    """
    if not adf_content:
        return ""
    
    # If it's already a string, return as-is
    if isinstance(adf_content, str):
        return adf_content
    
    # If it's not a dict, convert to string
    if not isinstance(adf_content, dict):
        return str(adf_content)
    
    # Handle ADF structure
    text_parts = []
    
    def extract_text_recursive(content):
        if isinstance(content, dict):
            if content.get('type') == 'text':
                text_parts.append(content.get('text', ''))
            elif 'content' in content:
                for item in content['content']:
                    extract_text_recursive(item)
        elif isinstance(content, list):
            for item in content:
                extract_text_recursive(item)
    
    extract_text_recursive(adf_content)
    return ' '.join(text_parts).strip()

def get_issue_details(config, issue_keys):
    """Get issue details (summary, description) for a list of issue keys."""
    if not issue_keys:
        return {}

    # Convert to list if it's a set
    if isinstance(issue_keys, set):
        issue_keys = list(issue_keys)

    # Build JQL to get multiple issues
    issue_list = ",".join(issue_keys)
    jql = f"key in ({issue_list})"

    url = f"{config.base_url}/rest/api/3/search/jql"
    auth = HTTPBasicAuth(config.email, config.api_token)
    headers = {"Accept": "application/json"}

    params = {
        "jql": jql,
        "fields": "key,summary,description",
        "maxResults": len(issue_keys)
    }

    try:
        response = requests.get(url, headers=headers, auth=auth, params=params)

        if response.status_code == 200:
            data = response.json()
            issue_details = {}

            for issue in data.get('issues', []):
                issue_key = issue['key']
                summary = issue['fields']['summary']

                # Extract description text from Atlassian Document Format
                description = extract_text_from_adf(issue['fields'].get('description', ''))

                issue_details[issue_key] = {
                    'summary': summary,
                    'description': description
                }

            return issue_details
        else:
            print(f"Failed to fetch issue details. Status: {response.status_code}")
            return {}

    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Jira API: {e}")
        return {}

def list_worklogs(args, config):
    """List current day's worklogs and saved issues."""
    # Show current working date context
    working_date = get_working_date()
    today = datetime.date.today()
    
    if working_date != today:
        if working_date == today - datetime.timedelta(days=1):
            date_context = f" (working date: yesterday, {working_date.strftime('%Y-%m-%d')})"
        else:
            days_diff = (today - working_date).days
            if days_diff > 0:
                date_context = f" (working date: {days_diff} day{'s' if days_diff != 1 else ''} ago, {working_date.strftime('%Y-%m-%d')})"
            else:
                date_context = f" (working date: in {abs(days_diff)} day{'s' if abs(days_diff) != 1 else ''}, {working_date.strftime('%Y-%m-%d')})"
    else:
        date_context = ""
    
    # Parse arguments for date options
    if args and args[0] == 'week':
        print("Weekly worklogs:")
        weekly_worklogs = get_weekly_worklogs(config)
        
        if weekly_worklogs:
            # Group by date
            worklogs_by_date = {}
            for worklog in weekly_worklogs:
                date_str = worklog['date'].strftime('%Y-%m-%d')
                if date_str not in worklogs_by_date:
                    worklogs_by_date[date_str] = []
                worklogs_by_date[date_str].append(worklog)
            
            total_seconds = 0
            for date_str in sorted(worklogs_by_date.keys()):
                date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                day_name = date_obj.strftime('%A')
                print(f"\n{day_name}, {date_str}:")
                
                day_total = 0
                for worklog in worklogs_by_date[date_str]:
                    line = f"  \033[1m{worklog['issue']}\033[0m: {worklog['timeSpent']} - {worklog['summary']}"
                    if worklog['comment']:
                        line += f" – {worklog['comment']}"
                    print(line)
                    day_total += worklog['timeSpentSeconds']
                    total_seconds += worklog['timeSpentSeconds']
                
                print(f"  Day total: {day_total // 3600}h {(day_total % 3600) // 60}m")
            
            print(f"\nWeek total: {total_seconds // 3600}h {(total_seconds % 3600) // 60}m")
        else:
            print("  No worklogs found for this week")
    else:
        print(f"Today's worklogs{date_context}:")
        daily_worklogs = get_daily_worklogs(config, working_date)
        
        if daily_worklogs:
            total_seconds = 0
            for worklog in daily_worklogs:
                line = f"  \033[1m{worklog['issue']}\033[0m: {worklog['timeSpent']} - {worklog['summary']}"
                if worklog['comment']:
                    line += f" – {worklog['comment']}"
                print(line)
                total_seconds += worklog['timeSpentSeconds']
            
            print(f"  Total: {total_seconds // 3600}h {(total_seconds % 3600) // 60}m")
        else:
            print("  No worklogs found for today")
    
    # Combine saved issues and cached issues, sorted alphabetically
    saved_issues = load_json_set(SAVED_ISSUES_FILE)
    excluded_issues = load_json_set(EXCLUDED_ISSUES_FILE)
    cached_data = load_cached_issues()
    
    # Build a combined list of all available issues
    all_issues = {}  # key -> {summary, description, source}
    
    # Add saved issues
    for issue_key in saved_issues:
        all_issues[issue_key] = {'source': 'saved'}
    
    # Add cached issues (excluding those already saved or excluded)
    if cached_data and cached_data.get('issues'):
        for issue_data in cached_data['issues']:
            issue_key = issue_data['key']
            if issue_key not in saved_issues and issue_key not in excluded_issues:
                all_issues[issue_key] = {
                    'summary': issue_data['summary'],
                    'description': issue_data.get('description', ''),
                    'source': 'cached'
                }
    
    if all_issues:
        # Get details for saved issues (cached issues already have details)
        saved_issue_keys = [k for k, v in all_issues.items() if v['source'] == 'saved']
        if saved_issue_keys:
            issue_details = get_issue_details(config, saved_issue_keys)
            for issue_key in saved_issue_keys:
                if issue_key in issue_details:
                    all_issues[issue_key].update(issue_details[issue_key])
        
        print("\nAvailable issues:")
        
        # Sort alphabetically and display
        for issue_key in sorted(all_issues.keys()):
            issue_info = all_issues[issue_key]
            source_indicator = "*" if issue_info['source'] == 'saved' else ""
            
            if 'summary' in issue_info:
                print(f"  \033[1m{issue_key}\033[0m: {issue_info['summary']} {source_indicator}")
            else:
                print(f"  \033[1m{issue_key}\033[0m (details not available) {source_indicator}")
        
        # Show cache info if we have cached items
        cached_count = sum(1 for v in all_issues.values() if v['source'] == 'cached')
        if cached_count > 0 and cached_data:
            updated_time = cached_data.get('updated', 'unknown')
            days = cached_data.get('days', 7)
            
            # Parse and format the update time
            try:
                updated_dt = datetime.datetime.fromisoformat(updated_time.replace('Z', '+00:00'))
                time_str = updated_dt.strftime('%Y-%m-%d %H:%M')
            except:
                time_str = updated_time
            
            print(f"\nCache info: {cached_count} recent issues from last {days} days (updated {time_str})")
            print("Use 'save ISSUE' to save or 'exclude ISSUE' to hide. Run 'update' to refresh.")
    
    # Show excluded issues separately
    if excluded_issues:
        print("\nExcluded issues:")
        issue_details = get_issue_details(config, excluded_issues)
        
        for issue in sorted(excluded_issues):
            if issue in issue_details:
                details = issue_details[issue]
                print(f"  \033[1m{issue}\033[0m: {details['summary']}")
            else:
                print(f"  \033[1m{issue}\033[0m (details not available)")

def save_issue(args, config):
    """Add issue to saved list."""
    if not args:
        print("Usage: save ISSUE")
        return
    
    issue = args[0].upper()
    saved_issues = load_json_set(SAVED_ISSUES_FILE)
    excluded_issues = load_json_set(EXCLUDED_ISSUES_FILE)
    
    # Remove from excluded if present
    if issue in excluded_issues:
        excluded_issues.remove(issue)
        save_json_set(EXCLUDED_ISSUES_FILE, excluded_issues)
        print(f"Removed \033[1m{issue}\033[0m from excluded list")
    
    # Add to saved
    saved_issues.add(issue)
    save_json_set(SAVED_ISSUES_FILE, saved_issues)
    print(f"Added \033[1m{issue}\033[0m to saved issues")

def exclude_issue(args, config):
    """Add issue to excluded list."""
    if not args:
        print("Usage: exclude ISSUE")
        return
    
    issue = args[0].upper()
    saved_issues = load_json_set(SAVED_ISSUES_FILE)
    excluded_issues = load_json_set(EXCLUDED_ISSUES_FILE)
    
    # Remove from saved if present
    if issue in saved_issues:
        saved_issues.remove(issue)
        save_json_set(SAVED_ISSUES_FILE, saved_issues)
        print(f"Removed \033[1m{issue}\033[0m from saved list")
    
    # Add to excluded
    excluded_issues.add(issue)
    save_json_set(EXCLUDED_ISSUES_FILE, excluded_issues)
    print(f"Added \033[1m{issue}\033[0m to excluded issues")

def create_issue(args, config):
    """Create new issue in Jira."""
    if len(args) < 2:
        print("Usage: create PROJECT Issue description")
        return
    
    project = args[0].upper()
    summary = " ".join(args[1:])
    
    url = f"{config.base_url}/rest/api/3/issue"
    auth = HTTPBasicAuth(config.email, config.api_token)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    payload = {
        "fields": {
            "project": {
                "key": project
            },
            "summary": summary,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": summary
                            }
                        ]
                    }
                ]
            },
            "issuetype": {
                "name": "Task"
            }
        }
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, auth=auth)
        
        if response.status_code == 201:
            data = response.json()
            issue_key = data['key']
            issue_url = f"{config.base_url}/browse/{issue_key}"
            
            print(f"Created issue \033[1m{issue_key}\033[0m")
            print(f"URL: {issue_url}")
            
            # Add to saved issues
            saved_issues = load_json_set(SAVED_ISSUES_FILE)
            saved_issues.add(issue_key)
            save_json_set(SAVED_ISSUES_FILE, saved_issues)
            print(f"Added \033[1m{issue_key}\033[0m to saved issues")
            
        else:
            print(f"Failed to create issue. Status: {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Jira API: {e}")

def remove_issue(args, config):
    """Remove issue from both saved and excluded lists."""
    if not args:
        print("Usage: remove ISSUE")
        return
    
    issue = args[0].upper()
    saved_issues = load_json_set(SAVED_ISSUES_FILE)
    excluded_issues = load_json_set(EXCLUDED_ISSUES_FILE)
    
    removed_from = []
    
    # Remove from saved if present
    if issue in saved_issues:
        saved_issues.remove(issue)
        save_json_set(SAVED_ISSUES_FILE, saved_issues)
        removed_from.append("saved")
    
    # Remove from excluded if present
    if issue in excluded_issues:
        excluded_issues.remove(issue)
        save_json_set(EXCLUDED_ISSUES_FILE, excluded_issues)
        removed_from.append("excluded")
    
    if removed_from:
        lists_str = " and ".join(removed_from)
        print(f"Removed \033[1m{issue}\033[0m from {lists_str} list{'s' if len(removed_from) > 1 else ''}")
    else:
        print(f"\033[1m{issue}\033[0m was not in any saved or excluded lists")

def get_recent_issues(config, days=7):
    """Get issues from the last N days that the user has worked on."""
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=days)

    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')

    # JQL to find issues where user has logged work in the date range
    jql = f"worklogAuthor = currentUser() AND worklogDate >= '{start_str}' AND worklogDate <= '{end_str}'"

    url = f"{config.base_url}/rest/api/3/search/jql"
    auth = HTTPBasicAuth(config.email, config.api_token)
    headers = {"Accept": "application/json"}

    all_issues = []
    next_page_token = None
    max_results = 100

    try:
        while True:
            params = {
                "jql": jql,
                "fields": "key,summary,description",
                "maxResults": max_results
            }

            if next_page_token:
                params["nextPageToken"] = next_page_token

            response = requests.get(url, headers=headers, auth=auth, params=params)

            if response.status_code == 200:
                data = response.json()

                for issue in data.get('issues', []):
                    issue_key = issue['key']
                    summary = issue['fields']['summary']

                    # Extract description text from Atlassian Document Format
                    description = extract_text_from_adf(issue['fields'].get('description', ''))

                    all_issues.append({
                        'key': issue_key,
                        'summary': summary,
                        'description': description
                    })

                # Check if we have more results using nextPageToken
                next_page_token = data.get('nextPageToken')
                if not next_page_token:
                    break
            else:
                print(f"Failed to fetch recent issues. Status: {response.status_code}")
                return []

        return all_issues

    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Jira API: {e}")
        return []

def set_date_command(args, config):
    """Set the current working date."""
    global current_date
    
    if not args:
        print("Usage: set DATE")
        print("Examples:")
        print("  set 2025-08-18")
        print("  set Monday")
        print("  set 3 days ago")
        print("  set yesterday")
        return
    
    date_str = " ".join(args)
    
    try:
        parsed_date = dateparser.parse(date_str)
        if parsed_date is None:
            raise ValueError(f"Unable to parse date: {date_str}")
        
        new_date = parsed_date.date()
        current_date = new_date
        
        # Show relative description
        today = datetime.date.today()
        if new_date == today:
            relative = "today"
        elif new_date == today - datetime.timedelta(days=1):
            relative = "yesterday"
        else:
            days_diff = (today - new_date).days
            if days_diff > 0:
                relative = f"{days_diff} day{'s' if days_diff != 1 else ''} ago"
            else:
                relative = f"in {abs(days_diff)} day{'s' if abs(days_diff) != 1 else ''}"
        
        print(f"Set working date to {new_date.strftime('%Y-%m-%d')} ({new_date.strftime('%A')}, {relative})")
        
        # Show worklogs for the newly set date
        list_worklogs([], config)
        
    except (ValueError, AttributeError) as e:
        print(f"Error: Unable to parse date '{date_str}'")
        print("Supported formats:")
        print("  YYYY-MM-DD (e.g., 2025-08-18)")
        print("  Weekday names (Monday, Tue, Wed, etc.)")
        print("  Relative dates (3 days ago, yesterday)")

def reset_date_command(args, config):
    """Reset to today's date."""
    global current_date
    current_date = None
    print("Reset to today's date")

def get_working_date():
    """Get the current working date (either set date or today)."""
    return current_date if current_date is not None else datetime.date.today()

def update_cache(args, config):
    """Refresh issues cache."""
    print("Updating issues cache...")
    
    # Parse days argument (default to 7)
    days = 7
    if args and args[0].isdigit():
        days = int(args[0])
        print(f"Fetching issues from the last {days} days...")
    else:
        print(f"Fetching issues from the last {days} days...")
    
    # Get recent issues
    recent_issues = get_recent_issues(config, days)
    
    if recent_issues:
        # Save to cache file
        cache_data = {
            'updated': datetime.datetime.now().isoformat(),
            'days': days,
            'issues': recent_issues
        }
        
        ensure_cache_dir()
        with open(RECENT_ISSUES_FILE, 'w') as f:
            json.dump(cache_data, f, indent=2)
        
        print(f"Found {len(recent_issues)} issues:")
        
        # Show the issues found
        for issue_data in recent_issues:
            print(f"  \033[1m{issue_data['key']}\033[0m: {issue_data['summary']}")
        
        print(f"\nCache updated successfully. Use 'save ISSUE' to save specific issues.")
    else:
        print("No recent issues found.")
        
        # Still create an empty cache file to mark the update time
        cache_data = {
            'updated': datetime.datetime.now().isoformat(),
            'days': days,
            'issues': []
        }
        
        ensure_cache_dir()
        with open(RECENT_ISSUES_FILE, 'w') as f:
            json.dump(cache_data, f, indent=2)


# Command mapping
commands = {
    'list': list_worklogs,
    'save': save_issue,
    'exclude': exclude_issue,
    'remove': remove_issue,
    'create': create_issue,
    'update': update_cache,
    'set': set_date_command,
    'reset': reset_date_command,
    'help': help_command,
}


def match_text_against_commands(text):
    """Match text against available commands."""
    for command in commands.keys():
        if command.startswith(text):
            return commands[command]
    
    return None

def run_command(command, args, config):
    """Execute a command."""
    if callable(command):
        command(args, config)
        return
    
    raise TypeError(f"Invalid command: {command}")

# Regular expression for issue and time parsing
RE_ISSUE_TIME = re.compile(r'^([A-Z]+-\d+)\s+([0-9. hm:]+)(?:\s+(.+))?$', re.IGNORECASE)

def parse_time_to_seconds(time_str):
    """Parse various time formats and return seconds and formatted string.
    
    Supported formats:
    - 1.5h (decimal hours)
    - 3h 10m (hours and minutes)
    - 3h10 (hours and minutes without space)
    - 3:10 (hours:minutes)
    - 0:30 (minutes only in hours:minutes format)
    
    Returns tuple: (seconds, formatted_string) or (None, None) if invalid
    """
    time_str = time_str.strip()
    
    # Pattern 1: Decimal hours (1.5h, 2h, 1.5)
    decimal_match = re.match(r'^([0-9.]+)h?$', time_str, re.IGNORECASE)
    if decimal_match:
        try:
            hours = float(decimal_match.group(1))
            seconds = int(hours * 3600)
            
            # Format for display
            if hours >= 1:
                whole_hours = int(hours)
                minutes = int((hours - whole_hours) * 60)
                if minutes > 0:
                    formatted = f"{whole_hours}h {minutes}m"
                else:
                    formatted = f"{whole_hours}h"
            else:
                minutes = int(hours * 60)
                formatted = f"{minutes}m"
            
            return seconds, formatted
        except ValueError:
            pass
    
    # Pattern 2: Hours and minutes (3h 10m, 2h30m, 1h30)
    hm_match = re.match(r'^([0-9]+)h\s*([0-9]+)m?$', time_str, re.IGNORECASE)
    if hm_match:
        try:
            hours = int(hm_match.group(1))
            minutes = int(hm_match.group(2))
            seconds = (hours * 3600) + (minutes * 60)
            formatted = f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"
            return seconds, formatted
        except ValueError:
            pass
    
    # Pattern 3: Hours:minutes format (3:10, 0:30)
    colon_match = re.match(r'^([0-9]+):([0-9]+)$', time_str)
    if colon_match:
        try:
            hours = int(colon_match.group(1))
            minutes = int(colon_match.group(2))
            if minutes >= 60:
                return None, None  # Invalid minutes
            seconds = (hours * 3600) + (minutes * 60)
            if hours > 0:
                formatted = f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"
            else:
                formatted = f"{minutes}m"
            return seconds, formatted
        except ValueError:
            pass
    
    # Pattern 4: Just minutes (30m, 45)
    minutes_match = re.match(r'^([0-9]+)m?$', time_str, re.IGNORECASE)
    if minutes_match:
        try:
            minutes = int(minutes_match.group(1))
            seconds = minutes * 60
            formatted = f"{minutes}m"
            return seconds, formatted
        except ValueError:
            pass
    
    return None, None

def is_issue_time_command(text):
    """Check if text matches issue time logging format."""
    return RE_ISSUE_TIME.match(text) is not None

def check_stale_date():
    """Check if the set date might be stale and prompt to reset.

    If a specific date was set and more than 30 minutes have passed
    since the last worklog entry, prompt the user to reset to today.

    Returns True if we should proceed, False if the user cancelled.
    """
    global current_date, last_worklog_time

    if current_date is None or last_worklog_time is None:
        return True

    elapsed = datetime.datetime.now() - last_worklog_time
    if elapsed.total_seconds() < 30 * 60:
        return True

    formatted_date = current_date.strftime('%Y-%m-%d')
    try:
        answer = input(f"The date is set to {formatted_date}. Reset to current date? [Y/n] ")
    except (EOFError, KeyboardInterrupt):
        print()
        return False

    if answer.strip().lower() != 'n':
        current_date = None
        print("Reset to today's date")

    return True

def log_time_to_issue(config, text):
    """Log time to a Jira issue."""
    match = RE_ISSUE_TIME.match(text)
    if not match:
        print("Invalid format. Use: ISSUE TIME [DESCRIPTION] (e.g., 'ABC-123 2h Fixed login bug')")
        return

    issue = match.group(1).upper()
    time_str = match.group(2)
    description = match.group(3) if match.group(3) else ""

    # Parse time using the new function
    time_spent_seconds, time_spent = parse_time_to_seconds(time_str)

    if time_spent_seconds is None:
        print("Invalid time format. Supported formats:")
        print("   1.5h (decimal hours)")
        print("   3h 10m (hours and minutes)")
        print("   3h10 (hours and minutes without space)")
        print("   3:10 (hours:minutes)")
        print("   30m (minutes only)")
        return

    # Check if the set date might be stale
    if not check_stale_date():
        return

    url = f"{config.base_url}/rest/api/3/issue/{issue}/worklog"
    auth = HTTPBasicAuth(config.email, config.api_token)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    # Start time using working date at current time with proper timezone
    working_date = get_working_date()
    now = datetime.datetime.now()
    
    # Create datetime with local timezone info
    started_dt = datetime.datetime.combine(working_date, now.time()).replace(tzinfo=now.astimezone().tzinfo)
    
    # Format with proper timezone offset (Jira expects ISO format with timezone)
    started = started_dt.strftime('%Y-%m-%dT%H:%M:%S.000%z')
    
    payload = {
        "timeSpentSeconds": time_spent_seconds,
        "started": started
    }
    
    # Add comment/description if provided
    if description:
        payload["comment"] = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": description
                        }
                    ]
                }
            ]
        }
    
    try:
        response = requests.post(url, json=payload, headers=headers, auth=auth)
        
        if response.status_code == 201:
            global last_worklog_time
            last_worklog_time = datetime.datetime.now()

            if description:
                print(f"Logged {time_spent} to \033[1m{issue}\033[0m: {description}")
            else:
                print(f"Logged {time_spent} to \033[1m{issue}\033[0m")

            # Show working date's worklogs after successful logging
            working_date = get_working_date()
            today = datetime.date.today()
            
            if working_date != today:
                if working_date == today - datetime.timedelta(days=1):
                    date_context = f" (working date: yesterday, {working_date.strftime('%Y-%m-%d')})"
                else:
                    days_diff = (today - working_date).days
                    if days_diff > 0:
                        date_context = f" (working date: {days_diff} day{'s' if days_diff != 1 else ''} ago, {working_date.strftime('%Y-%m-%d')})"
                    else:
                        date_context = f" (working date: in {abs(days_diff)} day{'s' if abs(days_diff) != 1 else ''}, {working_date.strftime('%Y-%m-%d')})"
            else:
                date_context = ""
            
            print(f"\nToday's worklogs{date_context}:")
            daily_worklogs = get_daily_worklogs(config)
            
            if daily_worklogs:
                total_seconds = 0
                for worklog in daily_worklogs:
                    line = f"  \033[1m{worklog['issue']}\033[0m: {worklog['timeSpent']} - {worklog['summary']}"
                    if worklog['comment']:
                        line += f" – {worklog['comment']}"
                    print(line)
                    total_seconds += worklog['timeSpentSeconds']
                
                print(f"  Total: {total_seconds // 3600}h {(total_seconds % 3600) // 60}m")
            else:
                print("  No worklogs found for today")
        else:
            print(f"Failed to log time to \033[1m{issue}\033[0m. Status: {response.status_code}")
            if response.status_code == 404:
                print(f"   Issue \033[1m{issue}\033[0m not found or no permission to log work")
            else:
                print(f"   Response: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Jira API: {e}")

def run_single_command(config):
    """Run a single command in the shell loop."""
    original_text = get_input_until(bool, prompt="jira> ")
    
    parts = shlex.split(original_text)
    
    # Check if it's an issue time logging command
    if is_issue_time_command(original_text):
        log_time_to_issue(config, original_text)
        return
    
    # Check if it's a regular command
    command = match_text_against_commands(parts[0])
    
    if command is not None:
        run_command(command, parts[1:], config)
        return
    
    print(f"Unknown command: {parts[0]}. Type 'help' for available commands.")


def main():
    """Main entry point for jira command."""
    arguments = docopt(__doc__, version=VERSION)

    try:
        config = JiraConfigFile()
    except Exception as e:
        print(f"Configuration error: {e}")
        print("Please create ~/.jira/config.ini with your Jira credentials")
        return 1

    # Non-interactive mode: just print today's worklogs and exit
    if arguments['--list']:
        # Determine the target date
        if arguments['--yesterday']:
            target_date = datetime.date.today() - datetime.timedelta(days=1)
        elif arguments['--date']:
            parsed = dateparser.parse(arguments['--date'])
            if parsed is None:
                print(f"Error: Unable to parse date '{arguments['--date']}'")
                return 1
            target_date = parsed.date()
        else:
            target_date = datetime.date.today()

        daily_worklogs = get_daily_worklogs(config, target_date)

        # Only use colors if output is a terminal
        if sys.stdout.isatty():
            bold, reset = "\033[1m", "\033[0m"
        else:
            bold, reset = "", ""

        # Show date header if not today
        today = datetime.date.today()
        if target_date != today:
            print(f"Worklogs for {target_date.strftime('%Y-%m-%d')} ({target_date.strftime('%A')}):")

        if daily_worklogs:
            total_seconds = 0
            for worklog in daily_worklogs:
                line = f"{bold}{worklog['issue']}{reset}: {worklog['timeSpent']} - {worklog['summary']}"
                if worklog['comment']:
                    line += f" – {worklog['comment']}"
                print(line)
                total_seconds += worklog['timeSpentSeconds']

            print(f"Total: {total_seconds // 3600}h {(total_seconds % 3600) // 60}m")
        else:
            if target_date == today:
                print("No worklogs found for today")
            else:
                print("No worklogs found")
        return 0

    # Setup readline with persistent history (only for interactive mode)
    setup_readline()

    print(f"Connected to Jira at {config.domain}")
    print("Type 'help' for available commands, or 'ISSUE TIME [DESC]' to log time (e.g., 'ABC-123 2h Fixed bug')")

    # Show initial status
    list_worklogs([], config)

    try:
        consume(repeatfunc(
            run_single_command,
            None,
            config,
        ))
    except (KeyboardInterrupt, EOFError):
        print("\nExiting...")
        return 0

if __name__ == '__main__':
    exit(main())
