"""Copier tool for clipboard management with YAML configuration.

Usage:
    copier <file>
    copier -h | --help
    copier --version

Options:
    -h, --help       Show this message.
    --version        Show version information.

Commands in shell:
    SECTION          - Copy section content to clipboard
    list             - Show available sections
    config           - Show the raw YAML configuration
    help             - Show this help
    
Quit by pressing Ctrl+D or Ctrl+C.

Configuration:
    Create ~/.info/<file>.yaml with sections. Each section can be:
    
    section_name:
      type: text|file|program
      (type-specific attributes)
    
    Types:
    - text (default): requires 'content' attribute
    - file: requires 'file' attribute (absolute path or relative to ~/.info/)
    - program: requires 'command' attribute (shell command)
    
    Example ~/.info/example.yaml:
    
    greeting:
      type: text
      content: "Hello, World!"
    
    current_dir:
      type: program
      command: "pwd"
    
    readme_absolute:
      type: file
      file: "~/README.md"
    
    readme_relative:
      type: file
      file: "snippets/readme.txt"
    
    simple_text: "This is just plain text"
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from collections.abc import Iterable

from docopt import docopt
import yaml
import shlex
from more_itertools import repeatfunc, consume

try:
    import readline
    READLINE_AVAILABLE = True
except ImportError:
    READLINE_AVAILABLE = False

VERSION = '1.0'

# Storage paths
CONFIG_DIR = Path.home() / '.info'
HISTORY_FILE = CONFIG_DIR / '.copier_history'

# Global variable to store current config
current_config = None
current_file = None

def ensure_config_dir():
    """Ensure config directory exists."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

def setup_readline():
    """Setup readline with history file."""
    if not READLINE_AVAILABLE:
        return
    
    ensure_config_dir()
    
    # Set up history file
    history_file = str(HISTORY_FILE)
    
    try:
        # Load existing history
        readline.read_history_file(history_file)
    except FileNotFoundError:
        # History file doesn't exist yet, that's okay
        pass
    except Exception:
        # Other errors reading history, continue without it
        pass
    
    # Set maximum history size
    readline.set_history_length(1000)
    
    # Save history on exit
    import atexit
    atexit.register(save_readline_history, history_file)

def save_readline_history(history_file):
    """Save readline history to file."""
    if not READLINE_AVAILABLE:
        return
    
    try:
        readline.write_history_file(history_file)
    except Exception:
        # Ignore errors when saving history
        pass

def load_config(file_name):
    """Load YAML configuration from ~/.info/<file>.yaml"""
    config_path = CONFIG_DIR / f"{file_name}.yaml"
    
    if not config_path.exists():
        print(f"Configuration file not found: {config_path}")
        print(f"Please create {config_path} with your sections.")
        return None
    
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        return config
    except yaml.YAMLError as e:
        print(f"Error parsing YAML configuration: {e}")
        return None
    except Exception as e:
        print(f"Error reading configuration file: {e}")
        return None

def get_input_until(predicate, prompt=None):
    """Get input until predicate is satisfied."""
    text = None
    
    while text is None or not predicate(text):
        text = input(prompt)
    
    return text

def copy_to_clipboard(content):
    """Copy content to clipboard using pbcopy."""
    try:
        process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE, text=True)
        process.communicate(input=content)
        
        if process.returncode == 0:
            return True
        else:
            print("Failed to copy to clipboard")
            return False
    except FileNotFoundError:
        print("pbcopy command not found. Are you on macOS?")
        return False
    except Exception as e:
        print(f"Error copying to clipboard: {e}")
        return False

def process_text_section(section_name, section_config):
    """Process a text section and return content."""
    content = section_config.get('content')
    if content is None:
        print(f"Error: Section '{section_name}' of type 'text' requires 'content' attribute")
        return None
    return str(content)

def process_file_section(section_name, section_config):
    """Process a file section and return file contents."""
    file_path = section_config.get('file')
    if file_path is None:
        print(f"Error: Section '{section_name}' of type 'file' requires 'file' attribute")
        return None
    
    # Convert to Path object
    path = Path(file_path)
    
    # Handle different path types
    if path.is_absolute():
        # Absolute path - use as-is, but expand ~ if present
        file_path = path.expanduser()
    else:
        # Relative path - make relative to ~/.info directory
        file_path = CONFIG_DIR / path
    
    try:
        with open(file_path, 'r') as f:
            return f.read()
    except FileNotFoundError:
        print(f"Error: File not found: {file_path}")
        return None
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return None

def process_program_section(section_name, section_config):
    """Process a program section and return command output."""
    command = section_config.get('command')
    if command is None:
        print(f"Error: Section '{section_name}' of type 'program' requires 'command' attribute")
        return None
    
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout
        else:
            print(f"Error: Command failed with return code {result.returncode}")
            if result.stderr:
                print(f"Error output: {result.stderr}")
            return None
    except Exception as e:
        print(f"Error running command: {e}")
        return None

def process_section(section_name, section_config):
    """Process a section configuration and return content to copy."""
    if not isinstance(section_config, dict):
        # If it's just a string, treat as text content
        return str(section_config)
    
    section_type = section_config.get('type', 'text')
    
    match section_type:
        case 'text':
            return process_text_section(section_name, section_config)
        case 'file':
            return process_file_section(section_name, section_config)
        case 'program':
            return process_program_section(section_name, section_config)
        case _:
            print(f"Error: Unknown section type '{section_type}' in section '{section_name}'")
            return None

def list_sections():
    """List available sections."""
    if not current_config:
        print("No configuration loaded")
        return
    
    print("Available sections:")
    for section_name, section_config in current_config.items():
        if isinstance(section_config, dict):
            section_type = section_config.get('type', 'text')
            print(f"  \033[1m{section_name}\033[0m ({section_type})")
        else:
            print(f"  \033[1m{section_name}\033[0m (text)")

def config_command():
    """Show the raw YAML configuration."""
    if not current_config:
        print("No configuration loaded")
        return
    
    config_path = CONFIG_DIR / f"{current_file}.yaml"
    
    try:
        with open(config_path, 'r') as f:
            content = f.read()
        print(f"Configuration from {config_path}:")
        print("-" * 40)
        print(content)
        print("-" * 40)
    except Exception as e:
        print(f"Error reading configuration file: {e}")

def help_command():
    """Show help message."""
    help_text = """
Available commands:
  SECTION          - Copy section content to clipboard
  list             - Show available sections  
  config           - Show the raw YAML configuration
  help             - Show this help

Quit by pressing Ctrl+D or Ctrl+C.
"""
    print(help_text.strip())

def handle_section(section_input):
    """Handle copying a section to clipboard with prefix matching."""
    if not current_config:
        print("No configuration loaded")
        return
    
    # First try exact match
    if section_input in current_config:
        section_name = section_input
    else:
        # Try prefix matching using functional approach
        matching_sections = list(filter(lambda key: key.startswith(section_input), current_config.keys()))
        
        match len(matching_sections):
            case 0:
                print(f"No sections found matching '{section_input}'")
                print("Use 'list' to see available sections")
                return
            case 1:
                section_name = matching_sections[0]
                print(f"Matched section: \033[1m{section_name}\033[0m")
            case _:
                print(f"Ambiguous prefix '{section_input}' matches multiple sections:")
                for match in sorted(matching_sections):
                    section_config = current_config[match]
                    if isinstance(section_config, dict):
                        section_type = section_config.get('type', 'text')
                        print(f"  \033[1m{match}\033[0m ({section_type})")
                    else:
                        print(f"  \033[1m{match}\033[0m (text)")
                print("Please be more specific.")
                return
    
    section_config = current_config[section_name]
    content = process_section(section_name, section_config)
    
    if content is not None:
        if copy_to_clipboard(content):
            lines = content.count('\n') + 1
            chars = len(content)
            print(f"Copied section '\033[1m{section_name}\033[0m' to clipboard ({lines} lines, {chars} characters)")

def run_single_command():
    """Run a single command in the shell loop."""
    try:
        command = get_input_until(bool, prompt=f"copier [{current_file}]> ")
    except (KeyboardInterrupt, EOFError):
        raise
    
    command = command.strip()
    
    match command:
        case 'list':
            list_sections()
        case 'config':
            config_command()
        case 'help':
            help_command()
        case cmd if cmd:
            # Treat as section name
            handle_section(cmd)
        case _:
            # Empty command, do nothing
            pass

def main():
    """Main entry point for copier command."""
    global current_config, current_file
    
    arguments = docopt(__doc__, version=VERSION)
    current_file = arguments['<file>']
    
    # Setup readline with persistent history
    setup_readline()
    
    # Load configuration
    current_config = load_config(current_file)
    if current_config is None:
        return 1
    
    print(f"Loaded configuration from ~/.info/{current_file}.yaml")
    print("Type 'list' to see available sections, 'help' for commands, or enter a section name to copy it.")
    
    # Show available sections initially
    list_sections()
    
    try:
        consume(repeatfunc(run_single_command, None))
    except (KeyboardInterrupt, EOFError):
        print("\nExiting...")
        return 0

if __name__ == '__main__':
    exit(main())