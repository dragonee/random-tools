from pathlib import Path
from configparser import ConfigParser


class SlackConfigFile:
    token = None

    def __init__(self):
        self.reader = ConfigParser()
        self.reader.read(self.paths())

        try:
            self.token = self.reader['Slack']['token']
        except KeyError:
            raise KeyError("Create ~/.slack/config.ini file with section [Slack] containing token (xoxp-... user token required)")

    def paths(self):
        return [
            '/etc/slack/config.ini',
            Path.home() / '.slack/config.ini',
        ]
