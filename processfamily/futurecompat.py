"""Most of this file has been copied from j5pythonpath in the framework"""

from __future__ import print_function
from __future__ import absolute_import
from __future__ import division
from __future__ import unicode_literals
from future import standard_library
standard_library.install_aliases()
from builtins import *

from future.utils import text_to_native_str, PY3, native

import locale
import sys
import os


def text_to_fs(t):
    """convert text to native_str, using the file system encoding, preserving None"""
    # PY2COMPAT: used to handle python2 requiring native str in encoding, and for type consistency of file system paths
    # also handle use during startup when filesystemencoding not yet initialized, within this module
    if t is None:
        return t
    return text_to_native_str(t, sys.getfilesystemencoding() or locale.getpreferredencoding())


def fs_to_text(s):
    """convert a native_str to text, using the file system encoding, preserving None"""
    # PY2COMPAT: used to handle python2 requiring native str in encoding, and for type consistency of file system paths
    if s is None:
        return s
    if PY3:
        return s
    # note that there isn't a native_str_to_text: this is the equivalent
    # also handle use during startup when filesystemencoding not yet initialized, within this module
    return native(s).decode(sys.getfilesystemencoding() or locale.getpreferredencoding())

# FUTURIZE_REVIEW: how to handle environment variables and filesystem encodings on Python 2
#
# We are using the filesystem encoding for the environment variables on Python 2 to retain existing behaviour.
# (Py3 is better: https://docs.python.org/3/library/os.html#file-names-command-line-arguments-and-environment-variables)
#
# However, this doesn't actually work properly for characters that can't be encoded with the filesystemencoding.
# For further info on this, see https://gist.github.com/davidfraser/b338ba07a6f058535a2d9786986ed8a3


_env_default = object()
def get_env(key, default=_env_default):
    """the same as os.environ[key] or os.environ.get(key, default), but key must be text and is converted with text_to_fs, and response is converted with fs_to_text"""
    key = text_to_fs(key)
    if default is _env_default:
        return fs_to_text(os.environ[key])
    result = fs_to_text(os.environ.get(key, None))
    return default if result is None else result


def has_env(key):
    """the same as key in os.environ, but key must be text and is converted with text_to_fs"""
    return text_to_fs(key) in os.environ


def set_env(key, value):
    """the same as os.environ[key] = value, but key and value must be text and are converted with text_to_fs"""
    os.environ[text_to_fs(key)] = text_to_fs(value)


def update_env(d, update_copy_of_env=None):
    """the same as os.environ.update(d), but keys and values of dict must be text and are converted with text_to_fs"""
    if update_copy_of_env is None:
        update_copy_of_env = os.environ
    update_copy_of_env.update({text_to_fs(key): text_to_fs(value) for key, value in d.items()})


def get_env_dict():
    """returns a copy of os.environ where keys and values are text, converted with text_to_fs"""
    return {text_to_fs(key): text_to_fs(value) for key, value in os.environ.items()}


def list_to_native_str(l):
    """Convert a list of text to a list of native_str"""
    return [text_to_native_str(i) for i in l]