"""
Append a JSON map to a CSV column.

Usage:
    maptocsvcolumn [options] INFILE JSONMAP OUTFILE

Options:
    --first-row TEXT  Use the following for the first row in CSV file.
    --column NUM      Use this column as map key [default: 2].
    -h, --help  Show this message.
    --version   Show version information.
"""

from pathlib import Path

from docopt import docopt

import os

import json

import csv

def main():
    arguments = docopt(__doc__, version='1.0')

    in_file = Path(arguments['INFILE']).resolve(strict=True)
    out_file = Path(arguments['OUTFILE']).resolve()
    map_path = Path(arguments['JSONMAP']).resolve(strict=True)

    map_dict = {}
    with open(str(map_path)) as map_file:
        map_dict = json.load(map_file)

    column = int(arguments['--column'])

    with open(str(in_file)) as input_csv:
        reader = csv.reader(input_csv)

        with open(str(out_file), 'w') as output_csv:
            writer = csv.writer(output_csv)

            first_row = True

            for row in reader:
                key = row[column]

                text = ''

                if first_row and arguments['--first-row']:
                    text = arguments['--first-row']
                    first_row = False

                else:
                    try:
                        text = map_dict[key]

                        if text is None:
                            text = ''
                    except KeyError:
                        print("Not found: {}".format(key))

                writer.writerow(row + [text])
                
        

