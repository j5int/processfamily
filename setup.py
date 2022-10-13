from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from future import standard_library
standard_library.install_aliases()
from builtins import *
__author__ = 'matth'

from distutils.core import setup
from setuptools import find_packages
import sys

setup(
    name='processfamily',
    version='0.9',
    packages = find_packages(),
    license='Apache License, Version 2.0',
    description='A library for launching, maintaining, and terminating a family of long-lived python child processes on Windows and *nix.',
    long_description=open('README.md').read(),
    long_description_content_type="text/markdown",
    url='https://github.com/j5int/processfamily/',
    author='j5 International',
    author_email='support@j5int.com',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: Apache Software License',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    install_requires = ["json-rpc", "future"] + (['pywin32', "mozprocess"] if sys.platform.startswith("win") else []),
    extras_require = {
        'tests': ['pytest', 'pytest-lazy-fixture', 'requests'] + (['py-exe-builder'] if sys.platform.startswith("win") else []),
    }
)
