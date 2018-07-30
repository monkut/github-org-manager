"""
GitHub Related Functions
"""
import re
import requests
from dateutil.parser import parse
from .exceptions import GithubGraphQLError

GITHUB_GRAPHQL_API_URL = 'https://api.github.com/graphql'


def get_created_datetime(item):
    """
    Key function for sorting comments by creation date

    :param item:
    :return:
    """
    return parse(item['created_at'])


def parse_github_link_header(link_value) -> dict:
    """
    A parser for the github assigned HTTP HEADER, 'Link' value, used for paging.

    :param link_value: Value of the 'Link' HTTP HEADER
    :return: Mapping of Conditional Links (next, last, etc)
    """
    parsed_links = {}
    for value in link_value.split(','):
        url_raw, condition_raw = value.split('; ')
        url = url_raw.strip()[1:-1]
        condition = re.findall(r'\"(.+?)\"', condition_raw.strip())[0]
        parsed_links[condition] = url
    return parsed_links


def run_graphql_request(query: str, token: str, raise_on_error: bool=False):
    """
    Run a GraphQL Query against the github graphql API

    :param query:
    :param token:
    :param raise_on_error:
    :return:
    """
    headers = {"Authorization": f"token {token}"}
    response = requests.post(GITHUB_GRAPHQL_API_URL, json={"query": query}, headers=headers)
    if response.status_code == 200:
        result = response.json()
        if raise_on_error:
            if not result['data'] and result['errors']:
                raise GithubGraphQLError(result['errors'])
        return result
    else:
        raise GithubGraphQLError("Query failed to run by returning code of {}. {}".format(response.status_code, query))
