from pathlib import Path
from configparser import ConfigParser


class JiraConfigFile:
    domain = None
    email = None
    api_token = None
    dashboard_id = None
    month_string = None
    week_string = None

    def __init__(self):
        self.reader = ConfigParser()
        self.reader.read(self.paths())

        try:
            self.domain = self.reader['Jira']['domain']
            self.email = self.reader['Jira']['email']
            self.api_token = self.reader['Jira']['api_token']
            self.dashboard_id = self.reader['Jira'].get('dashboard_id')
            self.month_string = self.reader['Jira'].get('month_string', 'month')
            self.week_string = self.reader['Jira'].get('week_string', 'week')
        except KeyError:
            raise KeyError("Create ~/.jira/config.ini file with section [Jira] containing domain, email, api_token, dashboard_id")

    def paths(self):
        return [
            '/etc/jira/config.ini',
            Path.home() / '.jira/config.ini',
        ]

    @property
    def base_url(self):
        return f"https://{self.domain}.atlassian.net"