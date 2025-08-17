"""Jira + Google Calendar integration tool.

Usage: 
    jira-calendar PROJECT_OR_ISSUE [options] TIME DAY
    jira-calendar PROJECT_OR_ISSUE [options] TIME_START TIME_END DAY

Arguments:
    PROJECT_OR_ISSUE    Either a project key (e.g., MEET) or existing issue (e.g., ABC-123)

Options:
    -t TIME, --duration=TIME   Meeting duration [default: 1h]
    -s SUMMARY, --summary=SUMMARY  Issue summary for new issue [default: Meeting]
    -c CALENDAR, --calendar=CALENDAR  Calendar name or ID to use (overrides config)
    -m TITLE, --meeting=TITLE  Title of the calendar event (overrides default)
    -d DESC, --description=DESC  Additional description for the calendar event
    -h, --help                 Show this message.
    --version                  Show version information.

Examples:
    jira-calendar MEET 14:30 Friday                    # Create issue in MEET project, 1h meeting
    jira-calendar ABC-123 14:30 Friday                 # Use existing issue ABC-123
    jira-calendar MEET -t 30m 14:30 Friday            # 30min meeting in MEET project
    jira-calendar MEET 14:30 15:00 Friday             # Meeting from 14:30 to 15:00
    jira-calendar ABC-123 14:30 "next Friday"         # Use existing issue, next Friday
    jira-calendar MEET 14:30 2024-12-25               # Meeting on specific date
    jira-calendar MEET -c work 14:30 Friday           # Use named calendar "work"
    jira-calendar MEET -m "Team Standup" 14:30 Friday  # Custom meeting title
    jira-calendar MEET -d "Discuss Q4 planning" 14:30 Friday  # Add description

Configuration:
    Create ~/.google/config.ini with:
    
    [WorkGoogle]
    token_path = ~/.google/work_token.json
    credentials_path = ~/.google/work_credentials.json
    selected_calendar = work
    
    [WorkCalendars]
    work = john.doe@company.com
    personal = john.doe@gmail.com
    team = team-calendar@company.com
    
    And ~/.jira/config.ini with:
    
    [Jira]
    domain = your-company
    email = your-email@company.com
    api_token = your-jira-api-token
"""

import json
import datetime
import re
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from docopt import docopt
import requests
from requests.auth import HTTPBasicAuth
import dateparser

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .config.jira import JiraConfigFile

VERSION = '1.0'

# Google Calendar API scopes
SCOPES = ['https://www.googleapis.com/auth/calendar']

class WorkGoogleConfigFile:
    """Separate Google config for work calendar (different from personal calendar)."""
    token_path = None
    credentials_path = None
    calendars = {}

    def __init__(self):
        from configparser import ConfigParser
        self.reader = ConfigParser()
        self.reader.read(self.paths())

        try:
            self.token_path = Path(self.reader['WorkGoogle']['token_path']).expanduser()
            self.credentials_path = Path(self.reader['WorkGoogle']['credentials_path']).expanduser()
            self.selected_calendar = self.reader['WorkGoogle'].get('selected_calendar', 'primary')
            
            # Load named calendars from config
            self.calendars = {}
            if self.reader.has_section('WorkCalendars'):
                for name, calendar_id in self.reader.items('WorkCalendars'):
                    self.calendars[name] = calendar_id
            
        except KeyError:
            raise KeyError("Create ~/.google/config.ini file with section [WorkGoogle] containing token_path/credentials_path")
    
    def get_calendar_id(self, name_or_id):
        """Get calendar ID by name (from config) or return the ID directly if not found in named calendars."""
        return self.calendars.get(name_or_id, name_or_id)

    def paths(self):
        return [
            '/etc/google/config.ini',
            Path.home() / '.google/config.ini',
        ]

def parse_time_duration(time_str):
    """Parse time duration string and return seconds.
    
    Supported formats:
    - 1h, 1.5h (hours)
    - 30m, 45m (minutes)
    - 1h30m (hours and minutes)
    """
    time_str = time_str.strip().lower()
    
    # Pattern for hours and minutes (1h30m)
    hm_match = re.match(r'^(\d+(?:\.\d+)?)h(?:(\d+)m)?$', time_str)
    if hm_match:
        hours = float(hm_match.group(1))
        minutes = int(hm_match.group(2)) if hm_match.group(2) else 0
        return int(hours * 3600 + minutes * 60)
    
    # Pattern for just hours (1h, 1.5h)
    h_match = re.match(r'^(\d+(?:\.\d+)?)h?$', time_str)
    if h_match:
        hours = float(h_match.group(1))
        return int(hours * 3600)
    
    # Pattern for just minutes (30m)
    m_match = re.match(r'^(\d+)m$', time_str)
    if m_match:
        minutes = int(m_match.group(1))
        return minutes * 60
    
    raise ValueError(f"Invalid time format: {time_str}")

def get_local_timezone():
    """Get the system's local timezone."""
    try:
        # Get timezone name from system
        timezone_name = time.tzname[time.daylight]
        # Try to convert to IANA timezone
        local_tz = datetime.datetime.now().astimezone().tzinfo
        if hasattr(local_tz, 'key'):
            return local_tz.key
        else:
            # Fallback to UTC offset
            return local_tz.tzname(None)
    except Exception:
        # Ultimate fallback
        return 'UTC'

def parse_date_time(time_str, day_str):
    """Parse time and day strings into datetime object using system timezone.
    
    Args:
        time_str: Time in HH:MM format (e.g., "14:30")
        day_str: Day specification (e.g., "Friday", "next Friday", "2024-12-25")
    
    Returns:
        datetime.datetime object with local timezone info
    """
    # Parse time
    time_match = re.match(r'^(\d{1,2}):(\d{2})$', time_str)
    if not time_match:
        raise ValueError(f"Invalid time format: {time_str}. Use HH:MM format.")
    
    hour = int(time_match.group(1))
    minute = int(time_match.group(2))
    
    if hour > 23 or minute > 59:
        raise ValueError(f"Invalid time: {time_str}")
    
    # Use dateparser to parse the day string
    parsed_date = dateparser.parse(day_str, settings={'PREFER_DATES_FROM': 'future'})
    
    if parsed_date is None:
        raise ValueError(f"Could not parse date: {day_str}")
    
    # Combine the parsed date with the specified time
    target_date = parsed_date.date()
    naive_datetime = datetime.datetime.combine(target_date, datetime.time(hour, minute))
    
    # Add local timezone information
    return naive_datetime.replace(tzinfo=datetime.datetime.now().astimezone().tzinfo)

def is_existing_issue(project_or_issue):
    """Check if the argument is an existing issue key (e.g., ABC-123) or a project key."""
    # Pattern for issue keys: PROJECT-NUMBER (e.g., ABC-123, DEV-456)
    return re.match(r'^[A-Z]+-\d+$', project_or_issue.upper()) is not None

def get_google_calendar_service(config):
    """Get authenticated Google Calendar service."""
    creds = None
    
    # Load existing token
    if config.token_path.exists():
        creds = Credentials.from_authorized_user_file(str(config.token_path), SCOPES)
    
    # If there are no (valid) credentials available, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(config.credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save the credentials for the next run
        config.token_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config.token_path, 'w') as token:
            token.write(creds.to_json())
    
    return build('calendar', 'v3', credentials=creds)

def create_jira_issue(jira_config, project, summary, meeting_title=None, additional_description=None):
    """Create a new Jira issue and return its key."""
    url = f"{jira_config.base_url}/rest/api/3/issue"
    auth = HTTPBasicAuth(jira_config.email, jira_config.api_token)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    # Use meeting title as issue summary if provided, otherwise use default summary
    issue_summary = meeting_title or summary
    
    # Build description content
    description_content = []
    
    if meeting_title and meeting_title != summary:
        # If we have a custom meeting title, include the original summary in description
        description_content.append({
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": f"Type: {summary}"
                }
            ]
        })
    
    if additional_description:
        description_content.append({
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": additional_description
                }
            ]
        })
    
    # If no description content, add a default
    if not description_content:
        description_content.append({
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": issue_summary
                }
            ]
        })
    
    payload = {
        "fields": {
            "project": {
                "key": project
            },
            "summary": issue_summary,
            "description": {
                "type": "doc",
                "version": 1,
                "content": description_content
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
            return issue_key
        else:
            raise Exception(f"Failed to create issue. Status: {response.status_code}, Response: {response.text}")
            
    except requests.exceptions.RequestException as e:
        raise Exception(f"Error connecting to Jira API: {e}")

def get_issue_summary(jira_config, issue_key):
    """Get issue summary from Jira API."""
    url = f"{jira_config.base_url}/rest/api/3/issue/{issue_key}"
    auth = HTTPBasicAuth(jira_config.email, jira_config.api_token)
    headers = {"Accept": "application/json"}
    
    params = {"fields": "summary"}
    
    try:
        response = requests.get(url, headers=headers, auth=auth, params=params)
        
        if response.status_code == 200:
            data = response.json()
            return data['fields']['summary']
        else:
            print(f"Warning: Could not fetch issue summary for {issue_key}. Status: {response.status_code}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"Warning: Error connecting to Jira API for issue {issue_key}: {e}")
        return None

def create_calendar_event(calendar_service, calendar_id, start_time, end_time, issue_key, issue_url, summary, meeting_title=None, additional_description=None):
    """Create a Google Calendar event with Jira issue link."""
    # Use custom meeting title or default to issue + summary
    event_title = meeting_title or f"{issue_key}: {summary}"
    
    # Build description with Jira link and optional additional description
    description_parts = [f"Jira Issue: {issue_url}"]
    if additional_description:
        description_parts.append(f"\n{additional_description}")
    
    # Get timezone from the datetime objects
    timezone_name = start_time.tzinfo.key if hasattr(start_time.tzinfo, 'key') else 'UTC'
    
    event = {
        'summary': event_title,
        'description': '\n'.join(description_parts),
        'start': {
            'dateTime': start_time.isoformat(),
            'timeZone': timezone_name,
        },
        'end': {
            'dateTime': end_time.isoformat(),
            'timeZone': timezone_name,
        },
    }
    
    try:
        event = calendar_service.events().insert(
            calendarId=calendar_id,
            body=event
        ).execute()
        
        return event.get('htmlLink')
        
    except HttpError as error:
        raise Exception(f"Error creating calendar event: {error}")

def main():
    """Main entry point for jira-calendar command."""
    arguments = docopt(__doc__, version=VERSION)
    
    # Parse arguments
    project_or_issue = arguments['PROJECT_OR_ISSUE']
    time_args = [arguments['TIME'], arguments.get('TIME_END')]
    time_args = [t for t in time_args if t is not None]
    day = arguments['DAY']
    duration_str = arguments.get('--duration', '1h')
    summary = arguments.get('--summary', 'Meeting')
    calendar_override = arguments.get('--calendar')
    meeting_title = arguments.get('--meeting')
    additional_description = arguments.get('--description')
    
    try:
        # Initialize configs
        jira_config = JiraConfigFile()
        google_config = WorkGoogleConfigFile()
        
        # Parse start time with local timezone
        start_time = parse_date_time(time_args[0], day)
        
        # Calculate end time
        if len(time_args) == 2:
            # End time specified
            end_time_parts = time_args[1].split(':')
            end_hour = int(end_time_parts[0])
            end_minute = int(end_time_parts[1])
            end_time = datetime.datetime.combine(start_time.date(), datetime.time(end_hour, end_minute))
            
            if end_time <= start_time:
                raise ValueError("End time must be after start time")
        else:
            # Use duration
            duration_seconds = parse_time_duration(duration_str)
            end_time = start_time + datetime.timedelta(seconds=duration_seconds)
        
        # Handle Jira issue
        if is_existing_issue(project_or_issue):
            # It's an existing issue
            issue_key = project_or_issue.upper()
            print(f"Using existing issue: {issue_key}")
            
            # If no custom meeting title provided, get issue summary from Jira
            if not meeting_title:
                issue_summary = get_issue_summary(jira_config, issue_key)
                if issue_summary:
                    summary = issue_summary
                    print(f"Using issue summary: {issue_summary}")
        else:
            # It's a project key, create new issue
            project = project_or_issue.upper()
            print(f"Creating new issue in project {project}...")
            issue_key = create_jira_issue(jira_config, project, summary, meeting_title, additional_description)
            print(f"Created issue: {issue_key}")
        
        issue_url = f"{jira_config.base_url}/browse/{issue_key}"
        
        # Determine which calendar to use
        calendar_name_or_id = calendar_override or google_config.selected_calendar
        calendar_to_use = google_config.get_calendar_id(calendar_name_or_id)
        
        # Create calendar event
        print(f"Creating calendar event for {start_time.strftime('%Y-%m-%d %H:%M')} - {end_time.strftime('%H:%M')}...")
        calendar_service = get_google_calendar_service(google_config)
        calendar_link = create_calendar_event(
            calendar_service, calendar_to_use, start_time, end_time, 
            issue_key, issue_url, summary, meeting_title, additional_description
        )
        
        print(f"✓ Issue: {issue_url}")
        print(f"✓ Calendar event: {calendar_link}")
        
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0

if __name__ == '__main__':
    exit(main())