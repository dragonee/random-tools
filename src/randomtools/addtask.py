"""Add a task.

Usage: 
    addtask [options] TEXT

Options:
    --thread THREAD  Use specific thread [default: Daily].
    -h, --help       Show this message.
    --version        Show version information.
"""

GOTOURL = """
See more:
- {url}/hello/world/
"""

import json, os, re, sys

from docopt import docopt

from datetime import datetime

import tempfile

import subprocess

import requests
from requests.auth import HTTPBasicAuth


from pathlib import Path

from .config.tasks import TasksConfigFile


def main():
    arguments = docopt(__doc__, version='1.0.1')

    config = TasksConfigFile()

    payload = {
        'thread-name': arguments['--thread'],
        'text': arguments['TEXT'],
    }

    url = '{}/boards/append/'.format(config.url)

    r = requests.post(url, json=payload, auth=HTTPBasicAuth(config.user, config.password))

    if r.ok:
        print("Task added.")

        print(GOTOURL.format(url=config.url).strip())
    else:
        try:
            print(json.dumps(r.json(), indent=4, sort_keys=True))
        except json.decoder.JSONDecodeError:
            print("HTTP {}\n{}".format(r.status_code, r.text))



        
            

            
