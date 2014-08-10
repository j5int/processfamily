
__author__ = 'matth'

from processfamily import ProcessFamily
from processfamily.test import ChildProcess
import time
import sys
import os

class MyProcessFamily(ProcessFamily):
    def get_child_process_cmd(self):
        return [sys.executable, os.path.join(os.path.dirname(ChildProcess.__file__), 'ChildProcess.py')]

if __name__ == '__main__':
    print "Starting"
    family = MyProcessFamily(number_of_child_processes=1)
    family.start()
    time.sleep(5)
    family.stop()
    print "Done"