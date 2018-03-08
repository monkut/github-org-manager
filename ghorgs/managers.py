"""
A Manager utilizing the GITHUB API with the objective
to link Organizational Projects to Issues and capture the *project state (column)* of the issues.
"""
import os
import json
import logging
import datetime
import concurrent.futures
from time import sleep
from functools import lru_cache
from dateutil.parser import parse

import requests

logging.basicConfig(format='%(asctime) [%(level)s]: %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

GITHUB_ACCESS_TOKEN = os.environ.get('GITHUB_ACCESS_TOKEN', None)
GITHUB_API_URL = 'https://api.github.com/'
DEFAULT_DUEON_DATETIME_STR = '2012-10-09T23:39:01Z'


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
        """
        Method to be used with json.loads() to load directly to a class
        Example:
            object = json.loads(data, object_hook=BaseJsonClass.from_dict)
        :param d:
        :return:
        """
        obj = cls()
        obj.__dict__.update(d)
        return obj


class GithubIssue(BaseJsonClass):
    _project_manager = None
    project_column = None
    column_priority = None  # added from connected Github Project
    latest_comment_created_by = None
    latest_comment_created_at = None
    latest_comment_body = None

    def _process_referenced_issues(self, raw):
        """
        Github referenced issues take the following formats:
            '#N' -- Where issue is in the same repository as current issue
            'OWNER/REPO#N'
        :param raw:
        :return:
        """
        repo, issue_number_str = raw.split('#')
        issue_number = int(issue_number_str)
        confirmed_issue_id = None
        if not repo:
            # same repo as current this issue
            for issue in self._project_manager.issues():
                if issue.number == issue_number:
                    confirmed_issue_id = issue.id
                    break
        else:
            raise NotImplementedError('Cross Repository Dependencies not yet supported')
        return confirmed_issue_id

    @property
    def is_open(self):
        if self.state == 'open':
            return True
        return False

    @property
    def is_closed(self):
        return not self.is_open

    @property
    def depends_on(self):
        """
        Parse the Github issue body and retrieve the issue the issue depends on
        Dependencies are defined by starting a line with one of the following:
            - 'depends-on:'
            - 'dp:'
            - 'dependson:'

        :return: (list) [ISSUE_NUMBER, ISSUE_NUMBER, ...]
        """
        ids = []
        for line in self.body.split('\n'):
            clean_line = line.strip().lower()
            if clean_line.startswith(('depends-on:', 'dp:', 'dependson:')):
                _, raw_numbers = clean_line.split(':')

                # process links
                for item in raw_numbers.split(','):
                    confirmed_issue_id = self._process_referenced_issues(item.strip())
                    if confirmed_issue_id:
                        ids.append(confirmed_issue_id)
        return ids


DEFAULT_LABEL_COLOR = 'f29513'


class GithubRepository(BaseJsonClass):
    _session = None  # Populated on creation
    _org = None  # Populated on creation

    @property
    def milestones(self):
        normalized_url, _ = self.milestones_url.split('{')
        return self._session.get(normalized_url).json()

    def create_milestone(self, title: str, description: str, due_on: datetime.datetime, state: str='open'):
        if due_on:
            iso8601 = due_on.isoformat(sep='T', timespec='seconds')
            if '+' not in iso8601 and 'Z' not in iso8601:
                iso8601 += 'Z'  # setting to UTC if timezone not defined
        else:
            iso8601 = DEFAULT_DUEON_DATETIME_STR

        milestone = {
            'title': title,
            'state': state,
            'description': description,
            'due_on': iso8601
        }

        normalized_url, _ = self.milestones_url.split('{')
        response = self._session.post(normalized_url, json=milestone)
        return response.status_code, response.json()

    def update_milestone(self, title: str, description: str, due_on: datetime.datetime, state: str='open', number: int=None):
        raise NotImplementedError()

    def delete_milestone(self, number):
        normalized_url, _ = self.milestones_url.split('{')
        specific_milestone_url = '{}/{}'.format(normalized_url, number)
        response = self._session.delete(specific_milestone_url)
        return response.status_code

    @property
    def labels(self):
        normalized_url, _ = self.labels_url.split('{')
        return self._session.get(normalized_url).json()

    def create_label(self, name, description='', color=DEFAULT_LABEL_COLOR):
        assert self._session
        label = {
            'name': name,
            'description': description,
            'color': color,
        }
        normalized_url, _ = self.labels_url.split('{')
        response = self._session.post(normalized_url, json=label)
        return response.status_code, response.json()

    def delete_label(self, name):
        # DELETE / repos /: owner /:repo / labels /: name
        assert self._session
        normalized_url, _ = self.labels_url.split('{')
        specific_label_url = '{}/{}'.format(normalized_url, name)
        response = self._session.delete(specific_label_url)
        return response.status_code


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

    @property
    @lru_cache()
    def repositories(self):
        for repo_url in self.repository_urls():
            yield GithubRepository(url=repo_url)

    @lru_cache()
    def repository_urls(self):
        unique_repo_urls = set()
        for issue in self.issues():
            unique_repo_urls.add(issue.repository_url)
        return tuple(unique_repo_urls)

    def issues(self):
        def process_issue(url, column_name=None, position=None):
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
                    CARD_POSITION_IN_COLUMN, (int)
                    ISSUE_DESCRIPTION, (str)
                ]
            """
            response = self._session.get(url)
            response.raise_for_status()

            issue = json.loads(response.text, object_hook=GithubIssue.from_dict)
            issue._project = self
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
                response.raise_for_status()

                comments_data = response.json()
                latest_comment = sorted(comments_data, key=get_created_datetime)[-1]
                latest_comment_body = latest_comment['body']
                latest_comment_created_at = parse(latest_comment['created_at'])
                latest_comment_created_by = latest_comment['user']['login']  # username
            processed_issue.append(latest_comment_created_at)
            processed_issue.append(latest_comment_created_by)
            processed_issue.append(latest_comment_body)
            issue.latest_comment_created_at = latest_comment_created_at
            issue.latest_comment_created_by = latest_comment_created_by
            issue.latest_comment_body = latest_comment_body

            # add position in order to get card priority in column
            processed_issue.append(position)
            issue.column_priority = position  # issue priority within the column
            issue.project_column = column_name  # related project column name

            # add description
            processed_issue.append(issue.body)
            issue.simple = processed_issue
            issue.project_column = column_name
            issue._project_manager = self  # attach so that project can be queiried from within the Issue object

            return issue

        # prepare and process cards (issues)
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            # submit jobs
            jobs = []
            for column_data in self.columns():
                column_name = column_data['name']

                # get issues (cards) in column
                cards_url = column_data['cards_url']
                next_url = cards_url
                index_start = 0
                while next_url:
                    cards_response = self._session.get(next_url)
                    if cards_response.status_code != 200:
                        retry_after_raw = cards_response.headers.get('Retry-After', None)
                        if retry_after_raw:
                            print('Hit Rate Limit, will retry after: {}s'.format(retry_after_raw))
                            sleep(int(retry_after_raw))
                            continue
                        else:
                            cards_response.raise_for_status()  # raise exception for non-200 values
                    cards_data = cards_response.json()

                    for position, card in enumerate(cards_data, index_start):
                        if 'content_url' in card and 'issue' in card['content_url']:
                            job = executor.submit(process_issue,
                                                  card['content_url'],
                                                  column_name,
                                                  position)
                            jobs.append(job)

                    # check for next url link
                    links = cards_response.headers.get('Link', None)
                    next_url = None
                    if links:
                        for link in links.split(','):
                            if 'next' in link:
                                url_raw, rel = link.split(';')
                                next_url = url_raw[1:-1]
                                index_start = position + 1
                                break

            # process results
            for future in concurrent.futures.as_completed(jobs):
                yield future.result()

    def columns(self):
        # "columns_url":"https://api.github.com/projects/426145/columns",
        url = self._data['columns_url']
        response = self._session.get(url)
        response.raise_for_status()

        # sample response
        # {'cards_url': 'https://api.github.com/projects/columns/737779/cards',
        #   'created_at': '2017-03-03T00:45:48Z',
        #   'id': 737779,
        #   'name': 'Ready For Acceptance Tests',
        #   'project_url': 'https://api.github.com/projects/426145',
        #   'updated_at': '2017-03-27T04:11:18Z',
        #   'url': 'https://api.github.com/projects/columns/737779'},
        return response.json()


class GithubAccessTokenNotDefined(Exception):
    pass


class GithubOrganizationManager:
    """
    Functions/Tools for managing Github Organization Projects
    """

    def __init__(self, oauth_token=GITHUB_ACCESS_TOKEN, org=None):
        """
        :param oauth_token: GITHUB OAUTH TOKEN
        :param org: GITHUB ORGANIZATION NAME
        :param projects: (list) project names to filter
        """
        self._oauth_token = oauth_token
        if not self._oauth_token:
            raise GithubAccessTokenNotDefined('Set the GITHUB_ACCESS_TOKEN envar, or pass on GithubOrganizationManager instantiation!')

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

    @lru_cache(maxsize=10)
    def projects(self):
        """
        :return: list of organization project objects
        """
        url = '{root}orgs/{org}/projects'.format(root=GITHUB_API_URL,
                                                 org=self.org)
        response = self._session.get(url)
        response.raise_for_status()

        projects_data = response.json()

        # Create generator for project data
        yield from (GithubOrganizationProject(self._session, p) for p in projects_data)

    @lru_cache(maxsize=10)
    def repositories(self, names=None):
        def classify(repository_dict):
            """
            Load Github repository API dictionary representation to an internally defined GitRepository Object
            :param repository_dict: (dict) github Repository dictionary Representation
            :return: (obj) GithubRepository
            """
            repoository_json = json.dumps(repository_dict)
            repository = json.loads(repoository_json, object_hook=GithubRepository.from_dict)
            repository._session = self._session  # attach session so queries can be made
            repository._org = self.org
            return repository

        if names:
            for name in names:
                # https://api.github.com/repos/OWNER/REPOSITORY
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
            response.raise_for_status()

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
                print(issue.simple)

            print('---')
            for urls in project.repository_urls():
                print(urls)



