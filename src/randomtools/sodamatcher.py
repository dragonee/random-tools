"""
Match SoDA members e-mails with GUID map. Output a new CSV file.

Usage:
    sodamatcher [options] IN_CSVFILE MAPFILE

Options:
    -p MAP           Persist JSON map.
    --no-drop-first  Drop first row in CSV file.
    --default FILE   Present this file for match [default: default.pdf].
    --column NUM     Use this column, zero-indexed [default: 2].  
    -h, --help  Show this message.
    --version   Show version information.
"""

from pathlib import Path

from docopt import docopt

from shutil import copy

import os
import csv

import json

import re

from thefuzz import process

number_regexp = re.compile(r'^(0|1|2|3|4)$') 


pattern = "https://sodaconf2021.makimo.pl/{file}"

def remvovefilesuffix(name):
    return '.'.join(name.split('.')[:-1])

def main():
    arguments = docopt(__doc__, version='1.0')

    in_csv_path = Path(arguments['IN_CSVFILE']).resolve(strict=True)
    map_path = Path(arguments['MAPFILE']).resolve(strict=True)

    with open(str(map_path)) as map_file:
        guid_dict = json.load(map_file)
    
    choice_dict = {remvovefilesuffix(k): v for k,v in guid_dict.items()}
    choices = choice_dict.keys()

    column_number = int(arguments['--column'])

    print(choices)

    new_rows = []

    link_map = {}

    if map_path := arguments['-p']:
        if os.path.exists(map_path):
            with open(map_path) as map_file:
                link_map = json.load(map_file)

    with open(str(in_csv_path)) as input_csv:
        reader = csv.reader(input_csv)

        first_row = True

        try:
            for row in reader:
                if first_row and not arguments['--no-drop-first']:
                    first_row = False
                    continue
                
                email = row[column_number]

                if email in link_map:
                    continue

                print(row)

                tuples = process.extract(email, choices, limit=5)

                for i, item in enumerate(tuples):
                    print("{}) {} ({}%)".format(i, item[0], item[1]))

                text = input("Choice [number/filename/D/S]: ").strip()
                
                if text == 's' or text == 'S':
                    link = None
                elif text == 'd' or text == 'D':
                    link = guid_dict[arguments['--default']]
                elif number_regexp.match(text):
                    link = choice_dict[tuples[int(text)][0]]
                else:
                    link = guid_dict[text]

                if link:
                    link = pattern.format(file=link)

                link_map[email] = link
        except KeyboardInterrupt:
            pass

    if map_path := arguments['-p']:
        with open(map_path, 'w') as map_file:
            json.dump(link_map, map_file)