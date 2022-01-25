"""Get wishes for someone.

Usage: 
    wish [options]

Options:
    --plural         Display plural wishes.
    -h, --help       Show this message.
    --version        Show version information.
"""

URL="https://cudowne.zyczenia.online/wishes/get?isPlural={is_plural}"

import json, os, re, sys

from docopt import docopt

from datetime import datetime

import tempfile

import subprocess

import requests


def main():
    arguments = docopt(__doc__, version='1.0')

    url = URL.format(
        is_plural='true' if arguments['--plural'] else 'false'
    )

    r = requests.get(url)

    if r.ok:
        print(r.json()['content'])
    else:
        try:
            print(json.dumps(r.json(), indent=4, sort_keys=True))
        except json.decoder.JSONDecodeError:
            print("HTTP {}\n{}".format(r.status_code, r.text))



        
            

            
