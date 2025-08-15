"""Jira Time Tracker auto-updater.

Usage:
    jira-dates [--date=<date>] [--format=<fmt>] [--dashboard=<id>] [--month-string=<str>] [--week-string=<str>]
    jira-dates (-h | --help)

Options:
    -h --help              Show this screen.
    --date=<date>          Reference date for calculations (YYYY-MM-DD format, defaults to today).
    --format=<fmt>         Date format [default: %Y-%m-%d].
    --dashboard=<id>       Dashboard ID (overrides config).
    --month-string=<str>   String to detect month gadgets (overrides config, defaults to "month").
    --week-string=<str>    String to detect week gadgets (overrides config, defaults to "week").

Examples:
    jira-dates                                    # Auto-update all time tracker gadgets to current periods
    jira-dates --date=2025-07-15                 # Use July 15, 2025 as reference date
    jira-dates --dashboard=123                    # Update specific dashboard
    jira-dates --month-string="monthly"          # Use "monthly" to detect month gadgets
    jira-dates --week-string="weekly"            # Use "weekly" to detect week gadgets

Configuration:
    Create ~/.jira/config.ini with:
    [Jira]
    domain = your-domain
    email = your-email@example.com
    api_token = your-api-token
    dashboard_id = 12345
    month_string = month  # Optional, defaults to "month"
    week_string = week    # Optional, defaults to "week"

"""
import datetime
import json
import requests
from requests.auth import HTTPBasicAuth
from docopt import docopt
from randomtools.config.jira import JiraConfigFile

VERSION = '1.0'


def get_week_range(reference_date):
    """Get start and end dates for the week containing the given reference date."""
    # Get Monday of the week (weekday() returns 0 for Monday)
    days_since_monday = reference_date.weekday()
    monday = reference_date - datetime.timedelta(days=days_since_monday)
    
    # Sunday is 6 days after Monday
    sunday = monday + datetime.timedelta(days=6)
    
    return monday, sunday


def get_month_range(reference_date):
    """Get start and end dates for the month containing the given reference date."""
    # First day of the month
    first_day = reference_date.replace(day=1)
    
    # Last day of the month
    if reference_date.month == 12:
        next_month = reference_date.replace(year=reference_date.year + 1, month=1, day=1)
    else:
        next_month = reference_date.replace(month=reference_date.month + 1, day=1)
    
    last_day = next_month - datetime.timedelta(days=1)
    
    return first_day, last_day


def get_timetracker_gadgets(config, dashboard_id):
    """Get all time tracker gadgets from a dashboard."""
    url = f"{config.base_url}/rest/api/3/dashboard/{dashboard_id}/gadget"
    
    auth = HTTPBasicAuth(config.email, config.api_token)
    headers = {"Accept": "application/json"}
    
    try:
        response = requests.get(url, headers=headers, auth=auth)
        
        if response.status_code == 200:
            data = response.json()
            gadgets = data.get('gadgets', [])
            
            # Filter for time tracker gadgets
            timetracker_gadgets = []
            for gadget in gadgets:
                module_key = gadget.get('moduleKey', '')
                if 'timereports-gadget' in module_key:
                    timetracker_gadgets.append(gadget)
            
            return timetracker_gadgets
        else:
            print(f"✗ Failed to fetch dashboard gadgets. Status: {response.status_code}")
            return []
            
    except requests.exceptions.RequestException as e:
        print(f"✗ Error connecting to Jira API: {e}")
        return []


def get_gadget_config(config, dashboard_id, gadget_id):
    """Get gadgetConfig for a specific gadget."""
    url = f"{config.base_url}/rest/api/3/dashboard/{dashboard_id}/items/{gadget_id}/properties/gadgetConfig"
    
    auth = HTTPBasicAuth(config.email, config.api_token)
    headers = {"Accept": "application/json"}
    
    try:
        response = requests.get(url, headers=headers, auth=auth)
        
        if response.status_code == 200:
            data = response.json()
            return data.get('value', {})
        else:
            print(f"✗ Failed to fetch config for gadget {gadget_id}. Status: {response.status_code}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"✗ Error fetching config for gadget {gadget_id}: {e}")
        return None


def update_gadget_config(config, dashboard_id, gadget_id, updated_config):
    """Update gadgetConfig for a specific gadget."""
    url = f"{config.base_url}/rest/api/3/dashboard/{dashboard_id}/items/{gadget_id}/properties/gadgetConfig"
    
    auth = HTTPBasicAuth(config.email, config.api_token)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    payload = json.dumps(updated_config)
    
    try:
        response = requests.put(url, data=payload, headers=headers, auth=auth)

        print(f"Response: {response.text}")
        if response.status_code in [200, 201, 204]:
            return True
        else:
            print(f"✗ Failed to update config for gadget {gadget_id}. Status: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"✗ Error updating config for gadget {gadget_id}: {e}")
        return False


def auto_update_timetracker_gadgets(config, dashboard_id, reference_date, date_format, month_string=None, week_string=None):
    """Automatically find and update all time tracker gadgets."""
    print(f"Auto-updating time tracker gadgets in dashboard {dashboard_id}...")
    print(f"Reference date: {reference_date.strftime('%Y-%m-%d')}")
    
    # Use provided strings or fall back to config or defaults
    month_str = month_string or config.month_string or 'month'
    week_str = week_string or config.week_string or 'week'
    
    print(f"Using detection strings: month='{month_str}', week='{week_str}'")
    
    gadgets = get_timetracker_gadgets(config, dashboard_id)
    if not gadgets:
        print("No time tracker gadgets found in dashboard")
        return True
    
    print(f"Found {len(gadgets)} time tracker gadgets")
    updated_count = 0
    
    for gadget in gadgets:
        gadget_id = gadget.get('id')
        title = gadget.get('title', '').lower()
        
        print(f"\nProcessing gadget {gadget_id}: '{gadget.get('title', 'N/A')}'")
        
        # Determine if it's a week or month gadget using configurable strings
        is_month = month_str.lower() in title
        is_week = week_str.lower() in title
        
        if not (is_month or is_week):
            print(f"  Skipping - title doesn't contain '{week_str}' or '{month_str}'")
            continue
        
        # Get current config
        current_config = get_gadget_config(config, dashboard_id, gadget_id)
        if current_config is None:
            print(f"  Skipping - couldn't get config")
            continue
        
        # Calculate new dates based on reference date
        if is_month:
            start_date, end_date = get_month_range(reference_date)
            period_type = "month"
        else:
            start_date, end_date = get_week_range(reference_date)
            period_type = "week"
        
        # Update config with new dates
        updated_config = current_config.copy()
        updated_config['startDate'] = start_date.strftime(date_format)
        updated_config['endDate'] = end_date.strftime(date_format)
        
        print(f"  Updating {period_type}: {start_date.strftime(date_format)} to {end_date.strftime(date_format)}")
        
        if update_gadget_config(config, dashboard_id, gadget_id, updated_config):
            print(f"  ✓ Successfully updated gadget {gadget_id}")
            updated_count += 1
        else:
            print(f"  ✗ Failed to update gadget {gadget_id}")
    
    print(f"\nSummary: Updated {updated_count} of {len(gadgets)} gadgets")
    return updated_count > 0



def main():
    """Main entry point for jira-dates command."""
    args = docopt(__doc__, version=VERSION)
    
    date_format = args['--format']
    date_string = args['--date']
    month_string = args['--month-string']
    week_string = args['--week-string']
    
    try:
        config = JiraConfigFile()
        
        dashboard_id = args['--dashboard'] or config.dashboard_id
        
        if not dashboard_id:
            print("✗ Error: dashboard_id is required")
            print("Provide it via --dashboard argument or in ~/.jira/config.ini")
            return 1
        
        # Parse reference date
        if date_string:
            try:
                reference_date = datetime.datetime.strptime(date_string, '%Y-%m-%d').date()
            except ValueError:
                print(f"✗ Error: Invalid date format '{date_string}'. Use YYYY-MM-DD format.")
                return 1
        else:
            reference_date = datetime.date.today()
        
        success = auto_update_timetracker_gadgets(config, dashboard_id, reference_date, date_format, month_string, week_string)
        return 0 if success else 1
            
    except KeyError as e:
        print(f"✗ Configuration error: {e}")
        return 1
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return 1


if __name__ == '__main__':
    exit(main())