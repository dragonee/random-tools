"""
List usecases from Markdown files as Markdown list.

Usage: 
    usecase [options] PATH

Options:
    -h, --help       Show this message.
    --version        Show version information.

Scenario file format:

# (vX.Y)            <- version, optional

## X. Something     <- a case

## X. .Hidden       <- This will not show up

## Cases

1. Some case        <- short notation
2. Some other case  <- can also be placed on top of file

"""


import os, re, sys

from docopt import docopt

from pathlib import Path

from dataclasses import dataclass


@dataclass
class Case:
    name: str
    simple: bool
    original_enumeration: str
    version: str = ''


@dataclass
class Scenario:
    path: Path
    cases: list[Case]


re_version = re.compile(r'^#{1,3} \(v([\d\.\-\w]+)\)')
re_cases = re.compile(r'^#{1,3} Cases')
re_case = re.compile(r'^#{1,3} (\d+)\. (.+)$')

re_case_simple = re.compile(r'^(\d+)\. (.+)$')


def read_file(filename):
    in_cases = True

    case_dict = {'version': ''}

    cases = []

    with open(filename, 'r') as f:
        for line in f.readlines():
            if m := re_version.match(line):
                case_dict['version'] = m.group(1)
                in_cases = False
            elif m := re_cases.match(line):
                in_cases = True
            elif m := re_case.match(line):
                if m.group(2).startswith('.'):
                    continue

                case_dict['name'] = m.group(2)
                case_dict['original_enumeration'] = m.group(1)
                cases.append(Case(**case_dict, simple=False))
            elif in_cases and (m := re_case_simple.match(line)):
                case_dict['name'] = m.group(2)
                case_dict['original_enumeration'] = m.group(1)
                cases.append(Case(**case_dict, simple=True))
            elif line.startswith('#'):
                in_cases = False
    
    if len(cases) == 0:
        return None

    return Scenario(cases=cases, path=filename)


def print_scenario(scenario, relative_to=None):
    path = scenario.path

    if relative_to:
        path = path.relative_to(relative_to)

    print('{}:'.format(path))
    
    for i, case in enumerate(scenario.cases, start=1):
        if case.version:
            version_string = ' ({})'.format(case.version)
        else:
            version_string = ''

        print('{}. {}{}'.format(i, case.name, version_string))
    
    print('')


def print_scenarios(scenarios, relative_to=None):
    for scenario in scenarios:
        print_scenario(scenario, relative_to)


def main():
    arguments = docopt(__doc__, version='1.0')

    filename = Path(arguments['PATH']).resolve(strict=True)

    if filename.is_dir():
        paths = filename.glob('**/*.md')
    else:
        paths = [filename]

    scenarios = []

    for path in paths:
        if scenario := read_file(path):
            scenarios.append(scenario)

    print_scenarios(
        scenarios, 
        filename if filename.is_dir() else filename.parent
    )
