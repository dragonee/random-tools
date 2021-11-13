"""Add a journal entry.

Usage: 
    journal [options]

Options:
    --date DATE      Use specific date.
    --thread THREAD  Use specific thread [default: Daily].
    --weekly         Alias for --thread weekly
    --big-picture    Alias for --thread big-picture
    -h, --help       Show this message.
    --version        Show version information.
"""

TEMPLATE = """
> Date: {pub_date}
> Thread: {thread}

- [{dreamstate}] Dreamstate
- [{current_in_sync}] Current plan in-sync
- [{next_in_sync}] Next plan in-sync

# Current plan

## Focus

{current_focus}

## Want

{current_want}

# Reflection

## Good (What did you do well today?)

{good}

# Better (How could you improve? What could you do better?)

{better}

# Best (How should you approach it in the future?)

{best}

# Next plan

## Focus

{next_focus}

## Want

{next_want}

"""

GOTOURL = """
See more:
- {url}/periodical/
"""

import json, os, re, sys

from docopt import docopt

from datetime import datetime

import tempfile

import subprocess

import requests
from requests.auth import HTTPBasicAuth

from pathlib import Path

from .config import TasksConfigFile


def template_from_arguments(arguments):
    if arguments['--weekly']:
        thread = 'Weekly'
    elif arguments['--big-picture']:
        thread = 'big-picture'
    else:
        thread = arguments['--thread']


    return TEMPLATE.format(
        pub_date=arguments['--date'] or datetime.today().strftime('%Y-%m-%d'),
        thread=thread,
        good='',
        better='',
        best='',
        dreamstate=' ',
        current_focus='',
        current_want='',
        current_in_sync=' ',
        next_focus='',
        next_want='',
        next_in_sync=' ',
    ).lstrip()


def template_from_payload(payload):
    return TEMPLATE.format(**payload).lstrip()


title_re = re.compile(r'^# (Good|Better|Best)')
meta_re = re.compile(r'^> (Date|Thread|Type): (.*)$')


def add_meta_to_payload(payload, name, item):
    if name == 'Date':
        name = 'pub_date'

    payload[name.lower()] = item


def add_stack_to_payload(payload, name, lines):
    payload[name.lower()] = ''.join(lines).strip()
        

def main():
    arguments = docopt(__doc__, version='1.0')

    config = TasksConfigFile()

    tmpfile = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.md')

    template = template_from_arguments(arguments)

    with tmpfile:
        tmpfile.write(template)
    
    editor = os.environ.get('EDITOR', 'vim')

    result = subprocess.run([
        editor, tmpfile.name
    ])

    if result.returncode != 0:
        sys.exit(1)

    payload = {
        'pub_date': None,
        'thread': None,
        'type': None,
        'situation': None,
        'interpretation': None,
        'approach': None,
    }

    with open(tmpfile.name) as f:
        current_name = None
        current_stack = []

        for line in f:
            if m := meta_re.match(line):
                add_meta_to_payload(payload, m.group(1).strip(), m.group(2).strip())
            elif m := title_re.match(line):
                if current_name is not None:
                    add_stack_to_payload(payload, current_name, current_stack)
                
                current_name = m.group(1).strip()
                current_stack = []
            else:
                current_stack.append(line)
    
        if current_name is not None:
            add_stack_to_payload(payload, current_name, current_stack)

    os.unlink(tmpfile.name)

    if payload['situation'] == '':
        print("No changes were made to the Situation field.")
        sys.exit(0)

    url = '{}/observation-api/'.format(config.url)

    r = requests.post(url, json=payload, auth=HTTPBasicAuth(config.user, config.password))

    if r.ok:
        print(template_from_payload(r.json()))

        print(GOTOURL.format(url=config.url).strip())
    else:
        try:
            print(json.dumps(r.json(), indent=4, sort_keys=True))
        except json.decoder.JSONDecodeError:
            print("HTTP {}\n{}".format(r.status_code, r.text))


        
            

            
