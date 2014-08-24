__author__ = 'matth'

import BaseHTTPServer
import SocketServer
import argparse
from processfamily.test import Config
import logging
import logging.handlers
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
else:
    import prctl

def crash():
    """
    crash the Python interpreter...
    see https://wiki.python.org/moin/CrashingPython
    """
    exec CodeType(0, 5, 8, 0, "hello moshe", (), (), (), "", "", 0, "")

if sys.platform.startswith('win'):
    #Using a PyDLL here instead of a WinDLL causes the GIL to be acquired:
    _kernel32 = ctypes.PyDLL('kernel32.dll')
    def hold_gil(timeout):
        try:
            logging.info("Stealing GIL for %ss", timeout)
            _kernel32.Sleep(timeout*1000)
            logging.info("Released GIL")
        except ValueError as e:
            #This happens because it does some sneaky checking of things at the end of the
            #function call and notices that it has been tricked in to using the wrong calling convention
            #(because we are using PyDLL instead of WinDLL)
            #See http://python.net/crew/theller/ctypes/tutorial.html#calling-functions
            pass
else:
    _libc = ctypes.PyDLL('libc.so.6')
    def hold_gil(timeout):
        #Using a PyDLL here instead of a CDLL causes the GIL to be acquired:
        logging.info("Stealing GIL for %ss", timeout)
        _libc.sleep(timeout)
        logging.info("Released GIL")

class MyHTTPRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):

    funkyserver = None
    http_server = None

    def do_GET(self):
        """Serve a GET request."""
        t = self.get_response_text()
        if self.send_head(t):
            self.wfile.write(t)
            #I preempt the finish operation here so that processing of this request is all done before we crash or whatever:
            self.finish()
            self.http_server.shutdown_request(self.connection)

            if self.path.startswith('/crash'):
                crash()
            if self.path.startswith('/stop'):
                self.funkyserver.stop()
            if self.path.startswith('/interrupt_main'):
                thread.interrupt_main()
            if self.path.startswith('/exit'):
                os._exit(1)
            if self.path.startswith('/hold_gil_'):
                t = int(self.path.split('_')[-1])
                hold_gil(t)

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
        if self.path.lower().startswith('/favicon'):
            self.send_error(404, "File not found")
            return False

        self.send_response(200)
        self.send_header("Content-type", "application/json; charset=utf-8")
        self.send_header("Connection", "close")
        self.end_headers()
        return True

class MyHTTPServer(SocketServer.ThreadingMixIn, BaseHTTPServer.HTTPServer):
    def __init__(self, port):
        MyHTTPRequestHandler.http_server = self
        BaseHTTPServer.HTTPServer.__init__(self, ("", port), MyHTTPRequestHandler)

class FunkyWebServer(object):

    def __init__(self):
        arg_parser = argparse.ArgumentParser(description='FunkyWebServer')
        arg_parser.add_argument('--process_number', type=int)
        arg_parser.add_argument('--num_children', type=int)
        args = arg_parser.parse_args()
        self.process_number = args.process_number or 0

        logsdir = os.path.join(os.path.dirname(__file__), 'tmp', 'logs')
        if not os.path.exists(logsdir):
            os.makedirs(logsdir)
        logFormatter = logging.Formatter('%(asctime)s %(message)s')
        loghandler = logging.handlers.TimedRotatingFileHandler(os.path.join(logsdir, "process-%02d-log.txt" % self.process_number), when="midnight")
        loghandler.setFormatter(logFormatter)
        logger = logging.getLogger()
        logger.addHandler(loghandler)

        if not sys.platform.startswith('win'):
            if self.process_number > 0:
                prctl.set_name('python-pfchild')
            else:
                prctl.set_name('python-pfparent')


        self.num_children = args.num_children or 3
        port = Config.get_starting_port_nr() + self.process_number
        logging.info("Process %d listening on port %d", self.process_number, port)
        MyHTTPRequestHandler.funkyserver = self
        self.httpd = MyHTTPServer(port)


    def run(self):
        self.httpd.serve_forever()

    def stop(self):
        self.httpd.shutdown()