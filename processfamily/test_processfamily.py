__author__ = 'matth'

import unittest
import sys
from processfamily.test import ParentProcess, Config
import os
import subprocess
import requests
import time

class TestStartStop(unittest.TestCase):
    def test_start_stop_one(self):
        family = ParentProcess.ProcessFamilyForTests(number_of_child_processes=1)
        family.start()
        family.stop()

    def test_start_stop_three(self):
        family = ParentProcess.ProcessFamilyForTests(number_of_child_processes=3)
        family.start()
        family.stop()

class _BaseProcessFamilyFunkyWebServerTestSuite(unittest.TestCase):
    def test_start_stop(self):
        time.sleep(5)
        self.send_parent_http_command("stop")

    def get_path_to_ParentProcessPy(self):
        return os.path.join(os.path.dirname(__file__), 'test', 'ParentProcess.py')

    def send_parent_http_command(self, command):
        return self.send_http_command(Config.get_starting_port_nr(), command)

    def send_http_command(self, port, command):
        r = requests.get('http://localhost:%d/%s' % (port, command))
        return r.json


class NormalSubprocessServiceTests(_BaseProcessFamilyFunkyWebServerTestSuite):
    def setUp(self):
        self.parent_process = subprocess.Popen(
            [sys.executable, self.get_path_to_ParentProcessPy()],
            close_fds=True)

    def tearDown(self):
        self.parent_process.wait()




#Remove the base class from the module dict so it isn't smelled out:
del(_BaseProcessFamilyFunkyWebServerTestSuite)