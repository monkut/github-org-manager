"""
This module provides mock classes for classes in ghorgs.managers
"""
import datetime
from typing import List, Tuple


class GithubAssigneeMock:

    def __init__(self, login):
        self.login = login


class GithubIssueMock:

    def __init__(self, title, body, repository_url, url, html_url, project_column, state='open', number_of_assignees=1):
        self.title = title
        self.body = body
        self.repository_url = repository_url
        self.url = url
        self.html_url = html_url
        self.project_column = project_column
        self.state = state
        self.number_of_assignees = number_of_assignees

        self.latest_comment_body = 'sample latest comment body'
        self.latest_comment_created_by = 'someone'
        self.latest_comment_created_at = datetime.datetime.now() - datetime.timedelta(days=3)

    @property
    def assignees(self):
        result = []
        for i in range(self.number_of_assignees):
            login = f'assignee-{i}'
            result.append(GithubAssigneeMock(login))
        return result


class GithubOrganizationProjectMock:

    def __init__(self, github_issue_mocks=None):
        self.github_issue_mocks = github_issue_mocks

    def issues(self):
        return self.github_issue_mocks


class GithubOrganizationManagerMock:

    def __init__(self, github_project_mocks=None):
        self.github_project_mocks = github_project_mocks

    def projects(self):
        return self.github_project_mocks


class GithubGraphQLManagerMock:

    def __init(self, github_organization_name: str, token: str):
        self.organization = github_organization_name
        self.token = token
        self.url = None  # set as needed when testing

    def create_orgnaizational_project(self, name: str, description: str, columns: list=None) -> Tuple[str, List[object]]:
        return self.url, []

    def add_column(self, project_id, columns):
        return []
