__author__ = 'matth'

import os
import sys

pythonw_exe = os.path.join(sys.prefix, "pythonw.exe")
svc_name = 'ProcessFamilyTest'
def get_starting_port_nr():
    return int(os.environ.get("PROCESSFAMILY_TESTS_STARTING_PORT_NR", "9080"))