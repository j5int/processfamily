__author__ = 'matth'

import os

pythonw_exe = "c:\\Python27\\pythonw.exe"
svc_name = 'ProcessFamilyTest'
def get_starting_port_nr():
    return int(os.environ.get("PROCESSFAMILY_TESTS_STARTING_PORT_NR", "9080"))