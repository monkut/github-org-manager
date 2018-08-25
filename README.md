# github-org-manager README

This project provides classes to make it easier to discover the current state of multiple GITHUB Organizational projects.


## GithubOrganizationManager class

The main interface is through the `ghorgs.managers.GithubOrganizationManager` class.

### GithubOrganizationManager Methods

- `create_organizational_project(name: str, description: str, columns: list =None) -> Tuple[str, List[object]]`
    - Creates a new *organizational project*

- `projects() -> Generator[GithubOrganizationProject, None, None]`
    - returns a generator yielding `GithubOrganizationProject` objects

- `repositories(names: List[str]=None) -> Generator[GithubRepository, None, None]`
    - returns a generator yielding `GithubRepository` objects


## GithubOrganizationProject class

### GithubOrganizationProject methods

The `GithubOrganizationManager.projects()` method *yields* `GithubOrganizationProject` objects.
`GithubOrganizationProject` objects wrap the github API returned JSON by providing the following convience methods:

- `issues()`
    - Method that provides all issues attached to an *organzation project*, with the option to filter by *column_name*
        Returns a list of github issues containing the following information:
    - Resulting in a GithubIssue object that wraps the JSON object returned by the github API.

```
# Returned issue information:
# issue.simple
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
```

- `columns()`
    - Returns all available column data assigned to the project.

```
[
    {
        'cards_url': 'https://api.github.com/projects/columns/999999/cards',
        'created_at': '2017-03-03T00:45:48Z',
        'id': 999999,
        'name': 'Ready For Acceptance Tests',
        'project_url': 'https://api.github.com/projects/11111',
        'updated_at': '2017-03-27T04:11:18Z',
        'url': 'https://api.github.com/projects/columns/11111'
     },
    ...
 ]
```


## Usage

> NOTE: Github token may be set in the GITHUB_ACCESS_TOKEN environment variable.

Example:
```
from ghorgs.managers import GithubOrganizationManager
ORGANIZATION = 'my organization'
TOKEN = os.environ.get('GITHUB_API_TOKEN')
manager = GithubOrganizationManager(organizaton=ORGANIZATION,
                                    token=TOKEN)
for project in manager.projects():
    for issue in project.issues():
        print(issue.simple)
```

