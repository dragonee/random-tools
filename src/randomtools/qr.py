"""
Generate QR codes from links with automatic file naming.

Usage:
    qr LINK [FILE] [options]
    qr -h | --help
    qr --version

Arguments:
    LINK    The URL or text to encode in the QR code
    FILE    Output filename (optional, will be slugified from LINK if not provided)

Options:
    -q --quiet    Quiet mode, suppress output messages.
    -h --help     Show this screen.
    --version     Show version.
"""

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from docopt import docopt


def slugify(text):
    """Convert text to a filename-safe slug."""
    # Remove protocol and www
    text = re.sub(r'^https?://', '', text)
    text = re.sub(r'^www\.', '', text)
    
    # Replace non-alphanumeric characters with hyphens
    text = re.sub(r'[^a-zA-Z0-9]+', '-', text)
    
    # Remove leading/trailing hyphens and convert to lowercase
    text = text.strip('-').lower()
    
    # Limit length to reasonable filename length
    if len(text) > 50:
        text = text[:50].rstrip('-')
    
    return text


def detect_file_type(filename):
    """Detect file type from extension."""
    suffix = Path(filename).suffix.lower()
    if suffix == '.png':
        return 'png'
    elif suffix == '.svg':
        return 'svg'
    else:
        # Default to PNG if no recognized extension
        return 'png'


def main():
    arguments = docopt(__doc__, version='1.0.0')
    
    link = arguments['LINK']
    file_arg = arguments['FILE']
    quiet = arguments['--quiet']
    
    # Generate filename if not provided
    if file_arg:
        output_file = file_arg
    else:
        slug = slugify(link)
        if not slug:
            slug = 'qr-code'
        output_file = f"{slug}.png"
    
    # Detect file type
    file_type = detect_file_type(output_file)
    
    # Build qrtool command
    cmd = ['qrtool', 'encode', link, '-o', output_file, '-t', file_type]
    
    try:
        # Run qrtool
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            if not quiet:
                print(f"QR code generated: {output_file}")
        else:
            print(f"Error generating QR code: {result.stderr}", file=sys.stderr)
            sys.exit(1)
            
    except FileNotFoundError:
        print("Error: qrtool not found. Please install qrtool first.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()