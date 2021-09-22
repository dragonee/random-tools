"""
Convert a JSON map dictionary into CSV file with two columns

Usage:
    maptocsv [options] JSONMAP OUTFILE

Options:
    -k KEY_TITLE    Use the following for the first column of title row of CSV file.
    -v VALUE_TITLE  Use the following for the second column of title row of CSV file.
    -h, --help  Show this message.
    --version   Show version information.
"""

from pathlib import Path

from docopt import docopt

import os

import json

import csv

from collections import OrderedDict

def main():
    arguments = docopt(__doc__, version='1.0')

    out_file = Path(arguments['OUTFILE']).resolve()
    map_path = Path(arguments['JSONMAP']).resolve(strict=True)

    map_dict = {}
    with open(str(map_path)) as map_file:
        map_dict = json.load(map_file, object_pairs_hook=OrderedDict)

    with open(str(out_file), 'w') as output_csv:
        writer = csv.writer(output_csv)

        if arguments['-k'] or arguments['-v']:
            title_row = [
                arguments['-k'] or '',
                arguments['-v'] or '',
            ]

            writer.writerow(title_row)

        for key, value in map_dict.items():
            writer.writerow([key, value])
            
        

