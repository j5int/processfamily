__author__ = 'Administrator'

import subprocess
import os
import threading
from processfamily import _traceback_str
from processfamily.test import Config
from processfamily.processes import  kill_process
import time

def get_path_to_ParentProcessPy():
    return os.path.join(os.path.dirname(__file__), 'ParentProcess.py')

if __name__ == '__main__':
    parent_process = subprocess.Popen(
        [Config.pythonw_exe, get_path_to_ParentProcessPy()],
        close_fds=True)

    def wait_for_end():
        try:
            while True:
                print 'Waiting'
                if parent_process.poll() is not None:
                    print 'Ended'
                    return
                time.sleep(1)
        except Exception as e:
            print _traceback_str()

    t = threading.Thread(target=parent_process.wait)
    t.start()
    try:
        while t.isAlive():
            t.join(1)
    except Exception as e:
        kill_process(parent_process.pid)
    print "Done"