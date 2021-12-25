"""
List usecases from Markdown files as Markdown list.

Usage: 
    usecase [options] PATH

Options:
    -h, --help       Show this message.
    --version        Show version information.
"""


GOTOURL = """
See more:
- {url}/observations/
"""

import json, os, re, sys, pprint

from docopt import docopt

from datetime import datetime

import tempfile

import subprocess

import requests
from requests.auth import HTTPBasicAuth

from pathlib import Path

from .config.tasks import TasksConfigFile

from mistletoe import Document, ast_renderer

from dataclasses import dataclass

from enum import Enum

def threads_to_dict(response):
    thread_f = lambda thread: (thread['name'], thread['id'])

    return dict(map(thread_f, response['results']))


def get_board_meta(response):
    board = response['results'][0]

    return {
        'focus': board['focus'],
        'date_started': board['date_started'],
        'date_closed': board['date_closed'],
        'id': board['id'],
    }


def get_state_tree(response):
    return response['results'][0]['state']


def empty_enumerator(path):
    return ''


def dotted_enumerator(path):
    return ' {}.'.format('.'.join(map(str, path)))


def state_func(item):
    is_category = '☐' if len(item['children']) == 0 else ''

    made_progress = '~' if item['data']['meaningfulMarkers']['madeProgress'] else is_category

    return '{} '.format(
        '✓' if item['state']['checked'] else made_progress
    )


def importance(item):
    imp = item['data']['meaningfulMarkers']['important']

    if imp > 0:
        return ' ({})'.format('!' * imp)

    return ''


def recur_print_md(tree, enumerator, path=tuple()):        
    title_str = "{} {}{} {}{}".format(
        "#" * len(path), 
        state_func(tree),
        enumerator(path), 
        tree['text'],
        importance(tree)
    )

    print(title_str)
    print("")

    for i, item in enumerate(tree['children'], start=1):
        recur_print_md(item, enumerator, path + (i,))

@dataclass
class Case:
    name: str
    version: str
    initial_conditions: str
    steps: list[str]
    data: str
    expected_result: str

@dataclass
class Scenario:
    name: str
    description: str
    author: str
    initial_conditions: str
    cases: list[Case]

class ParserState(Enum):
    INITIAL = 1
    DESCRIPTION_OR_META_OR_CASES = 2
    CASES = 3


def extract_case_from_ast(node):
    return node

def to_plain_text(token):
    if token['type'] == 'RawText':
        return token['content']

    return ' '.join([to_plain_text(node) for node in token['children']]).strip()


def extract_scenario_from_ast(ast):
    return ast

    state = ParserState.INITIAL

    name = None
    description = None
    author = None
    initial_conditions = None
    cases = []

    def parse_node(node):

    for node in ast['children']:
        if state == ParserState.INITIAL and node['type'] == 'Heading' and node['level'] == 1:
            state = ParserState.DESCRIPTION_OR_META_OR_CASES
            name = to_plain_text(node)
        
        if state == ParserState.DESCRIPTION_OR_META_OR_CASES and node['type'] == 'Paragraph':
            description = to_plain_text(node)
        
        if state == ParserState.DESCRIPTION_OR_META_OR_CASES and node['type'] == 'List':
            for meta_node in node['children']:
                

        


    return Scenario(
        name=name,
        description=description,
        author=author,
        initial_conditions=initial_conditions,
        cases=cases
    )
        



def read_file(filename):
    with open(filename, 'r') as f:
        document = Document(f)

        ast = ast_renderer.get_ast(document)

        return extract_scenario_from_ast(ast)


def main():
    arguments = docopt(__doc__, version='1.0')

    filename = Path(arguments['PATH']).resolve(strict=True)

    pprint.pprint(read_file(filename))    
