from pathlib import Path
from configparser import ConfigParser


class CalamariConfigFile:
    tenant = None
    api_key = None

    def __init__(self):
        self.reader = ConfigParser()
        self.reader.read(self.paths())

        try:
            self.tenant = self.reader['Calamari']['tenant']
            self.api_key = self.reader['Calamari']['api_key']
        except KeyError:
            raise KeyError("Create ~/.calamari/config.ini file with section [Calamari] containing tenant, api_key")

    def paths(self):
        return [
            '/etc/calamari/config.ini',
            Path.home() / '.calamari/config.ini',
        ]

    @property
    def base_url(self):
        return f"https://{self.tenant}.calamari.io/api"
