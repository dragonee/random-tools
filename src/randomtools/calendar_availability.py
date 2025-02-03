"""Check if I'm free in the evening.

Usage: 
    evenings [options]

Options:
    -S, --stats           Show statistics.
    -T, --type TYPE       Type of evenings to check. free/busy/all [default: free].
    -a, --all             Alias for --type all.
    -d, --days DAYS       Number of days to check [default: 14].
    -s, --start DATE      Start date
    --hour-from HOUR      Start hour [default: 18].
    --hour-to HOUR        End hour [default: 22].
    -h, --help       Show this message.
    --version        Show version information.
"""

import datetime
import os
import pickle
from typing import List, Union

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from pydantic import BaseModel
from pprint import pprint
from docopt import docopt

from .config.google import GoogleConfigFile


SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']


# -------------------------------
# Pydantic Models
# -------------------------------
class CalendarEvent(BaseModel):
    id: str
    summary: str = "No Title"
    start: Union[datetime.datetime, datetime.date]
    end: Union[datetime.datetime, datetime.date]


class Day(BaseModel):
    date: datetime.date
    events: List[CalendarEvent] = []

    def is_available(self) -> bool:
        """Return True if no events are scheduled in the evening."""
        return len(self.events) == 0

    def status(self) -> str:
        """Return a simple status message."""
        return "Available" if self.is_available() else "Busy"


def parse_event(event: dict) -> CalendarEvent:
    """
    Convert a Google Calendar API event dict into a CalendarEvent model.
    It checks for either 'dateTime' (for timed events) or 'date' (for all-day events).
    """
    
    start_str = event.get('start', {}).get('dateTime') or event.get('start', {}).get('date')
    end_str = event.get('end', {}).get('dateTime') or event.get('end', {}).get('date')

    return CalendarEvent(
        id=event.get('id'),
        summary=event.get('summary', 'No Title'),
        start=start_str,
        end=end_str,
    )


def authorize(
        token_path: str = 'token.pickle',
        credentials_path: str = 'credentials.json',
        scopes: List[str] = SCOPES,
    ):
    """Check if we have valid credentials."""

    creds = None
    if os.path.exists(token_path):
        with open(token_path, 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, scopes)
            creds = flow.run_local_server(port=0)

        with open(token_path, 'wb') as token:
            pickle.dump(creds, token)

    return creds


def print_stats(days: List[Day]):
    print(f"Total days: {len(days)}")
    print(f"Free days: {len(list(filter(lambda d: d.is_available(), days)))}")
    print(f"Busy days: {len(list(filter(lambda d: not d.is_available(), days)))}")


def main():
    arguments = docopt(__doc__, version='1.0')

    config = GoogleConfigFile()

    creds = authorize(
        token_path=config.token_path,
        credentials_path=config.credentials_path,
    )

    service = build('calendar', 'v3', credentials=creds)

    days_to_check = int(arguments['--days'])

    hour_from = datetime.time(int(arguments['--hour-from']), 0)
    hour_to = datetime.time(int(arguments['--hour-to']), 0)

    now = datetime.datetime.now()

    if now.hour > 18:
        now = now + datetime.timedelta(days=1)

    local_tz = now.astimezone().tzinfo
    today = datetime.datetime.strptime(arguments['--start'], '%Y-%m-%d').date() if arguments['--start'] else now.date()


    calendars_result = service.calendarList().list().execute()
    calendars = calendars_result.get('items', [])
    if not calendars:
        print("No calendars found.")
        return
    
    filtered_calendars = list(filter(lambda c: c['summary'] in config.selected_calendars, calendars))

    # A list to store Day objects.
    days = []

    for i in range(days_to_check):
        day_date = today + datetime.timedelta(days=i)
        day_model = Day(date=day_date, events=[])  # Start with no events for this day

        naive_start = datetime.datetime.combine(day_date, hour_from)
        naive_end = datetime.datetime.combine(day_date, hour_to)

        evening_start = naive_start.astimezone(local_tz)
        evening_end = naive_end.astimezone(local_tz)

        time_min = evening_start.isoformat()
        time_max = evening_end.isoformat()

        for calendar in filtered_calendars:
            calendar_id = calendar.get('id')
            calendar_name = calendar.get('summary')

            try:
                events_result = service.events().list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
            except Exception as e:
                print(f"Error retrieving events for calendar {calendar_name}: {e}")
                continue

            events = events_result.get('items', [])

            # Convert each event to our internal CalendarEvent model.
            for event in events:
                try:
                    event_model = parse_event(event)
                    day_model.events.append(event_model)
                except Exception as e:
                    print(f"Error parsing event: {event}\nError: {e}")

        days.append(day_model)

    if arguments['--stats']:
        print_stats(days)
        return

    if arguments['--all']:
        arguments['--type'] = 'all'

    if arguments['--type'] == 'free':
        days = list(filter(lambda d: d.is_available(), days))
    elif arguments['--type'] == 'busy':
        days = list(filter(lambda d: not d.is_available(), days))


    for day in days:
        if arguments['--type'] == 'all':
            print(f"{day.date.strftime('%Y-%m-%d (%A)')} - {day.status()}")
        else:
            print(f"{day.date.strftime('%Y-%m-%d (%A)')}")

        for event in day.events:
            print(f"  {event.start.strftime('%H:%M')} - {event.end.strftime('%H:%M')}: {event.summary}")
        
        if arguments['--type'] == 'all' or arguments['--type'] == 'busy':
            print()

