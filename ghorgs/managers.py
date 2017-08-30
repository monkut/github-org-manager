"""
A Manager utilizing the GITHUB API with the objective
to link Organizational Projects to Issues and capture the *project state (column)* of the issues.
"""
import os
import json
import logging
import concurrent.futures
from functools import lru_cache
from dateutil.parser import parse

import requests

logging.basicConfig(format='%(asctime) [%(level)s]: %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

GITHUB_API_URL = 'https://api.github.com/'


def get_created_datetime(item):
    """
    Key function for sorting comments by creation date
    :param item:
    :return:
    """
    return parse(item['created_at'])


class BaseJsonClass:

    @classmethod
    def from_dict(cls, d):
        # can be used with json.loads() to load directly to a class
        # github_issue = json.loads(data, object_hook=GithubIssue.from_dict)
        obj = cls()
        obj.__dict__.update(d)
        return obj


class GithubIssue(BaseJsonClass):
    pass


DEFAULT_LABEL_COLOR = 'f29513'


class GithubRepository(BaseJsonClass):
    _session = None

    def create_label(self, name, color=DEFAULT_LABEL_COLOR):
        assert self._session
        label = {
            'name': name,
            'color': color,
        }
        normalized_url, _ = self.labels_url.split('{')
        response = self._session.post(normalized_url, json=label)
        return response.status_code, response.json()


class GithubOrganizationProject:
    """
    Wraps an individual Github Organization Project found in the response:
    https://developer.github.com/v3/projects/#list-organization-projects
    """

    def __init__(self, session, data):
        self._session = session
        self._data = data
        self._raw_issues = []

    def __repr__(self):
        return '{}({})'.format(self.__class__.__name__, self.name)

    @property
    def name(self):
        return self._data['name']

    @property
    def html_url(self):
        return self._data['html_url']

    @property
    def url(self):
        return self._data['url']

    def issues(self):
        def process_issue(url, column_name=None):
            """
            Retrieve data from the given ISSUE URL and internal COMMENTS URL and return a list of key desired values
            :param url: (str) GITHUB issue url
            :param column_name: (str) Project Column Name that the issue belongs to
            :return: (list)
                [
                    ISSUE_NUMBER, (int)
                    ISSUE_ID, (int)
                    ISSUE_TITLE, (str)
                    ISSUE_STATE, (str)
                    PROJECT_COLUMN_NAME, (str)
                    ISSUE_URL, (str)
                    ISSUE_MILESTONE, (str)
                    ISSUE_LABEL_NAMES, (list)
                    ISSUE_CREATED_BY, (str)
                    ISSUE_ASSIGNEE, (str)
                    ISSUE_CREATED_AT, (datetime)
                    ISSUE_UPDATED_AT, (datetime)
                    LATEST_COMMENT_CREATED_AT, (datetime)
                    LATEST_COMMENT_CREATED_BY, (str)
                    LATEST_COMMENT_BODY, (str)
                ]
            """
            response = self._session.get(url)
            assert response.status_code == 200
            issue = json.loads(response.text, object_hook=GithubIssue.from_dict)
            processed_issue = [
                issue.number,
                issue.id,
                issue.title,
                issue.state,
                column_name,
                issue.html_url,  # link
                issue.milestone
            ]

            # parse labels
            labels = [d.name for d in issue.labels]
            processed_issue.append(labels)

            # add creator
            created_by = issue.user.login
            processed_issue.append(created_by)

            # add assignee
            assignee = None
            if issue.assignee:
                assignee = issue.assignee.login
            processed_issue.append(assignee)

            # created_datetime
            processed_issue.append(parse(issue.created_at))

            # updated_datetime
            processed_issue.append(parse(issue.updated_at))

            latest_comment_body = None
            latest_comment_created_at = None
            latest_comment_created_by = None
            if issue.comments:  # defines number of comments
                # get last comment info
                comments_url = issue.comments_url
                response = self._session.get(comments_url)
                assert response.status_code == 200
                comments_data = response.json()
                latest_comment = sorted(comments_data, key=get_created_datetime)[-1]
                latest_comment_body = latest_comment['body']
                latest_comment_created_at = parse(latest_comment['created_at'])
                latest_comment_created_by = latest_comment['user']['login']  # username
            processed_issue.append(latest_comment_created_at)
            processed_issue.append(latest_comment_created_by)
            processed_issue.append(latest_comment_body)

            return processed_issue

        # prepare and process cards (issues)
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            # submit jobs
            jobs = []
            for column_data in self.columns():
                column_name = column_data['name']

                # get issues (cards) in column
                cards_url = column_data['cards_url']
                cards_response = self._session.get(cards_url)
                assert cards_response.status_code == 200
                cards_data = cards_response.json()
                for card in cards_data:
                    if 'content_url' in card and 'issue' in card['content_url']:
                        job = executor.submit(process_issue,
                                              card['content_url'],
                                              column_name)
                        jobs.append(job)

            # process results
            for future in concurrent.futures.as_completed(jobs):
                yield future.result()

    def columns(self):
        # "columns_url":"https://api.github.com/projects/426145/columns",
        url = self._data['columns_url']
        response = self._session.get(url)
        assert response.status_code == 200

        # sample response
        # {'cards_url': 'https://api.github.com/projects/columns/737779/cards',
        #   'created_at': '2017-03-03T00:45:48Z',
        #   'id': 737779,
        #   'name': 'Ready For Acceptance Tests',
        #   'project_url': 'https://api.github.com/projects/426145',
        #   'updated_at': '2017-03-27T04:11:18Z',
        #   'url': 'https://api.github.com/projects/columns/737779'},
        return response.json()


class GithubOrganizationManager:
    """
    Functions/Tools for managing Github Organization Projects
    """

    def __init__(self, oauth_token, org=None):
        """
        :param oauth_token: GITHUB OAUTH TOKEN
        :param org: GITHUB ORGANIZATION NAME
        :param projects: (list) project names to filter
        """
        self._oauth_token = oauth_token
        self._session = requests.session()
        self._session.headers.update({'Authorization': 'token {}'.format(oauth_token)})
        # Accept Header added for GITHUB projects API support
        # See:
        # https://developer.github.com/v3/projects/
        self._session.headers.update({'Accept': 'application/vnd.github.inertia-preview+json'})

        # add adapter to increase pool maxsize!
        adapter = requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=100)
        self._session.mount('https://', adapter)

        self.org = org

    @lru_cache(maxsize=1)
    def projects(self):
        """
        :return: list of organization project objects
        """
        url = '{root}orgs/{org}/projects'.format(root=GITHUB_API_URL,
                                                 org=self.org)
        response = self._session.get(url)
        assert response.status_code == 200
        projects_data = response.json()

        # Create generator for project data
        yield from (GithubOrganizationProject(self._session, p) for p in projects_data)

    @lru_cache(maxsize=1)
    def repositories(self, name=None):
        def classify(d):
            repo_json = json.dumps(d)
            repository = json.loads(repo_json, object_hook=GithubRepository.from_dict)
            repository._session = self._session  # attach session
            return repository

        if name:
            # https://api.github.com/repos/abeja-inc/platform-release-planning
            url = '{root}repos/{org}/{name}'.format(root=GITHUB_API_URL,
                                                    org=self.org,
                                                    name=name)
            response = self._session.get(url)
            if response.status_code != 200:
                raise Exception('{}: {}'.format(url, response.status_code))
            repository = classify(response.json())
            yield repository

        else:
            url = '{root}orgs/{org}/repos'.format(root=GITHUB_API_URL,
                                                  org=self.org)
            response = self._session.get(url)
            assert response.status_code == 200
            data = response.json()
            for repo in data:
                # dumping to load to class object
                respository = classify(repo)
                yield respository


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-t', '--token',
                        default=os.environ.get('GITHUB_OAUTH_TOKEN', None),
                        help='GITHUB OAUTH Token')
    parser.add_argument('-o', '--organization',
                        default='abeja-inc',
                        help='Github Organization Name')
    parser.add_argument('-p', '--projects',
                        nargs='+',
                        default=None,
                        required=True,
                        help='Project Name Filter(s) [DEFAULT=None]')
    parser.add_argument('--verbose',
                        action='store_true',
                        default=False,
                        help='If given, DEBUG info will be displayed')
    args = parser.parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    manager = GithubOrganizationManager(args.token,
                                        args.organization)
    for project in manager.projects():
        if project.name in args.projects:
            for issue in project.issues():
                print(issue)

