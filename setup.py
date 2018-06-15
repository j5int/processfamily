
__author__ = 'matth'

from distutils.core import setup
from setuptools import find_packages
import sys

setup(
    name='processfamily',
    version='0.7',
    packages = find_packages(),
    license='Apache License, Version 2.0',
    description='A library for launching, maintaining, and terminating a family of long-lived python child processes on Windows and *nix.',
    long_description=open('README.md').read(),
    url='http://www.j5int.com/',
    author='j5 International',
    author_email='support@j5int.com',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: Apache Software License',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2 :: Only',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    install_requires = ["json-rpc", "affinity"] + (['pywin32', "mozprocess"] if sys.platform.startswith("win") else []),
    extras_require = {
        'tests': ['nose', 'requests'] + (['py-exe-builder'] if sys.platform.startswith("win") else []),
    }
)
