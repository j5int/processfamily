__author__ = 'matth'

import unittest
import time
from processfamily import ProcessFamily
import logging

class TestStartStop(unittest.TestCase):
    def test_start_stop_one(self):
        family = ProcessFamily(child_process_module_name='processfamily.test.ChildProcess', number_of_child_processes=1)
        family.start()
        family.stop()

    def test_start_stop_three(self):
        family = ProcessFamily(child_process_module_name='processfamily.test.ChildProcess', number_of_child_processes=3)
        family.start()
        family.stop()
