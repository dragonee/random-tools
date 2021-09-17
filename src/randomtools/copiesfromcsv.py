"""
Usage: 
copiesfromcsv [options] CSVFILE INFILE 

Options:
    --column N    Use specific column, zero-indexed [default: 0]
    --drop-first  Drop first line.
    -h, --help  Show this message.
    --version   Show version information.

"""

import csv, os

from pathlib import Path

from docopt import docopt

from shutil import copy

def main():
    arguments = docopt(__doc__, version='1.0')

    with open(arguments['CSVFILE'], 'r') as f:
        reader = csv.reader(f, delimiter=';')

        path = Path(arguments['INFILE']).resolve(strict=True)
        parent = path.parent

        first = True

        for row in reader:
            if arguments['--drop-first'] and first:
                first = False
                continue

            name = row[int(arguments['--column'])].strip()

            new_path = parent / '{}{}'.format(
                name,
                path.suffix
            )

            print("Copying {} into {}...".format(
                str(path), 
                str(new_path)
            ))

            copy(str(path), str(new_path))
            

            
