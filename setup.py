from setuptools import setup
from ghorgs import __version__

setup(
    name='ghorgs',
    version=__version__,
    packages=['ghorgs'],
    url='https://github.com/monkut/github-org-manager',
    install_requires=['requests', 'python-dateutil'],
    license='MIT',
    author='Shane Cousins',
    author_email='shane.cousins@gmail.com',
    description='Github Wrapper for Organization Projects'
)
