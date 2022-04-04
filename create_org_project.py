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
                        help='Github Organization Name',
                        required=True)
    parser.add_argument('-n', '--name', type=str, help="project name", required=True)
    parser.add_argument("-d", "--description", type=str, help="project description")
    parser.add_argument('--verbose',
                        action='store_true',
                        default=False,
                        help='If given, DEBUG info will be displayed')
    args = parser.parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    if args.token:
        manager = GithubOrganizationManager(args.organization, args.token)
    else:
        manager = GithubOrganizationManager(args.organization)
    project_url, responses = manager.create_organizational_project(name=args.name, description=args.description)
    logger.info(f'project_url={project_url}')
    for r in responses:
        logger.info(f"response={r}")


