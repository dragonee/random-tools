
from pathlib import Path

from configparser import ConfigParser

class TasksConfigFile:
    url = None
    user = None
    password = None

    def __init__(self):
        self.reader = ConfigParser()

        self.reader.read(self.paths())

        try:
            self.url = self.reader['Tasks']['url']
            self.user = self.reader['Tasks']['user']
            self.password = self.reader['Tasks']['password']
        except KeyError:
            raise KeyError("Create ~/.tasks-collector.ini file with section [Tasks] containing url/user/password")

    def paths(self):
        return [
            '/etc/tasks-collector.ini',
            Path.home() / '.tasks-collector.ini',
        ]

