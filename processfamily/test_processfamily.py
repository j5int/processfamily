__author__ = 'matth'

import unittest
import sys
from processfamily.test import ParentProcess, Config
import os
import subprocess
import requests
import time
import socket
import logging

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
    def test_start_stop1(self):
        time.sleep(5)
        self.send_parent_http_command("stop")

    def test_start_stop2(self):
        time.sleep(5)
        self.send_parent_http_command("stop")

    def check_server_ports_unbound(self):
        for pnumber in range(4):
            port = Config.get_starting_port_nr() + pnumber
            #I just try and bind to the server port and see if I have a problem:
            logging.info("Checking for ability to bind to port %d", port)
            serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                serversocket.bind(("", port))
            finally:
                serversocket.close()

    def get_path_to_ParentProcessPy(self):
        return os.path.join(os.path.dirname(__file__), 'test', 'ParentProcess.py')

    def send_parent_http_command(self, command):
        return self.send_http_command(Config.get_starting_port_nr(), command)

    def send_http_command(self, port, command):
        r = requests.get('http://localhost:%d/%s' % (port, command))
        return r.json


class NormalSubprocessServiceTests(_BaseProcessFamilyFunkyWebServerTestSuite):
    def setUp(self):
        self.check_server_ports_unbound()
        self.parent_process = subprocess.Popen(
            [sys.executable, self.get_path_to_ParentProcessPy()],
            close_fds=True)

    def tearDown(self):
        self.parent_process.wait()
        self.check_server_ports_unbound()



#Remove the base class from the module dict so it isn't smelled out:
del(_BaseProcessFamilyFunkyWebServerTestSuite)