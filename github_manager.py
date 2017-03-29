"""
A Manager utilizing the GITHUB API with the objective 
to link Organizational Projects to Issues and capture the *project state (column)* of the issues.
"""
import os
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


class GithubOrganizationProject:

    def __init__(self, session, data):
        self._session = session
        self._data = data

    @property
    def name(self):
        return self._data['name']

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
            issue = response.json()
            processed_issue = []
            processed_issue.append(issue['number'])
            processed_issue.append(issue['id'])
            processed_issue.append(issue['title'])
            processed_issue.append(issue['state'])
            processed_issue.append(column_name)
            processed_issue.append(issue['html_url'])  # link
            processed_issue.append(issue['milestone'])

            # parse labels
            labels = [d['name'] for d in issue['labels']]
            processed_issue.append(labels)

            # add creator
            created_by = issue['user']['login']
            processed_issue.append(created_by)

            # add assignee
            assignee = None
            if issue['assignee']:
                assignee = issue['assignee']['login']
            processed_issue.append(assignee)

            # created_datetime
            processed_issue.append(parse(issue['created_at']))

            # updated_datetime
            processed_issue.append(parse(issue['updated_at']))

            latest_comment_body = None
            latest_comment_created_at = None
            latest_comment_created_by = None
            if issue['comments']:  # defines number of comments
                # get last comment info
                comments_url = issue['comments_url']
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


class GithubProjectManager:

    def __init__(self, oauth_token, org=None, repositories=None):
        """
        :param oauth_token: GITHUB OAUTH TOKEN
        :param org: GITHUB ORGANIZATION NAME
        :param repositories: (list) repository names to filter
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
        self.repositories = repositories

    @lru_cache(maxsize=1)
    def repositories(self):
        assert self.org  # At the moment only support ORG queries
        url = '{root}orgs/{org}/repos'.format(root=GITHUB_API_URL,
                                              org=self.org)
        response = self._session.get(url)
        assert response.status_code == 200

        repos = []
        for idx, repo in enumerate(response.json()):
            name_keys = ('full_name', 'name')
            if any(repo[k] in self.repositories for k in name_keys):
                repos.append(repo)
        return repos

    def issues(self):
        """
        Return all issues for given repositories
        :return: (list) issues
        """
        for repo in self.repositories():
            url = repo['issues_url']
            response = self._session.get(url)  # TODO: does not support pagination
            assert response.status_code == 200
            yield from response.json()

    @lru_cache(maxsize=1)
    def _key_issues_by_id(self):
        return {i['id']: i for i in self.issues()}

    @lru_cache(maxsize=1)
    def organization_projects(self):
        """        
        :return: list of organization project objects 
        """
        url = '{root}orgs/{org}/projects'.format(root=GITHUB_API_URL,
                                                 org=self.org)
        response = self._session.get(url)
        assert response.status_code == 200
        projects_data = response.json()
        return (GithubOrganizationProject(self._session, p) for p in projects_data)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-t', '--token',
                        default=os.environ.get('GITHUB_OAUTH_TOKEN', None),
                        help='GITHUB OAUTH Token')
    parser.add_argument('-o', '--organization',
                        default='abeja-inc',
                        help='Github Organization Name')
    parser.add_argument('-r', '--repositories',
                        nargs='+',
                        default=None,
                        help='Repository Name Filter [DEFAULT=None]')
    parser.add_argument('--verbose',
                        action='store_true',
                        default=False,
                        help='If given, DEBUG info will be displayed')
    args = parser.parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    manager = GithubProjectManager(args.token,
                                   args.organization,
                                   args.repositories)
    for project in manager.organization_projects():
        print(project.name)
        for issue in project.issues():
            print(issue)

