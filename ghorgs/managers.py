"""
A Manager utilizing the GITHUB API with the objective
to link Organizational Projects to Issues and capture the *project state (column)* of the issues.
"""
import os
import json
import uuid
import logging
from typing import Tuple, List, Generator, Optional
from functools import lru_cache

import requests
from .wrappers import GithubOrganizationProject, GithubPagedRequestHandler, GithubRepository
from .functions import run_graphql_request
from .exceptions import UnexpectedResponseError


logging.basicConfig(format='%(asctime)s [ %(levelname)s ]: %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# https://developer.github.com/webhooks/
VALID_WEBHOOK_EVENTS = (
    '*',
    'check_run',
    'check_suite',
    'commit_comment',
    'create',
    'delete',
    'deployment',
    'deployment_status',
    'fork',
    'github_app_authorization',
    'gollum',
    'installation',
    'installation_repositories',
    'issue_comment',
    'issues',
    'label',
    'marketplace_purchase',
    'member',
    'membership',
    'milestone'
    'organization',
    'org_block',
    'page_build',
    'project_card',
    'project_column',
    'project',
    'public',
    'pull_request_review_comment',
    'pull_request_review',
    'pull_request',
    'push',
    'repository',
    'repository_vulnerability_alert',
    'release',
    'status',
    'team',
    'team_add',
    'watch',
)
GITHUB_ACCESS_TOKEN = os.environ.get('GITHUB_ACCESS_TOKEN', None)
GITHUB_REST_API_URL = 'https://api.github.com/'


class GithubAccessTokenNotDefined(Exception):
    pass


class GithubGraphQLManager:

    def __init__(self, github_organization_name: str, token: str):
        self.organization = github_organization_name
        self.token = token

    def _get_owner_id(self, name: str) -> str:
        """Performs a lookup for the related internal github ID needed as a key for other queries"""
        query = """
        {
          viewer {
            login,
            id,
            organization (login:"%(name)s"){
              id,
              name
            }
          }

        }    
        """ % {'name': name}
        response = run_graphql_request(query,
                                       self.token,
                                       raise_on_error=True)

        # {'data': {'viewer':
        # {'login': '{GITHUB_LOGIN}', 'id': '{NODE_ID}', 'organization': {'id': '{NODE_ID}', 'name': '{GITHUB_ORG_NAME}'}}}}
        try:
            org_id = response['data']['viewer']['organization']['id']
        except KeyError as e:
            raise UnexpectedResponseError(e.args)
        return org_id

    def create_organizational_project(self, name: str, description: str, columns: Optional[list]=None) -> Tuple[str, List[object]]:
        """
        Create an Organizational Project in github

        :param name: name of project to create
        :param description: description of project to create
        :param columns:
            Columns Definitions .

            If included the columns will be created in the project.
            Columns will be added in the order given.
            .. code:: python

                [
                    COLUMN_NAME,
                    COLUMN_NAME
                ]

        :return:

            .. code:: python

                PROJECT_URL, [{CREATION_REQUEST_RESPONSE_OBJECT}, ]

        """
        owner_id = self._get_owner_id(self.organization)
        mutation_id = str(uuid.uuid4())  # get a random id

        # escape description content, may be json
        encoded_description = json.dumps(description)
        if encoded_description.startswith('"') and encoded_description.endswith('"'):
            # remove unnecessary quotes
            encoded_description = encoded_description[1:-1]

        graphql_mutation = """
        mutation {
          createProject(input:{name:"%(name)s", body:"%(body)s", ownerId:"%(owner_id)s", clientMutationId:"%(mutation_id)s"}) {

                project{
              id,
              name,
              url,
              number      
            }
          }
        }    
        """ % {'name': name,
               'body': encoded_description,
               'owner_id': owner_id,
               'mutation_id': mutation_id}

        responses = []
        response = run_graphql_request(graphql_mutation,
                                       token=self.token,
                                       raise_on_error=True)

        # {'data': {'createProject': {'project': {'id': '{NODE ID}=', 'name': 'project name', 'url':
        project_url = response['data']['createProject']['project']['url']
        responses.append(response)

        try:
            project_id = response['data']['createProject']['project']['id']
        except KeyError as e:
            raise UnexpectedResponseError(e.args)

        if columns:
            add_columns_response = self.add_columns(project_id, columns)
            responses.append(add_columns_response)

        return project_url, responses

    def add_columns(self, project_id: str, columns: List[str]) -> List:
        """
        Add column(s) to the given project.

        :param project_id: Project Identifier which links to the source github organization
        :param columns: Columns to add to the project in the expected order
        :return:
            .. code:: python

                 [{CREATION_REQUEST_RESPONSE_OBJECT}, ]

        """
        addcolumns_responses = []
        for column_name in columns:
            mutation_id = str(uuid.uuid4())  # get a random id
            graphql_addprojectcolumn = """
            mutation {
              addProjectColumn(input:{name:"%(name)s", projectId:"%(project_id)s", clientMutationId:"%(mutation_id)s"}) {
                  columnEdge {
                      node {
                        id,
                        name,
                        resourcePath
                      }
                    }
                  }
            }""" % {'name': column_name,
                    'project_id': project_id,
                    'mutation_id': mutation_id}

            response = run_graphql_request(graphql_addprojectcolumn,
                                           token=self.token,
                                           raise_on_error=True)
            addcolumns_responses.append(response)
        return addcolumns_responses


class GithubOrganizationManager(GithubPagedRequestHandler):
    """
    Functions/Tools for managing Github Organization Projects
    """

    def __init__(self, organization: str, token: str=GITHUB_ACCESS_TOKEN):
        """
        :param organization: Github organization name
        :param token: Github personal access token
            (see: https://help.github.com/articles/creating-a-personal-access-token-for-the-command-line/)

        """
        self._token = token
        if not self._token:
            raise GithubAccessTokenNotDefined('Set the GITHUB_ACCESS_TOKEN envar, or pass on GithubOrganizationManager instantiation!')

        self._session = requests.session()
        self._session.headers.update({'Authorization': 'token {}'.format(token)})
        # Accept Header added for GITHUB projects API support
        # See:
        # https://developer.github.com/v3/projects/
        self._session.headers.update({'Accept': 'application/vnd.github.inertia-preview+json'})

        # add adapter to increase pool maxsize!
        adapter = requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=100)
        self._session.mount('https://', adapter)

        self.org = organization

    def create_organizational_webhook(self, webhook_target_url: str, events: List[str], content_type: str='json', active: bool=True):
        if not all(e in VALID_WEBHOOK_EVENTS for e in events):
            raise ValueError(f'invalid event given, must be one of: {VALID_WEBHOOK_EVENTS}')
        params = {
            'name': 'web',
            'active': active,
            'events': events,
            'config': {
                'url': webhook_target_url,
                'content_type': content_type,
            }
        }
        url = '{root}orgs/{org}/hooks'.format(root=GITHUB_REST_API_URL,
                                              org=self.org)
        response = self._session.post(url, json=params)
        return response.status_code, response.json()

    def ping_organizational_webhook(self, hook_id: int):
        """
        This will trigger a ping event to be sent to the hook.
        :return:
        """
        url = '{root}orgs/{org}/hooks/{hook_id}/ping'.format(root=GITHUB_REST_API_URL,
                                                             org=self.org,
                                                             hook_id=hook_id)
        response = self._session.post(url)
        return response.status_code, response.json()

    def create_organizational_project(self, *args, **kwargs) -> Tuple[str, List[object]]:
        """
        This method makes organizational project creation available through the Github GraphQL API.

        .. note::

            The RESTv3 API does not have an endpoint for organizational project creation.

        :param args:
        :param kwargs:
        :return:

            .. code:: python

                PROJECT_URL, [{CREATION_REQUEST_RESPONSE_OBJECT}, ]

        """
        graphql_manager = GithubGraphQLManager(
            github_organization_name=self.org,
            token=self._token,
        )
        return graphql_manager.create_organizational_project(*args, **kwargs)

    @lru_cache(maxsize=10)
    def projects(self) -> Generator[GithubOrganizationProject, None, None]:
        """
        :return: list of organization project objects
        """
        url = '{root}orgs/{org}/projects'.format(root=GITHUB_REST_API_URL,
                                                 org=self.org)
        projects_data = self.get_paged_content(self._session, url)

        # Create generator for project data
        yield from (GithubOrganizationProject(self._session, p) for p in projects_data)

    @lru_cache(maxsize=10)
    def repositories(self, names: List[str]=None) -> Generator[GithubRepository, None, None]:
        def classify(repository_response: dict) -> GithubRepository:
            """
            Load Github repository API dictionary representation into an internally defined GitRepository Object
            :param repository_response: (dict) github Repository dictionary Representation
            :return: (obj) GithubRepository
            """
            repository_json = json.dumps(repository_response)
            repository = json.loads(repository_json, object_hook=GithubRepository.from_dict)
            repository._session = self._session  # attach session so queries can be made
            repository._org = self.org
            return repository

        if names:
            for name in names:
                # https://api.github.com/repos/OWNER/REPOSITORY
                url = '{root}repos/{org}/{name}'.format(root=GITHUB_REST_API_URL,
                                                        org=self.org,
                                                        name=name)
                response = self._session.get(url)
                if response.status_code != 200:
                    raise Exception('{}: {}'.format(url, response.status_code))
                repository = classify(response.json())
                yield repository

        else:
            url = '{root}orgs/{org}/repos'.format(root=GITHUB_REST_API_URL,
                                                  org=self.org)
            data = self.get_paged_content(self._session, url)
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

    manager = GithubOrganizationManager(args.organization,
                                        args.token)
    for project in manager.projects():
        if project.name in args.projects:
            for issue in project.issues():
                print(issue.to_json())
            print('---')
            for urls in project.repository_urls():
                print(urls)
