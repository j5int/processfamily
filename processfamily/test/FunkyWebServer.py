__author__ = 'matth'

import BaseHTTPServer
import SocketServer
import urlparse
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
from processfamily import _traceback_str
import select
import errno
import socket

if sys.platform.startswith('win'):
    import win32job
    import win32api
else:
    from .. import ctypes_prctl as prctl
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
        parsed_url = urlparse.urlparse(self.path)
        params = urlparse.parse_qs(parsed_url.query)
        path = parsed_url.path
        if path.startswith('/stop'):
            # stop children before we return a response
            timeout = int((params.get("timeout", []) or ["30"])[0])
            self.funkyserver.pre_stop(timeout=timeout)
        t = self.get_response_text()
        if self.send_head(t):
            self.wfile.write(t)
            #I preempt the finish operation here so that processing of this request is all done before we crash or whatever:
            self.finish()
            self.http_server.shutdown_request(self.connection)

            if path.startswith('/crash'):
                crash()
            if path.startswith('/stop'):
                self.funkyserver.stop()
            if path.startswith('/interrupt_main'):
                thread.interrupt_main()
            if path.startswith('/exit'):
                os._exit(1)
            if path.startswith('/hold_gil'):
                t = int((params.get("t", []) or ["100"])[0])
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
        if self.path.startswith('/close_file_and_delete_it'):
            try:
                if self.funkyserver._open_file_handle is not None:
                    f = os.path.join(os.path.dirname(__file__), 'tmp', 'testfile.txt')
                    logging.info("Closing test file handle")
                    self.funkyserver._open_file_handle.close()
                    self.funkyserver._open_file_handle = None
                    assert os.path.exists(f)
                    os.remove(f)
                    assert not os.path.exists(f)
                    return "OK"
            except Exception as e:
                logging.error("Failed to close file handle and delete file: %s\n%s", e, _traceback_str())
                return "FAIL"
        if self.path.startswith('/stop'):
            logging.info("Returning child_processes_terminated: %r", self.funkyserver.child_processes_terminated)
            return repr(self.funkyserver.child_processes_terminated)
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

    def log_message(self, format, *args):
        """Log an arbitrary message.

        This is used by all other logging functions.  Override
        it if you have specific logging wishes.

        The first argument, FORMAT, is a format string for the
        message to be logged.  If the format string contains
        any % escapes requiring parameters, they should be
        specified as subsequent arguments (it's just like
        printf!).

        The client ip address and current date/time are prefixed to every
        message.

        """

        logging.info("%s - - " + format, self.client_address[0], *args)

class MyHTTPServer(SocketServer.ThreadingMixIn, BaseHTTPServer.HTTPServer):
    def __init__(self, port):
        MyHTTPRequestHandler.http_server = self
        BaseHTTPServer.HTTPServer.__init__(self, ("", port), MyHTTPRequestHandler)

    def handle_error(self, request, client_address):
        logging.error('Exception happened during processing of request from %s:\n%s', client_address, _traceback_str())

class FunkyWebServer(object):

    _open_file_handle = None

    def __init__(self):
        self.parse_args_and_setup_logging()
        self.port = Config.get_starting_port_nr() + self.process_number
        MyHTTPRequestHandler.funkyserver = self
        self.httpd_lock = threading.RLock()
        self.httpd = None
        self.child_processes_terminated = None

    @classmethod
    def parse_args_and_setup_logging(cls):
        arg_parser = argparse.ArgumentParser(description='FunkyWebServer')
        arg_parser.add_argument('--process_number', type=int)
        arg_parser.add_argument('--num_children', type=int)
        args = arg_parser.parse_args()
        cls.process_number = args.process_number or 0

        logsdir = os.path.join(os.path.dirname(__file__), 'tmp', 'logs')
        if not os.path.exists(logsdir):
            os.makedirs(logsdir)
        logFormatter = logging.Formatter('%(asctime)s %(message)s')
        loghandler = logging.handlers.TimedRotatingFileHandler(os.path.join(logsdir, "process-%02d-log.txt" % cls.process_number), when="midnight")
        loghandler.setFormatter(logFormatter)
        logger = logging.getLogger()
        logger.addHandler(loghandler)

        if not sys.platform.startswith('win'):
            if cls.process_number > 0:
                prctl.set_name('python-pfchild')
            else:
                prctl.set_name('python-pfparent')

        cls.num_children = args.num_children or 3

        if cls._open_file_handle is None and cls.process_number == 0:
            logging.info("Opening a file and keeping it open")
            cls._open_file_handle = open(os.path.join(os.path.dirname(__file__), 'tmp', 'testfile.txt'), 'w')

    def run(self):
        with self.httpd_lock:
            self.httpd = MyHTTPServer(self.port)
        logging.info("Process %d listening on port %d", self.process_number, self.port)
        self.httpd.serve_forever(poll_interval=0.1)
        logging.info("Process %d finished listening on port %d", self.process_number, self.port)

    def pre_stop(self, timeout=30):
        try:
            if hasattr(self, 'family'):
                logging.info("Stopping family...")
                self.child_processes_terminated = terminated = self.family.stop(timeout=timeout)
                if terminated:
                    logging.info("Had to terminate %d child processes", terminated)
                else:
                    logging.info("Didn't have to terminate child processes, they stopped gracefully")
        except Exception, e:
            self.child_processes_terminated = e
            logging.error("Error terminating child processes: %r", e)

    def stop(self):
        with self.httpd_lock:
            if self.httpd:
                logging.info("Shutting down httpd (in separate thread)")
                threading.Thread(name="shutdown", target=self.shutdown_httpd).start()

    def shutdown_httpd(self):
        try:
            with self.httpd_lock:
                logging.info("Shutting down httpd")
                self.httpd.shutdown()
                logging.info("Shut down httpd")
                self.httpd = None
        finally:
            if self._open_file_handle is not None:
                logging.info("Closing test file handle")
                self._open_file_handle.close()
