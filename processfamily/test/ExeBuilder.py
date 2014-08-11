__author__ = 'matth'
import sys
import os
from py2exe.build_exe import py2exe as build_exe
from py2exe.build_exe import FixupTargets, Target
import tempfile
import shutil

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

            with open(bootscript, 'r') as f:
                src = f.read()

            src = r"""
# Fix up the system path so that we can run off a normal python install:

import sys

#sys.prefix = (sys.prefix[:-1] if sys.prefix.endswith('\\') else sys.prefix) + '\\Python27'
sys.exec_prefix = sys.prefix
pythonhome = sys.prefix

sys.path = [pythonhome + x for x in [
    '\\python27.zip',
    '\\DLLs',
    '\\lib',
    '\\lib\\plat-win',
    '\\lib\\lib-tk',
    '',
    ]]

import site

""" + src

            (fd, name) = tempfile.mkstemp(suffix='svcboot.py', text=True)
            self._tmp_file_list.append(name)
            with os.fdopen(fd, 'w') as f:
                f.write(src)

            return name
        return bootscript

    def build_exes(self, scripts_dir, dest_dir):
        try:
            self.dist_dir = dest_dir
            self.lib_dir = self.dist_dir
            self.distribution.zipfile = 'Dummy'
            self.bundle_files = 3
            self.skip_archive = True
            arcname = '.'
            for target in FixupTargets([{
                                           'script': os.path.join(scripts_dir, '%s-script.py' % s),
                                            'dest_base': s
                                        } for s in SCRIPTS], 'script'):

                dst = self.build_executable(target, self.get_console_template(),
                                        arcname, target.script)

            dst = self.build_service(SERVICE, self.get_service_template(),
                                     arcname)
        finally:
            for f in self._tmp_file_list:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except:
                        pass
        #shutil.copy2(os.path.join(sys.prefix, 'Python27.dll'), dest_dir)
        shutil.copy2(os.path.join(sys.prefix, 'Lib', 'site-packages', 'pywin32_system32', 'pythoncom27.dll'),
                     os.path.join(sys.prefix, 'Lib', 'site-packages', 'win32'))
        shutil.copy2(os.path.join(sys.prefix, 'Lib', 'site-packages', 'pywin32_system32', 'pythoncomloader27.dll'),
                     os.path.join(sys.prefix, 'Lib', 'site-packages', 'win32'))
        shutil.copy2(os.path.join(sys.prefix, 'Lib', 'site-packages', 'pywin32_system32', 'pywintypes27.dll'),
                     os.path.join(sys.prefix, 'Lib', 'site-packages', 'win32'))


if __name__ == '__main__':
    from distutils.dist import Distribution
    dest_dir = sys.prefix
    scripts_dir = os.path.join(dest_dir, 'Scripts')
    my_py2exe(Distribution()).build_exes(scripts_dir, dest_dir)