from pathlib import Path
from configparser import ConfigParser


class HarvestConfigFile:
    personal_token = None
    account_id = None

    def __init__(self):
        self.reader = ConfigParser()
        self.reader.read(self.paths())

        try:
            self.personal_token = self.reader['Harvest']['personal_token']
            self.account_id = self.reader['Harvest']['account_id']
        except KeyError:
            raise KeyError("Create ~/.harvest/config.ini file with section [Harvest] containing personal_token, account_id")

    def paths(self):
        return [
            '/etc/harvest/config.ini',
            Path.home() / '.harvest/config.ini',
        ]
