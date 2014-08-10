__author__ = 'Administrator'

import unittest
import time
from __init__ import ProcessFamily

class TestStartStop(unittest.TestCase):
    def test_start_stop_one(self):
        family = ProcessFamily(child_process_module_name='ChildProcessForTests', number_of_child_processes=1)
        family.start()
        time.sleep(5)
        family.stop()

