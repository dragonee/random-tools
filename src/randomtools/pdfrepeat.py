"""
Repeat a PDF multiple times

Usage:
    pdfrepeat [options] FILE N

Options:
    -o OUTPUT   Provide a filename for output file.
    -h, --help  Show this message.
    --version   Show version information.
"""

from pathlib import Path

from docopt import docopt

import os

import shutil

import subprocess


def output_file_name(filename, n):
    return filename.parent / '{}-{}{}'.format(
        filename.stem,
        n,
        filename.suffix
    )


def main():
    arguments = docopt(__doc__, version='1.0')

    filename = Path(arguments['FILE']).resolve(strict=True)

    command = shutil.which('pdfunite')

    if not command:
        raise ValueError("pdfunite is not installed, please install")

    n = int(arguments['N'])

    pdfunite_arguments = [command] + [str(filename)] * n

    pdfunite_arguments.append(
        arguments['-o'] or str(output_file_name(filename, n))
    )

    subprocess.check_call(pdfunite_arguments)