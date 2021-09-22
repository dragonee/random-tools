"""
Copy files in directory to GUID generated files.

Usage:
    movetoguids [options] IN_DIRECTORY OUT_DIRECTORY

Options:
    -p MAP      Persist files in a JSON map.
    -h, --help  Show this message.
    --version   Show version information.
"""

from pathlib import Path

from docopt import docopt

from shutil import copy

import os

import json
from uuid import uuid4

def main():
    arguments = docopt(__doc__, version='1.0')

    in_directory = Path(arguments['IN_DIRECTORY']).resolve(strict=True)
    out_directory = Path(arguments['OUT_DIRECTORY']).resolve(strict=True)

    guid_dict = {}

    if map_path := arguments['-p']:
        if os.path.exists(map_path):
            with open(map_path) as map_file:
                guid_dict = json.load(map_file)

    for path in in_directory.iterdir():
        if path.name not in guid_dict:
            guid_dict[path.name] = "{}{}".format(
                str(uuid4()),
                path.suffix
            )
        
        out_file = out_directory / guid_dict[path.name]

        if not out_file.exists():
            print("Copy {} to {}".format(
                str(path), str(out_file)
            ))

            copy(str(path), str(out_file))
    
    if map_path := arguments['-p']:
        with open(map_path, 'w') as map_file:
            json.dump(guid_dict, map_file)