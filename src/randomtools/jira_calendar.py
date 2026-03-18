"""Jira + Google Calendar integration tool.

Usage:
    jira-calendar PROJECT_OR_ISSUE [options] TIME DAY
    jira-calendar PROJECT_OR_ISSUE [options] TIME_START TIME_END DAY

Arguments:
    PROJECT_OR_ISSUE    Either a project key (e.g., MEET) or existing issue (e.g., ABC-123)

Options:
    -t TIME, --duration=TIME   Meeting duration [default: 1h]
    -c CALENDAR, --calendar=CALENDAR  Calendar name or ID to use (overrides config)
    -A, --dont-assign          Default template checkbox for assign to unchecked
    -M, --no-google-meet       Default template checkbox for Google Meet to unchecked
    --slack CHANNEL            Slack channel to invite members from and notify
    -S, --no-message           Default template checkbox for Slack message to unchecked
    --template                 Print the meeting template to stdout and exit
    -f FILE, --file=FILE       Use a prefilled template file instead of opening Vim
    -h, --help                 Show this message.
    --version                  Show version information.

Examples:
    jira-calendar MEET 14:30 Friday                        # Opens Vim to edit meeting template
    jira-calendar ABC-123 14:30 Friday                     # Use existing issue ABC-123
    jira-calendar MEET -t 30m 14:30 Friday                 # 30min meeting
    jira-calendar MEET 14:30 15:00 Friday                  # Meeting from 14:30 to 15:00
    jira-calendar MEET --slack dev 14:30 Friday            # Prefill attendees from #dev channel
    jira-calendar MEET --template --slack dev 14:30 Friday # Print template to stdout
    jira-calendar MEET -f meeting.md 14:30 Friday          # Use prefilled template file
    jira-calendar MEET -M -A 14:30 Friday                  # Default: no Meet, no assign

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

import datetime
import os
import re
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
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
from .config.slack import SlackConfigFile

VERSION = '1.1'

# Google Calendar API scopes
SCOPES = ['https://www.googleapis.com/auth/calendar']


@dataclass
class MeetingConfig:
    title: str = ''
    description: str = ''
    slack_message: bool = False
    slack_channel: str = None
    google_meet: bool = True
    assign_to_me: bool = True
    attendees: list = field(default_factory=list)
    optional_attendees: list = field(default_factory=list)


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

def get_local_timezone():
    """Get the system's IANA timezone as a ZoneInfo object."""
    tz_env = os.environ.get('TZ')
    if tz_env:
        try:
            return ZoneInfo(tz_env)
        except (KeyError, ValueError):
            pass

    localtime = Path('/etc/localtime')
    if localtime.is_symlink():
        target = str(localtime.resolve())
        idx = target.find('zoneinfo/')
        if idx != -1:
            tz_name = target[idx + len('zoneinfo/'):]
            try:
                return ZoneInfo(tz_name)
            except (KeyError, ValueError):
                pass

    return datetime.datetime.now().astimezone().tzinfo


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

def parse_date_time(time_str, day_str):
    """Parse time and day strings into datetime object using system timezone."""
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

    # Add local timezone information (IANA-aware, handles DST correctly)
    local_tz = get_local_timezone()
    return naive_datetime.replace(tzinfo=local_tz)

def is_existing_issue(project_or_issue):
    """Check if the argument is an existing issue key (e.g., ABC-123) or a project key."""
    return re.match(r'^[A-Z]+-\d+$', project_or_issue.upper()) is not None


# --- Template generation and parsing ---

def generate_template(project_or_issue, summary=None, slack_channel=None,
                      attendee_emails=None, google_meet=True, assign_to_me=True,
                      slack_message=True):
    """Generate a Markdown meeting template."""
    lines = []

    # Heading
    if summary:
        lines.append(f"# {project_or_issue}: {summary}")
    else:
        lines.append(f"# {project_or_issue}: ")

    # Description
    lines.append("")
    lines.append("Meeting")
    lines.append("")

    # Option checkboxes
    if slack_channel:
        check = "x" if slack_message else " "
        lines.append(f"- [{check}] Slack message ({slack_channel})")

    check = "x" if google_meet else " "
    lines.append(f"- [{check}] Create Google Meet")

    check = "x" if assign_to_me else " "
    lines.append(f"- [{check}] Assign to me")

    # Attendees section
    lines.append("")
    lines.append("## Attendees (emails)")
    lines.append("")

    if attendee_emails:
        for email in attendee_emails:
            lines.append(f"- [x] {email}")
    else:
        lines.append("- [ ] ")

    lines.append("")
    return '\n'.join(lines)


def parse_template(content):
    """Parse a Markdown meeting template into MeetingConfig."""
    lines = content.split('\n')

    config = MeetingConfig()

    # Parse heading: # KEY: Title
    for line in lines:
        if line.startswith('# '):
            match = re.match(r'^#\s+\S+:\s*(.*)', line)
            if match:
                config.title = match.group(1).strip()
            break

    # Parse description: text between heading and first checkbox or ## section
    desc_lines = []
    past_heading = False
    for line in lines:
        if line.startswith('# '):
            past_heading = True
            continue
        if not past_heading:
            continue
        if line.startswith('- [') or line.startswith('## '):
            break
        desc_lines.append(line)
    config.description = '\n'.join(desc_lines).strip()

    # Parse checkboxes and attendees
    in_attendees = False
    for line in lines:
        stripped = line.strip()

        if stripped.startswith('## Attendees'):
            in_attendees = True
            continue

        if in_attendees:
            match = re.match(r'^-\s+\[(x|~| )\]\s+(.*)', stripped)
            if match:
                marker = match.group(1)
                email = match.group(2).strip()
                if email:
                    if marker == 'x':
                        config.attendees.append(email)
                    elif marker == '~':
                        config.optional_attendees.append(email)
            continue

        # Option checkboxes (before attendees section)
        match = re.match(r'^-\s+\[(x| )\]\s+(.*)', stripped)
        if match:
            checked = match.group(1) == 'x'
            text = match.group(2)

            if text.startswith('Slack message'):
                config.slack_message = checked
                ch_match = re.search(r'\(([^)]+)\)', text)
                if ch_match:
                    config.slack_channel = ch_match.group(1)
            elif text.startswith('Create Google Meet'):
                config.google_meet = checked
            elif text.startswith('Assign to me'):
                config.assign_to_me = checked

    return config


def open_in_editor(template_content):
    """Write template to a temp file, open in Vim, return edited content."""
    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.md', delete=False, prefix='jira-calendar-'
    ) as f:
        f.write(template_content)
        tmppath = f.name

    try:
        result = subprocess.run(['vim', '+3', tmppath])
        if result.returncode != 0:
            raise Exception("Editor exited with non-zero status")
        with open(tmppath) as f:
            return f.read()
    finally:
        Path(tmppath).unlink(missing_ok=True)


# --- Google Calendar ---

def get_google_calendar_service(config):
    """Get authenticated Google Calendar service."""
    creds = None

    if config.token_path.exists():
        creds = Credentials.from_authorized_user_file(str(config.token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(config.credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)

        config.token_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config.token_path, 'w') as token:
            token.write(creds.to_json())

    return build('calendar', 'v3', credentials=creds)

def create_calendar_event(calendar_service, calendar_id, start_time, end_time,
                          title, description, google_meet=True, attendees=None,
                          optional_attendees=None):
    """Create a Google Calendar event."""
    timezone_name = start_time.tzinfo.key if hasattr(start_time.tzinfo, 'key') else 'UTC'

    event = {
        'summary': title,
        'description': description,
        'start': {
            'dateTime': start_time.isoformat(),
            'timeZone': timezone_name,
        },
        'end': {
            'dateTime': end_time.isoformat(),
            'timeZone': timezone_name,
        },
    }

    if attendees or optional_attendees:
        event['attendees'] = [{'email': email} for email in (attendees or [])]
        event['attendees'] += [{'email': email, 'optional': True} for email in (optional_attendees or [])]

    if google_meet:
        event['conferenceData'] = {
            'createRequest': {
                'requestId': str(uuid.uuid4()),
                'conferenceSolutionKey': {
                    'type': 'hangoutsMeet',
                },
            },
        }

    try:
        event = calendar_service.events().insert(
            calendarId=calendar_id,
            body=event,
            conferenceDataVersion=1 if google_meet else 0,
        ).execute()

        meet_link = None
        conference = event.get('conferenceData')
        if conference:
            for ep in conference.get('entryPoints', []):
                if ep.get('entryPointType') == 'video':
                    meet_link = ep.get('uri')
                    break

        return event.get('htmlLink'), meet_link

    except HttpError as error:
        raise Exception(f"Error creating calendar event: {error}")


def query_freebusy(calendar_service, emails, time_min, time_max):
    """Query FreeBusy API for the given window. Returns {email: [(start, end), ...]}."""
    body = {
        "timeMin": time_min.isoformat(),
        "timeMax": time_max.isoformat(),
        "items": [{"id": email} for email in emails],
    }
    result = calendar_service.freebusy().query(body=body).execute()

    busy_periods = {}
    for email in emails:
        periods = []
        for p in result.get('calendars', {}).get(email, {}).get('busy', []):
            periods.append((
                datetime.datetime.fromisoformat(p['start']),
                datetime.datetime.fromisoformat(p['end']),
            ))
        if periods:
            busy_periods[email] = periods
    return busy_periods


def find_conflicts(busy_periods, start_time, end_time):
    """From pre-fetched busy periods, find which overlap with [start_time, end_time)."""
    conflicts = {}
    for email, periods in busy_periods.items():
        overlapping = [(s, e) for s, e in periods if s < end_time and e > start_time]
        if overlapping:
            conflicts[email] = overlapping
    return conflicts


def find_available_slot(busy_periods, date, duration, tz):
    """From pre-fetched busy periods, find the first available slot between 10:00-17:00.

    Returns (start, end) or None.
    """
    window_start = datetime.datetime.combine(date, datetime.time(10, 0), tzinfo=tz)
    window_end = datetime.datetime.combine(date, datetime.time(17, 0), tzinfo=tz)

    all_busy = []
    for periods in busy_periods.values():
        all_busy.extend(periods)
    all_busy.sort()

    merged = []
    for start, end in all_busy:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    candidate = window_start
    for busy_start, busy_end in merged:
        if candidate + duration <= busy_start:
            return candidate, candidate + duration
        if busy_end > candidate:
            candidate = busy_end.astimezone(tz)
            mins = candidate.minute
            remainder = mins % 15
            if remainder:
                candidate += datetime.timedelta(minutes=15 - remainder)
                candidate = candidate.replace(second=0, microsecond=0)

    if candidate + duration <= window_end:
        return candidate, candidate + duration

    return None


# --- Jira ---

def get_myself(jira_config):
    """Get the current user's account ID from Jira."""
    url = f"{jira_config.base_url}/rest/api/3/myself"
    auth = HTTPBasicAuth(jira_config.email, jira_config.api_token)
    headers = {"Accept": "application/json"}

    response = requests.get(url, headers=headers, auth=auth)

    if response.status_code == 200:
        return response.json()['accountId']

    raise Exception(f"Failed to get current user. Status: {response.status_code}, Response: {response.text}")


def assign_issue(jira_config, issue_key, account_id):
    """Assign a Jira issue to a user."""
    url = f"{jira_config.base_url}/rest/api/3/issue/{issue_key}/assignee"
    auth = HTTPBasicAuth(jira_config.email, jira_config.api_token)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    response = requests.put(url, json={"accountId": account_id}, headers=headers, auth=auth)

    if response.status_code != 204:
        print(f"Warning: Could not assign issue {issue_key}. Status: {response.status_code}")


def text_to_adf_content(text):
    """Convert text with URLs into ADF paragraph content nodes.

    Splits text on URLs so that plain text becomes text nodes and URLs become
    text nodes with a link mark, making them clickable in Jira.
    """
    url_re = re.compile(r'(https?://\S+)')
    parts = url_re.split(text)
    nodes = []
    for part in parts:
        if not part:
            continue
        if url_re.match(part):
            nodes.append({
                "type": "text",
                "text": part,
                "marks": [{"type": "link", "attrs": {"href": part}}]
            })
        else:
            nodes.append({"type": "text", "text": part})
    return nodes


def text_to_adf_description(text):
    """Convert multi-line text into an ADF document body.

    Each paragraph (separated by blank lines) becomes its own ADF paragraph
    node. URLs within paragraphs are converted to clickable links.
    """
    paragraphs = re.split(r'\n{2,}', text.strip())
    content = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        content.append({
            "type": "paragraph",
            "content": text_to_adf_content(para)
        })
    return content


def create_jira_issue(jira_config, project, title, description=None, assignee_account_id=None):
    """Create a new Jira issue and return its key."""
    url = f"{jira_config.base_url}/rest/api/3/issue"
    auth = HTTPBasicAuth(jira_config.email, jira_config.api_token)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    fields = {
        "project": {"key": project},
        "summary": title,
        "description": {
            "type": "doc",
            "version": 1,
            "content": text_to_adf_description(description or title)
        },
        "issuetype": {"name": "Task"}
    }

    if assignee_account_id:
        fields["assignee"] = {"accountId": assignee_account_id}

    try:
        response = requests.post(url, json={"fields": fields}, headers=headers, auth=auth)

        if response.status_code == 201:
            return response.json()['key']
        else:
            raise Exception(f"Failed to create issue. Status: {response.status_code}, Response: {response.text}")

    except requests.exceptions.RequestException as e:
        raise Exception(f"Error connecting to Jira API: {e}")


def get_issue_summary(jira_config, issue_key):
    """Get issue summary from Jira API."""
    url = f"{jira_config.base_url}/rest/api/3/issue/{issue_key}"
    auth = HTTPBasicAuth(jira_config.email, jira_config.api_token)
    headers = {"Accept": "application/json"}

    try:
        response = requests.get(url, headers=headers, auth=auth, params={"fields": "summary"})

        if response.status_code == 200:
            return response.json()['fields']['summary']
        else:
            print(f"Warning: Could not fetch issue summary for {issue_key}. Status: {response.status_code}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"Warning: Error connecting to Jira API for issue {issue_key}: {e}")
        return None


def update_issue_description(jira_config, issue_key, description_text):
    """Update a Jira issue's description."""
    url = f"{jira_config.base_url}/rest/api/3/issue/{issue_key}"
    auth = HTTPBasicAuth(jira_config.email, jira_config.api_token)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    payload = {
        "fields": {
            "description": {
                "type": "doc",
                "version": 1,
                "content": text_to_adf_description(description_text)
            }
        }
    }

    response = requests.put(url, json=payload, headers=headers, auth=auth)

    if response.status_code not in (200, 204):
        print(f"Warning: Could not update issue description. Status: {response.status_code}")


# --- Slack ---

def find_channel_by_name(token, channel_name):
    """Find a Slack channel by name and return its ID."""
    channel_name = channel_name.lstrip('#')
    cursor = None
    url = 'https://slack.com/api/conversations.list'

    while True:
        params = {
            'types': 'public_channel,private_channel',
            'exclude_archived': 'true',
            'limit': 1000,
        }
        if cursor:
            params['cursor'] = cursor

        resp = requests.post(url, data=params, headers={
            'Authorization': f'Bearer {token}',
        })
        resp.raise_for_status()
        data = resp.json()

        if not data.get('ok'):
            raise Exception(f"Slack API error: {data.get('error', 'unknown')}")

        for ch in data.get('channels', []):
            if ch['name'] == channel_name:
                return ch['id'], ch['name']

        cursor = data.get('response_metadata', {}).get('next_cursor')
        if not cursor:
            break

    raise Exception(f"Slack channel '{channel_name}' not found")


def fetch_channel_members(token, channel_id):
    """Fetch all member user IDs from a Slack channel."""
    members = []
    cursor = None
    url = 'https://slack.com/api/conversations.members'

    while True:
        params = {
            'channel': channel_id,
            'limit': 1000,
        }
        if cursor:
            params['cursor'] = cursor

        resp = requests.post(url, data=params, headers={
            'Authorization': f'Bearer {token}',
        })
        resp.raise_for_status()
        data = resp.json()

        if not data.get('ok'):
            raise Exception(f"Slack API error fetching members: {data.get('error', 'unknown')}")

        members.extend(data.get('members', []))

        cursor = data.get('response_metadata', {}).get('next_cursor')
        if not cursor:
            break

    return members


def resolve_member_emails(slack_ids):
    """Resolve Slack user IDs to email addresses using whosename."""
    from whosename import name_of

    results = []
    for slack_id in slack_ids:
        try:
            email = name_of(slack_id, 'slack', 'email')
        except Exception:
            email = None
        results.append((slack_id, email))

    return results


def send_slack_notification(token, channel_id, title, description,
                            issue_key, issue_url, start_time, end_time,
                            meet_link=None):
    """Send a meeting notification to a Slack channel."""
    time_str = f"{start_time.strftime('%A, %B %d at %H:%M')} - {end_time.strftime('%H:%M')}"

    lines = [
        f":calendar: *{title}*",
        f":clock3: {time_str}",
    ]
    if description:
        lines.append(f"\n{description}")
    lines.append(f"<{issue_url}|{issue_key}>")
    if meet_link:
        lines.append(f"<{meet_link}|Google Meet>")

    text = '\n'.join(lines)

    resp = requests.post('https://slack.com/api/chat.postMessage', json={
        'channel': channel_id,
        'text': text,
    }, headers={
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    })
    resp.raise_for_status()
    data = resp.json()

    if not data.get('ok'):
        print(f"Warning: Could not send Slack message: {data.get('error', 'unknown')}")
    else:
        print(f"Sent meeting notification to Slack channel")


# --- Main ---

def main():
    """Main entry point for jira-calendar command."""
    arguments = docopt(__doc__, version=VERSION)

    # Parse arguments
    project_or_issue = arguments['PROJECT_OR_ISSUE'].upper()
    time_args = [arguments['TIME'], arguments.get('TIME_END')]
    time_args = [t for t in time_args if t is not None]
    day = arguments['DAY']
    duration_str = arguments.get('--duration', '1h')
    calendar_override = arguments.get('--calendar')
    slack_channel_arg = arguments.get('--slack')
    template_mode = arguments.get('--template', False)
    template_file = arguments.get('--file')

    # Default checkbox states from CLI flags
    default_assign = not arguments.get('--dont-assign', False)
    default_meet = not arguments.get('--no-google-meet', False)
    default_slack_msg = not arguments.get('--no-message', False)

    try:
        # Initialize configs
        jira_config = JiraConfigFile()
        google_config = WorkGoogleConfigFile()

        # Parse start time with local timezone
        start_time = parse_date_time(time_args[0], day)

        # Calculate end time
        if len(time_args) == 2:
            end_time_parts = time_args[1].split(':')
            end_hour = int(end_time_parts[0])
            end_minute = int(end_time_parts[1])
            end_time = start_time.replace(
                hour=end_hour, minute=end_minute, second=0, microsecond=0)
            if end_time <= start_time:
                raise ValueError("End time must be after start time")
        else:
            duration_seconds = parse_time_duration(duration_str)
            end_time = start_time + datetime.timedelta(seconds=duration_seconds)

        # Gather data for template
        summary = None
        attendee_emails = []
        slack_channel = None

        # Normalize slack channel name
        if slack_channel_arg:
            slack_channel = slack_channel_arg
            if not slack_channel.startswith('#'):
                slack_channel = f"#{slack_channel}"

        # Fetch existing issue summary
        if is_existing_issue(project_or_issue):
            issue_summary = get_issue_summary(jira_config, project_or_issue)
            if issue_summary:
                summary = issue_summary

        # Resolve Slack channel members (skip when using -f, data is in the file)
        if slack_channel and not template_file:
            slack_config = SlackConfigFile()

            print(f"Looking up Slack channel: {slack_channel}...")
            channel_id, resolved_name = find_channel_by_name(slack_config.token, slack_channel)
            print(f"Found channel: #{resolved_name}")

            print(f"Fetching channel members...")
            member_ids = fetch_channel_members(slack_config.token, channel_id)
            print(f"Found {len(member_ids)} members")

            print(f"Resolving email addresses...")
            members_with_emails = resolve_member_emails(member_ids)
            attendee_emails = [email for _, email in members_with_emails if email]
            print(f"Resolved {len(attendee_emails)} emails")

        # Generate template
        template = generate_template(
            project_or_issue, summary,
            slack_channel=slack_channel,
            attendee_emails=attendee_emails,
            google_meet=default_meet,
            assign_to_me=default_assign,
            slack_message=default_slack_msg,
        )

        # Template mode: print and exit
        if template_mode:
            print(template)
            return 0

        # Get template content: from file or editor
        if template_file:
            with open(template_file) as f:
                content = f.read()
        else:
            content = open_in_editor(template)

        # Parse the edited template
        config = parse_template(content)

        if not config.title:
            raise ValueError("Meeting title cannot be empty. Fill in the title after '#  KEY: '")

        # Resolve Slack channel ID if needed (for -f mode, channel comes from template)
        slack_config = None
        channel_id = None
        if config.slack_message and config.slack_channel:
            slack_config = SlackConfigFile()
            channel_id, _ = find_channel_by_name(slack_config.token, config.slack_channel)

        # Initialize calendar service and target calendar
        calendar_name_or_id = calendar_override or google_config.selected_calendar
        calendar_to_use = google_config.get_calendar_id(calendar_name_or_id)
        calendar_service = get_google_calendar_service(google_config)

        # Check attendee availability (including organizer's calendar)
        all_attendee_emails = config.attendees + config.optional_attendees
        freebusy_emails = [calendar_to_use] + all_attendee_emails
        if all_attendee_emails:
            duration = end_time - start_time
            local_tz = start_time.tzinfo

            while True:
                # Single freebusy query for the full day window
                day_start = datetime.datetime.combine(
                    start_time.date(), datetime.time(10, 0), tzinfo=local_tz)
                day_end = datetime.datetime.combine(
                    start_time.date(), datetime.time(17, 0), tzinfo=local_tz)

                print(f"Checking availability for {start_time.strftime('%Y-%m-%d %H:%M')} - {end_time.strftime('%H:%M')}...")
                busy_periods = query_freebusy(
                    calendar_service, freebusy_emails, day_start, day_end)
                conflicts = find_conflicts(busy_periods, start_time, end_time)

                if not conflicts:
                    print("All attendees are available.")
                    break

                print("\nFound conflicts:")
                for email, periods in conflicts.items():
                    for busy_start, busy_end in periods:
                        print(f"  - {email} ({busy_start.astimezone(local_tz).strftime('%H:%M')}-{busy_end.astimezone(local_tz).strftime('%H:%M')})")

                alternative = find_available_slot(
                    busy_periods, start_time.date(), duration, local_tz)

                if alternative:
                    alt_start, alt_end = alternative
                    print(f"\nFound another slot at {alt_start.strftime('%H:%M')} - {alt_end.strftime('%H:%M')}")
                    choice = input("([R]eserve, Cancel) > ").strip().lower()
                    if choice.startswith('c'):
                        print(f"\n{content}")
                        return 0
                    else:
                        start_time = alt_start
                        end_time = alt_end
                        break
                else:
                    print("\nCouldn't find suitable time slot on this day")
                    choice = input("([N]ext day, pick a Date, Cancel) > ").strip().lower()
                    if choice.startswith('n') or choice == '':
                        next_day = start_time.date() + datetime.timedelta(days=1)
                        while next_day.weekday() >= 5:  # skip Sat/Sun
                            next_day += datetime.timedelta(days=1)
                        start_time = datetime.datetime.combine(
                            next_day, start_time.timetz())
                        end_time = start_time + duration
                    elif choice.startswith('d') or choice.startswith('ch'):
                        new_day = input("Enter new day: ").strip()
                        start_time = parse_date_time(start_time.strftime('%H:%M'), new_day)
                        end_time = start_time + duration
                    else:
                        print(f"\n{content}")
                        return 0

        # Get account ID for assignment
        account_id = None
        if config.assign_to_me:
            account_id = get_myself(jira_config)

        # Handle Jira issue
        if is_existing_issue(project_or_issue):
            issue_key = project_or_issue
            print(f"Using existing issue: {issue_key}")
            if account_id:
                assign_issue(jira_config, issue_key, account_id)
                print(f"Assigned issue to me")
        else:
            print(f"Creating new issue in project {project_or_issue}...")
            issue_key = create_jira_issue(
                jira_config, project_or_issue, config.title,
                config.description, assignee_account_id=account_id)
            print(f"Created issue: {issue_key}")

        issue_url = f"{jira_config.base_url}/browse/{issue_key}"
        event_title = f"{issue_key}: {config.title}"

        # Build calendar event description
        cal_description_parts = []
        if config.description:
            cal_description_parts.append(config.description)
        cal_description_parts.append(f"Jira: {issue_url}")
        cal_description = '\n\n'.join(cal_description_parts)

        print(f"Creating calendar event for {start_time.strftime('%Y-%m-%d %H:%M')} - {end_time.strftime('%H:%M')}...")
        calendar_link, meet_link = create_calendar_event(
            calendar_service, calendar_to_use, start_time, end_time,
            event_title, cal_description,
            google_meet=config.google_meet, attendees=config.attendees,
            optional_attendees=config.optional_attendees,
        )

        print(f"✓ Issue: {issue_url}")
        print(f"✓ Calendar event: {calendar_link}")
        if meet_link:
            print(f"✓ Google Meet: {meet_link}")

        # Update Jira issue description with Meet link
        if meet_link:
            jira_desc_parts = []
            if config.description:
                jira_desc_parts.append(config.description)
            jira_desc_parts.append(f"Google Meet: {meet_link}")
            update_issue_description(jira_config, issue_key, '\n\n'.join(jira_desc_parts))

        # Send Slack notification
        if config.slack_message and channel_id:
            send_slack_notification(
                slack_config.token, channel_id,
                event_title, config.description,
                issue_key, issue_url,
                start_time, end_time, meet_link,
            )

    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0

if __name__ == '__main__':
    exit(main())
