"""Dump observations to markdown files.

Usage: 
    observationdump [options] PATH

Options:
    --open           Get only open observations.
    --closed         Get only closed observations.
    -d DATE_FROM, --from FROM  Dump from specific date.
    -D DATE_TO, --to DATE_TO   Dump to specific date.
    -f, --force      Overwrite existing files.
    --pk ID          Dump object with specific ID.
    --year YEAR      Dump specific year.
    -h, --help       Show this message.
    --version        Show version information.
"""

VERSION = '1.0.3'

import json, os, re, sys, pprint

from docopt import docopt

from datetime import datetime

import tempfile

import subprocess

import requests
from requests.auth import HTTPBasicAuth

from pathlib import Path

from .config.tasks import TasksConfigFile

from slugify import slugify


TEMPLATE = """
> Date: {pub_date}
> Thread: {thread}
> Type: {type}

# Situation (What happened?)

{situation}

# Interpretation (How you saw it, what you felt?)

{interpretation}

# Approach (How should you approach it in the future?)

{approach}

"""

CLOSED_TEMPLATE = """
> Closed on {date_closed}
"""

def closed(payload):
    if not payload['date_closed']:
        return ''
    
    return CLOSED_TEMPLATE.format(**payload).lstrip()


def template_from_payload(payload):
    return TEMPLATE.format(**payload).lstrip() + closed(payload)


def write_observation(observation, path, force=False):
    text = template_from_payload(observation)

    filename = '{}-{}.md'.format(
        observation['pub_date'],
        slugify(observation['situation'], max_length=32, word_boundary=True)
    )

    new_file = path / filename

    if new_file.exists() and not force:
        return

    with open(path / filename, 'w') as f:
        f.write(text)
    
    return filename


def main():
    arguments = docopt(__doc__, version=VERSION)

    directory = Path(arguments['PATH']).resolve(strict=True)

    config = TasksConfigFile()

    single = False

    filter_arg = ''

    if arguments['--year']:
        year = arguments['--year']

        filter_arg = f'?pub_date__gte={year}-01-01&pub_date__lte={year}-12-31'
    elif arguments['--pk']:
        filter_arg = '{}/'.format(arguments['--pk'])

        single = True
    elif arguments['--from']:
        date_from = arguments['--from']
        date_to = arguments['--to'] or datetime.today().strftime('%Y-%m-%d')

        filter_arg = f'?pub_date__gte={date_from}&pub_date__lte={date_to}'

    if not single:
        if arguments['--open']:
            filter_arg += '&date_closed__isnull=true'
        elif arguments['--closed']:
            filter_arg += '&date_closed__isnull=false'

    url = '{}/observation-api/{}'.format(config.url, filter_arg)

    auth = HTTPBasicAuth(config.user, config.password)

    while url:
        r = requests.get(url, auth=auth)

        out = r.json()

        if not r.ok:
            raise RuntimeError("{}: {}".format(r.status_code, str(out)))

        if not 'results' in out:
            out = {
                'results': [out],
                'next': None
            }

        for item in out['results']:
            filename = write_observation(item, directory, force=arguments['--force'])

            if filename:
                print('Create {}'.format(filename))

        url = out['next']

