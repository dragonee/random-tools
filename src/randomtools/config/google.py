
from pathlib import Path

from configparser import ConfigParser


class GoogleConfigFile:
    token_path = None
    credentials_path = None
    selected_calendars = set()

    def __init__(self):
        self.reader = ConfigParser()

        self.reader.read(self.paths())

        try:
            self.token_path = Path(self.reader['Google']['token_path']).expanduser()
            self.credentials_path = Path(self.reader['Google']['credentials_path']).expanduser()
            self.selected_calendars = set(map(str.strip, self.reader['Google']['selected_calendars'].split(',')))
        except KeyError:
            raise KeyError("Create ~/.google/config.ini file with section [Google] containing token_path/credentials_path")

    def paths(self):
        return [
            '/etc/google/config.ini',
            Path.home() / '.google/config.ini',
        ]

