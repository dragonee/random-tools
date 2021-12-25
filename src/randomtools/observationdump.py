"""Dump observations to markdown files.

Usage: 
    observationdump [options] PATH

Options:
    --year YEAR      Dump specific year.
    -h, --help       Show this message.
    --version        Show version information.
"""

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

def template_from_payload(payload):
    return TEMPLATE.format(**payload).lstrip()


def write_observation(observation, path):
    text = template_from_payload(observation)

    filename = '{}-{}.md'.format(
        observation['pub_date'],
        slugify(observation['situation'], max_length=32, word_boundary=True)
    )

    with open(path / filename, 'w') as f:
        f.write(text)
    
    return filename


def main():
    arguments = docopt(__doc__, version='1.0')

    directory = Path(arguments['PATH']).resolve(strict=True)

    config = TasksConfigFile()

    date_filter = ''

    if arguments['--year']:
        year = arguments['--year']

        date_filter = f'?pub_date__gte={year}-01-01&pub_date__lte={year}-12-31'

    url = '{}/observation-api/{}'.format(config.url, date_filter)

    auth = HTTPBasicAuth(config.user, config.password)

    while url:
        r = requests.get(url, auth=auth)

        out = r.json()

        for item in out['results']:
            filename = write_observation(item, directory)

            print('Create {}'.format(filename))

        url = out['next']

