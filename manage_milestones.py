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

    parser.add_argument('--verbose',
                        action='store_true',
                        default=False,
                        help='If given, DEBUG info will be displayed')
    subparsers = parser.add_subparsers()
    milestone_parser = subparsers.add_parser('miletones')
    milestone_parser.add_argument('-d', '--dump',
                                  action='store_true',
                                  default=False,
                                  help='Dump MILESTONES for the given repoistory')
    args = parser.parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    manager = GithubOrganizationManager(args.token,
                                        args.organization)
    repository = next(manager.repositories(name=args.repository))  # should only be 1
    print(repository.milestones)
