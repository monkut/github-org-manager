import os
import json
import logging
from ghorgs.managers import GithubOrganizationManager

logging.basicConfig(format='%(asctime) [%(level)s]: %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)


def update_repository_labels(organization, token, repositories, labels_definition_filepath, delete=False):
    """
    Update a repository's labels based on a given definition file.
    NOTE:
        if delete == True, undefined labels will be removed/deleted
    :param organization:
    :param token:
    :param repositories:
    :param labels_definition_filepath:
    :param delete:
    :return: created_labels, deleted_labels
    """
    created_labels = []
    deleted_labels = []
    assert os.path.exists(labels_definition_filepath)
    manager = GithubOrganizationManager(token,
                                        organization)

    # load file
    label_definitions = None
    with open(labels_definition_filepath, 'r', encoding='utf8') as labels_json:
        label_definitions = json.load(labels_json)
    assert label_definitions
    defined_label_names = [label['name'] for label in label_definitions]
    repositories = tuple(repositories)
    for repository in manager.repositories(names=repositories):
        existing_label_names = [label['name']for label in repository.labels]
        for label_definition in label_definitions:
            repository.create_label(label_definition['name'],
                                    label_definition['description'],
                                    label_definition['color'])
            created_labels.append(label_definition)

        if delete:
            undefined_label_names = set(existing_label_names) - set(defined_label_names)
            for label_name in undefined_label_names:
                repository.delete_label(label_name)
                deleted_labels.append(label_name)

    return created_labels, deleted_labels  


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-o', '--organization',
                        default='abeja-inc',
                        help='Github Organization Name')
    parser.add_argument('-t', '--token',
                        default=os.environ.get('GITHUB_OAUTH_TOKEN', None),
                        help='GITHUB OAUTH Token')
    parser.add_argument('-r', '--repositories',
                        default=None,
                        nargs='+',
                        help='Repository Name(s) to apply labels to [DEFAULT=None]')
    parser.add_argument('-l', '--labels-filepath',
                        dest='labels_filepath',
                        required=True,
                        default=None,
                        help='Specify the file that contains the labels to define for the given repositories.')
    parser.add_argument('--delete',
                        action='store_true',
                        default=False,
                        help='DELETE existing labels not specified in given definitions file',
                        )
    parser.add_argument('--verbose',
                        action='store_true',
                        default=False,
                        help='If given, DEBUG info will be displayed')
    args = parser.parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    created, deleted = update_repository_labels(args.organization,
                                                args.token,
                                                args.repositories,
                                                args.labels_filepath,
                                                args.delete)
    print('Created: {}'.format(created))
    print('Deleted: {}'.format(deleted))