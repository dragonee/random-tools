"""List Calamari absences for a team of people in a given period.

Usage:
    calamari-absences [options] EMPLOYEE...

Options:
    -d, --from-date DATE    Start date (YYYY-MM-DD) [default: today].
    -D, --to-date DATE      End date (YYYY-MM-DD) [default: today].
    --month                 Current calendar month.
    --week                  Current calendar week.
    -Y, --last              Previous period (with --month or --week).
    -t, --team TEAM         Filter by team name (can be repeated).
    -s, --status STATUS     Filter by status: PENDING, ACCEPTED, REJECTED [default: ACCEPTED].
    -h, --help              Show this message.
    --version               Show version information.

Examples:
    calamari-absences --month alice@example.com bob@example.com
    calamari-absences --week --last alice@example.com
    calamari-absences -d 2026-03-01 -D 2026-03-31 alice@example.com

Configuration:
    Create ~/.calamari/config.ini:

    [Calamari]
    tenant = your-tenant-name
    api_key = your-api-key
"""

import sys
import datetime
from itertools import groupby

from docopt import docopt
import dateparser
import requests
from requests.auth import HTTPBasicAuth

from .config.calamari import CalamariConfigFile

VERSION = '1.0'


def parse_date(value):
    if value == 'today':
        return datetime.date.today()
    parsed = dateparser.parse(value)
    if parsed is None:
        print(f"Cannot parse date: {value}", file=sys.stderr)
        sys.exit(1)
    return parsed.date()


def resolve_period(arguments):
    today = datetime.date.today()

    if arguments['--month']:
        if arguments['--last']:
            first = today.replace(day=1) - datetime.timedelta(days=1)
            date_from = first.replace(day=1)
            date_to = first
        else:
            date_from = today.replace(day=1)
            next_month = today.replace(day=28) + datetime.timedelta(days=4)
            date_to = next_month.replace(day=1) - datetime.timedelta(days=1)
    elif arguments['--week']:
        monday = today - datetime.timedelta(days=today.weekday())
        if arguments['--last']:
            monday -= datetime.timedelta(weeks=1)
        date_from = monday
        date_to = monday + datetime.timedelta(days=6)
    else:
        date_from = parse_date(arguments['--from-date'])
        date_to = parse_date(arguments['--to-date'])

    return date_from, date_to


def fetch_absences(config, employees, date_from, date_to, statuses=None):
    url = f"{config.base_url}/leave/request/v1/find-advanced"
    auth = HTTPBasicAuth('calamari', config.api_key)

    body = {
        'from': date_from.isoformat(),
        'to': date_to.isoformat(),
        'employees': employees,
    }

    if statuses:
        body['absenceStatuses'] = statuses

    resp = requests.post(url, json=body, auth=auth, headers={
        'Content-Type': 'application/json',
    })
    resp.raise_for_status()
    return resp.json()


def format_absence(absence):
    date_from = datetime.date.fromisoformat(absence['from'])
    date_to = datetime.date.fromisoformat(absence['to'])

    if date_from == date_to:
        label = date_from.strftime('%Y-%m-%d')
        if not absence.get('fullDayRequest', True):
            label += " (half day)"
        return label

    days = (date_to - date_from).days + 1
    return f"{date_from.strftime('%Y-%m-%d')}\u2013{date_to.strftime('%Y-%m-%d')} ({days} days)"


def main():
    arguments = docopt(__doc__, version=VERSION)

    try:
        config = CalamariConfigFile()
    except KeyError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    employees = arguments['EMPLOYEE']
    date_from, date_to = resolve_period(arguments)

    status_arg = arguments['--status']
    statuses = [s.strip() for s in status_arg.split(',')] if status_arg else None

    try:
        absences = fetch_absences(config, employees, date_from, date_to, statuses)
    except requests.HTTPError as e:
        print(f"API error: {e}", file=sys.stderr)
        if e.response is not None:
            print(e.response.text, file=sys.stderr)
        return 1

    # Group by employee
    sorted_absences = sorted(absences, key=lambda a: a.get('employeeEmail', ''))

    any_printed = False
    for employee, group in groupby(sorted_absences, key=lambda a: a.get('employeeEmail', '')):
        entries = sorted(group, key=lambda a: a['from'])
        if not entries:
            continue

        if any_printed:
            print()
        any_printed = True

        print(f"{employee}:")
        for absence in entries:
            line = format_absence(absence)
            absence_type = absence.get('absenceTypeName', '')
            if absence_type:
                line += f" [{absence_type}]"
            print(f"  - {line}")

    if not any_printed:
        print(f"No absences found for {date_from} to {date_to}.")
