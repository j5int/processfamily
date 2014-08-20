__author__ = 'matth'

import BaseHTTPServer
import argparse
from processfamily.test import Config
import logging
import threading
import thread
import os
from types import CodeType
import json
import sys
import ctypes

if sys.platform.startswith('win'):
    import win32job
    import win32api

def crash():
    """
    crash the Python interpreter...
    see https://wiki.python.org/moin/CrashingPython
    """
    exec CodeType(0, 5, 8, 0, "hello moshe", (), (), (), "", "", 0, "")

if sys.platform.startswith('win'):
    def hold_gil(timeout):
        #Using a PyDLL here instead of a WinDLL causes the GIL to be acquired:
        kernel32 = ctypes.PyDLL('kernel32.dll')
        try:
            logging.info("Stealing GIL for %ss", timeout)
            kernel32.Sleep(timeout*1000)
            logging.info("Released GIL")
        except ValueError as e:
            #This happens because it does some sneaky checking of things at the end of the
            #function call and notices that it has been tricked in to using the wrong calling convention
            #(because we are using PyDLL instead of WinDLL)
            #See http://python.net/crew/theller/ctypes/tutorial.html#calling-functions
            pass
else:
    def hold_gil(timeout):
        #Using a PyDLL here instead of a CDLL causes the GIL to be acquired:
        libc = ctypes.PyDLL('libc.so.6')
        logging.info("Stealing GIL for %ss", timeout)
        libc.sleep(timeout)
        logging.info("Released GIL")

class MyHTTPRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):

    funkyserver = None

    def do_GET(self):
        """Serve a GET request."""
        t = self.get_response_text()
        self.send_head(t)
        self.wfile.write(t)
        if self.path.startswith('/crash'):
            threading.Timer(0.5, crash).start()
        if self.path.startswith('/stop'):
            threading.Timer(0.5, self.funkyserver.stop).start()
        if self.path.startswith('/interrupt_main'):
            threading.Timer(0.5, thread.interrupt_main).start()
        if self.path.startswith('/exit'):
            threading.Timer(0.5, os._exit, args=[1]).start()
        if self.path.startswith('/hold_gil_'):
            t = int(self.path.split('_')[-1])
            threading.Timer(0.5, hold_gil, args=[t]).start()

    def do_HEAD(self):
        """Serve a HEAD request."""
        self.send_head(self.get_response_text())

    def get_response_text(self):
        return self._to_json_rsp(self.get_response_object())

    def get_response_object(self):
        if self.path.startswith('/injob'):
            return json.dumps(win32job.IsProcessInJob(win32api.GetCurrentProcess(), None), indent=3)
        if self.path.startswith('/job'):
            extended_info = win32job.QueryInformationJobObject(None, win32job.JobObjectExtendedLimitInformation)

            return json.dumps(extended_info, indent=3)
        return "OK"

    def _to_json_rsp(self, o):
        return json.dumps(o, indent=3, encoding='UTF-8')

    def send_head(self, content):
        """Common code for GET and HEAD commands.

        This sends the response code and MIME headers.

        """
        self.send_response(200)
        self.send_header("Content-type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(content))
        self.end_headers()

class FunkyWebServer(object):

    def __init__(self):
        arg_parser = argparse.ArgumentParser(description='FunkyWebServer')
        arg_parser.add_argument('--process_number', type=int)
        arg_parser.add_argument('--num_children', type=int)
        args = arg_parser.parse_args()
        self.process_number = args.process_number or 0
        self.num_children = args.num_children or 3
        port = Config.get_starting_port_nr() + self.process_number
        logging.info("Process %d listening on port %d", self.process_number, port)
        MyHTTPRequestHandler.funkyserver = self
        self.httpd = BaseHTTPServer.HTTPServer(("", port), MyHTTPRequestHandler)


    def run(self):
        self.httpd.serve_forever()

    def stop(self):
        self.httpd.shutdown()