import os
import logging
from ghorgs.managers import GithubOrganizationManager

logging.basicConfig(format='%(asctime) [%(level)s]: %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-t', '--token',
                        default=os.environ.get('GITHUB_OAUTH_TOKEN', None),
                        help='GITHUB OAUTH Token')
    parser.add_argument('-o', '--organization',
                        default='abeja-inc',
                        help='Github Organization Name')
    parser.add_argument('-r', '--repository',
                        default=None,
                        help='Project Name Filter(s) [DEFAULT=None]')
    parser.add_argument('-l', '--labels',
                        nargs='+',
                        default=None,
                        help='1 or more label names to add to the repository')
    DEFAULT_LABEL_COLOR = 'f29513'
    parser.add_argument('-c', '--color',
                        default=DEFAULT_LABEL_COLOR,
                        help='Color for label(s)')
    parser.add_argument('--verbose',
                        action='store_true',
                        default=False,
                        help='If given, DEBUG info will be displayed')
    args = parser.parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    manager = GithubOrganizationManager(args.token,
                                        args.organization)
    repository = next(manager.repositories(name=args.repository))  # should only be 1
    for label_name in args.labels:
        repository.create_label(label_name, color=args.color)
