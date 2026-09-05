
from pathlib import Path

from configparser import ConfigParser


class GoogleConfigFile:
    DEFAULT_SECTION = 'Google'

    token_path = None
    credentials_path = None

    def __init__(self, section=None):
        self.section = section or self.DEFAULT_SECTION

        self.reader = ConfigParser()

        self.reader.read(self.paths())

        try:
            self.token_path = Path(self.entries()['token_path']).expanduser()
            self.credentials_path = Path(self.entries()['credentials_path']).expanduser()
        except KeyError:
            raise KeyError("Create ~/.google/config.ini file with section [{}] containing token_path/credentials_path".format(self.section))

    def entries(self):
        try:
            return self.reader[self.section]
        except KeyError:
            raise KeyError("Create ~/.google/config.ini file with section [{}] containing token_path/credentials_path".format(self.section))

    @property
    def selected_calendars(self):
        try:
            return set(map(str.strip, self.entries()['selected_calendars'].split(',')))
        except KeyError:
            raise KeyError("Section [{}] of ~/.google/config.ini needs selected_calendars".format(self.section))

    def paths(self):
        return [
            '/etc/google/config.ini',
            Path.home() / '.google/config.ini',
        ]
