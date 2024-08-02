"""Add journal entry.

Usage: 
    journal [options]

Options:
    -o               Also save a copy as observation.
    -t THREAD, --thread THREAD  Use this thread [default: Daily]
    -h, --help       Show this message.
    --version        Show version information.
"""

TEMPLATE = """
> Thread: {thread}
> Published: {published}

# Comment

{comment}

"""

GOTOURL = """
See more:
- {url}/
"""

import json, os, re, sys

from docopt import docopt

from datetime import datetime, date

import tempfile

import subprocess

import requests
from requests.exceptions import ConnectionError

from requests.auth import HTTPBasicAuth

from pathlib import Path

from .config.tasks import TasksConfigFile


def template_from_arguments(arguments):
    return TEMPLATE.format(
        comment='',
        published=datetime.now(),
        thread=arguments['--thread'],
    ).lstrip()


def template_from_payload(payload):
    return TEMPLATE.format(**payload).lstrip()

title_re = re.compile(r'^# (Comment)')
meta_re = re.compile(r'^> (Thread|Published): (.*)$')


def add_meta_to_payload(payload, name, item):
    payload[name.lower()] = item

def add_stack_to_payload(payload, name, lines):
    payload[name.lower()] = ''.join(lines).strip()


DEAD_LETTER_DIRECTORY = os.path.expanduser(os.path.join('~', '.tasks', 'queue'))


def queue_dead_letter(payload, path, metadata):
    if not os.path.exists(path):
        os.makedirs(path)

    basename = "{}".format(datetime.now().strftime("%Y-%m-%d_%H%M%S_journal"))
    name = f'{basename}.json'
    i = 0

    while os.path.exists(name):
        i += 1
        name = f'{basename}-{i}.json'

    with open(os.path.join(path, name), "w") as f:
        json.dump({
            'payload': payload,
            'meta': metadata
        }, f)
    
    return name

def send_dead_letter(path, _metadata):
    metadata = _metadata.copy()

    print(f"Attempting to send {path}...")

    with open(path) as f:        
        data = json.load(f)


        metadata.update(data['meta'])
        payload = data['payload']

        requests.post(metadata['url'], json=payload, auth=metadata['auth'])

    os.unlink(path)


def send_dead_letters(path, metadata):
    for root, dirs, files in os.walk(path):
        for name in sorted(files):
            send_dead_letter(os.path.join(root, name), metadata)

def main():
    arguments = docopt(__doc__, version='1.0.2')

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
        'comment': None,
        'thread': arguments['--thread'],
        'published': datetime.now(),
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


    if payload['comment'] == '':
        print("No changes were made to the Comment field.")

        os.unlink(tmpfile.name)

        sys.exit(0)

    try:
        send_dead_letters(DEAD_LETTER_DIRECTORY, metadata={
            'auth': HTTPBasicAuth(config.user, config.password)
        })
    except Exception as e:
        print(e)
        print("Error: Failed to send queue")

    url = '{}/journal/'.format(config.url)

    try:
        r = requests.post(url, json=payload, auth=HTTPBasicAuth(config.user, config.password))

        if arguments['-o']:
            url = '{}/observation-api/'.format(config.url)

            new_payload = {
                'situation': payload['comment'],
                'thread': arguments['--thread'],
                'pub_date': str(date.today()),
                'type': 'observation',
            }

            r2 = requests.post(url, json=new_payload, auth=HTTPBasicAuth(config.user, config.password))

            if r2.ok:
                print("Saved observation under id {}".format(r2.json()['id']))
            else:
                try:
                    print(json.dumps(r2.json(), indent=4, sort_keys=True))
                except json.decoder.JSONDecodeError:
                    print("HTTP {}\n{}".format(r2.status_code, r2.text))
        

    except ConnectionError:
        name = queue_dead_letter(payload, path=DEAD_LETTER_DIRECTORY, metadata={
            'url': url,            
        })

        print("Error: Connection failed.")
        print(f"Your update was saved at {name}.")
        print("It will be sent next time you run this program.")

        sys.exit(2)

    if r.ok:
        new_payload = r.json()

        print(template_from_payload(new_payload))

        print(GOTOURL.format(url=config.url).strip())

        os.unlink(tmpfile.name)
    else:
        try:
            print(json.dumps(r.json(), indent=4, sort_keys=True))
        except json.decoder.JSONDecodeError:
            print("HTTP {}\n{}".format(r.status_code, r.text))
        
        print("The temporary file was saved at {}".format(
            tmpfile.name
        ))



        
            

            
