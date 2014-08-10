__author__ = 'matth'

import unittest
import time
from __init__ import ProcessFamily

class TestStartStop(unittest.TestCase):
    def test_start_stop_one(self):
        family = ProcessFamily(child_process_module_name='processfamily.test.ChildProcessForTests', number_of_child_processes=1)
        family.start()
        time.sleep(5)
        family.stop()

