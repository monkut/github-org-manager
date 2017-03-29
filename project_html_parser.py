"""
Parse the 2017-02-28 Project page to extract the per column, column name & issues
"""
import requests
from bs4 import BeautifulSoup


class GitHubOrganizationProjectParser:

    def __init__(self, html):
        self.html = html
        self.soup = BeautifulSoup(self.html, 'html.parser')

    def name(self):
        """
        Return the Project name
        :return: 
        """
        return self.soup.title.text

    def issues(self):
        """
        Parse project columns (names, issues) and return a list of issues
        :return: [(ISSUE-GLOBALID, PROJECT-NAME, PROJECT-ID, COLUMN-NAME), ...]
        """
        pass

class GithubSessionManager:

    def __init__(self, username, password):
        login_url = 'https://github.com/session'
        self._session = requests.session()



