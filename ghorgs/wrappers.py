"""
This module maintains key class objects for wrapping Github Key Nodes
(Such has Repository, Issue,
"""
import datetime
import concurrent.futures
from time import sleep
from typing import Tuple
from functools import lru_cache
try:
    import ujson as json
except ImportError:
    import json
import requests
from dateutil.parser import parse
from .functions import parse_github_link_header, get_created_datetime


DEFAULT_DUEON_DATETIME_STR = '2012-10-09T23:39:01Z'


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

    def to_json(self):
        def get_object_dict(obj):
            if hasattr(obj, '__dict__'):
                # filter out *private* methods/functions/variables
                return {k: v for k, v in obj.__dict__.items() if not k.startswith('_')}
            else:
                return repr(obj)

        return json.dumps(self, default=get_object_dict, sort_keys=True, indent=4)


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


class GithubPagedRequestHandler:

    def get_paged_content(self, session: requests.Session, url: str) -> list:
        """
        Get the paged response from a github url

        .. note::

            This is only expected to be used for urls which return multiple values (list)

        :param session: Session from which to make the GET reqeust
        :param url: URL to retrieve data/content from
        :return:  All data/content from the paged response
        """
        all_data = []
        current_url = url
        last_url = None
        while True:
            response = session.get(current_url)
            retry_after_raw = response.headers.get('Retry-After', None)
            if retry_after_raw:
                print('Hit Rate Limit, will retry after: {}s'.format(retry_after_raw))
                sleep(int(retry_after_raw))
                continue
            response.raise_for_status()

            data = response.json()
            assert isinstance(data, list)
            all_data.extend(data)

            # Need to move this check here and change to 'while True' so the last page of the gitbub project will be processed
            if current_url == last_url:
                break

            # check header
            if 'Link' in response.headers:
                # parse
                parsed_link_header = parse_github_link_header(response.headers['Link'])
                current_url = parsed_link_header['next']
                last_url = parsed_link_header['last']
            else:
                last_url = current_url
        return all_data


class GithubRepository(BaseJsonClass, GithubPagedRequestHandler):
    _session = None  # Populated on creation
    _org = None  # Populated on creation

    @property
    def milestones(self):
        normalized_url, _ = self.milestones_url.split('{')
        data = self.get_paged_content(self._session, normalized_url)
        return data

    def create_milestone(self, title: str, description: str, due_on: datetime.datetime, state: str = 'open') -> Tuple[int, dict]:
        """
        Create a github repository milestone

        :param title: milestone title
        :param description: milestone description
        :param due_on: milestone due date
        :param state: ('open'|'closed'|'all')
        :return:
            Status code and parsed JSON response.
            https://developer.github.com/v3/issues/milestones/#create-a-milestone
            .. code:: python

                (STATUS_CODE, CREATE_RESPONSE)

        """
        if due_on:
            if isinstance(due_on, datetime.date):
                due_on = datetime.datetime.combine(due_on, datetime.datetime.min.time())
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

    def update_milestone(self, title: str, description: str, due_on: datetime.datetime, state: str = 'open', number: int = None):
        assert number
        # PATCH / repos /: owner /:repo / milestones /: number
        if due_on:
            if isinstance(due_on, datetime.date):
                due_on = datetime.datetime.combine(due_on, datetime.datetime.min.time())
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
        update_url = f'{normalized_url}/{number}'
        print('UPDATE_URL:', update_url)
        response = self._session.patch(update_url, json=milestone)
        return response.status_code, response.json()

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


class GithubOrganizationProject(GithubPagedRequestHandler):
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
        return self._clean_url(self._data['html_url'])

    @property
    def url(self):
        return self._clean_url(self._data['url'])

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
                comments_data = self.get_paged_content(self._session, comments_url)
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
                cards_url = self._clean_url(column_data['cards_url'])
                cards_data = self.get_paged_content(self._session, cards_url)

                index_start = 1
                for position, card in enumerate(cards_data, index_start):
                    if 'content_url' in card and 'issue' in card['content_url']:
                        url = self._clean_url(card['content_url'])
                        job = executor.submit(process_issue,
                                              url,
                                              column_name,
                                              position)
                        jobs.append(job)

            # process results
            for future in concurrent.futures.as_completed(jobs):
                yield future.result()

    def _clean_url(self, url):
        schema_index = url.index('http')
        return url[schema_index:]

    def columns(self):
        """
        get the project columns data

        :return:
            .. code:: python

                [
                    {
                    'cards_url': 'https://api.github.com/projects/columns/737779/cards',
                    'created_at': '2017-03-03T00:45:48Z',
                    'id': 737779,
                    'name': 'Ready For Acceptance Tests',
                    'project_url': 'https://api.github.com/projects/426145',
                    'updated_at': '2017-03-27T04:11:18Z',
                    'url': 'https://api.github.com/projects/columns/737779'
                    },
                ]
        """
        # "columns_url":"https://api.github.com/projects/426145/columns",
        url = self._clean_url(self._data['columns_url'])
        columns_data = self.get_paged_content(self._session, url)
        return columns_data
