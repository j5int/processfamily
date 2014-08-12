__author__ = 'matth'

import unittest
import time
from processfamily.test import ChildProcess
import logging

class TestStartStop(unittest.TestCase):
    def test_start_stop_one(self):
        family = ChildProcess.ProcessFamilyForTests(number_of_child_processes=1)
        family.start()
        family.stop()

    def test_start_stop_three(self):
        family = ChildProcess.ProcessFamilyForTests(number_of_child_processes=3)
        family.start()
        family.stop()
