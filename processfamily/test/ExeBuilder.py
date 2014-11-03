__author__ = 'matth'
import sys
import os
from pyexebuilder.ExeBuilder import ExeBuilder

#These too imports have weird contortions to find DLLs: (look at the source in pywintypes.py)
#They also do something different if 'frozen' - which is the case when running from the exe
import pywintypes
import pythoncom

class ServiceExeBuilder(ExeBuilder):

    def __init__(self, dest_dir):
        super(ServiceExeBuilder, self).__init__(dest_dir,
                 service_module='processfamily.test.Win32Service',
                 module_exe_name='processfamily-test-svc.exe')

    def get_code_snippet_to_set_sys_path(self):
        return r"""
sys.path = %r
sys.path.append(%r)
sys.path.append(%r)
""" % (sys.path,
       os.path.abspath(os.path.dirname(pywintypes.__file__)),
       os.path.abspath(os.path.dirname(pythoncom.__file__)),
        )

def build_service_exe():
    dest_dir = os.path.join(os.path.dirname(__file__), "tmp", "bin")
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)

    ServiceExeBuilder(dest_dir).build()

    return os.path.join(dest_dir, 'processfamily-test-svc.exe')

if __name__ == '__main__':
    build_service_exe()