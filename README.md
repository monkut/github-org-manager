# github-projects-manager README

This project is intended to provide tools to make it easier to discover the current state of multiple GITHUB Organizational projects.

## Usage

The main interface is through the `GithubOrganizationProjectManager` class.
This class allows you to obtain all the projects assigned to a given organization, with the option to filter projects based on the project name.


Example:
```
ORGANIZATION = 'my orgnaization'
PROJECT_NAMES_FILTER = ['My Org Project Name']
manager = GithubOrganizationProjectManager(github_oauth_token,
                                           ORGANIZATION,
                                           PROJECT_NAMES_FILTER)
for project in manager.projects():
    for issue in project.issues():
```

The `GithubOrganizationProjectManager.projects()` method *yields* `GithubOrganizationProject` objects.
`GithubOrganizationProject` objects wrap the github API returned JSON by providing the following convience methods:

*issues*
    - Method that provides all issues attached to an *organzation project*, with the option to filter by *column_name*
    Returns a list of github issues containing the following information:
    ```
    # Returned issue information:
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
    ```

*columns*
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
