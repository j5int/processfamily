__author__ = 'matth'
import sys
import os
from py2exe.build_exe import py2exe as build_exe
from py2exe.build_exe import Target
import tempfile
import shutil
import json
from distutils.dist import Distribution
import ctypes.util

#These too imports have weird contortions to find DLLs: (look at the source in pywintypes.py)
#They also do something different if 'frozen' - which is the case when running from the exe
import pywintypes
import pythoncom


SCRIPTS = []
SERVICE = Target(
        # used for the versioninfo resource
        description = "A testing windows service for processfamily",
        # what to build. For a service, the module name (not the
        # filename) must be specified!
        modules = ["processfamily.test.Win32Service"],
        cmdline_style='custom',
        dest_base = 'processfamily-test-svc',
    )


class my_py2exe(build_exe):

    def __init__(self, *args, **kwargs):
        build_exe.__init__(self, *args, **kwargs)
        self._tmp_file_list = []

    def get_boot_script(self, boot_type):
        bootscript = build_exe.get_boot_script(self, boot_type)
        if boot_type == 'common':

            #When 'frozen' pywintypes and pythoncom find their DLLs looking on the python path
            extra_path = set()
            extra_path.add(os.path.dirname(pywintypes.__file__))
            extra_path.add(os.path.dirname(pythoncom.__file__))

            with open(bootscript, 'r') as f:
                src = f.read()

            src = r"""
# Fix up the system path so that we can run off a normal python install:

import sys

sys.prefix = %s
sys.exec_prefix = %s

sys.path = %s

import site

""" % (json.dumps(sys.prefix), json.dumps(sys.exec_prefix), json.dumps(
                sys.path + list(extra_path), indent=4)) + src

            (fd, name) = tempfile.mkstemp(suffix='svcboot.py', text=True)
            self._tmp_file_list.append(name)
            with os.fdopen(fd, 'w') as f:
                f.write(src)

            return name
        return bootscript

    def build_exe(self, dest_dir):
        try:
            self.dist_dir = dest_dir
            self.lib_dir = self.dist_dir
            self.distribution.zipfile = 'Dummy'
            self.bundle_files = 3
            self.skip_archive = True
            arcname = '.'
            dst = self.build_service(SERVICE, self.get_service_template(), arcname)
        finally:
            for f in self._tmp_file_list:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except:
                        pass

        python_dll = ctypes.util.find_library("Python27.dll")
        assert python_dll and os.path.exists(python_dll)
        shutil.copy2(python_dll, dest_dir)

def build_service_exe():
    dest_dir = os.path.join(os.path.dirname(__file__), "tmp", "bin")
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)

    my_py2exe(Distribution()).build_exe(dest_dir)

    return os.path.join(dest_dir, 'processfamily-test-svc.exe')

if __name__ == '__main__':
    build_service_exe()