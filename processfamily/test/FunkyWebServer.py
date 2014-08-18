__author__ = 'matth'

import BaseHTTPServer
import argparse
from processfamily.test import Config
import logging
import threading
import thread
import os
from types import CodeType

def crash():
    """
    crash the Python interpreter...
    see https://wiki.python.org/moin/CrashingPython
    """
    exec CodeType(0, 5, 8, 0, "hello moshe", (), (), (), "", "", 0, "")

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
        if self.path.startswith('/interrupt'):
            threading.Timer(0.5, thread.interrupt_main).start()
        if self.path.startswith('/exit'):
            threading.Timer(0.5, os._exit, args=[1]).start()



    def do_HEAD(self):
        """Serve a HEAD request."""
        self.send_head(self.get_response_text())

    def get_response_text(self):

        return u"OK".encode("UTF-8")

    def send_head(self, content):
        """Common code for GET and HEAD commands.

        This sends the response code and MIME headers.

        """
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", len(content))
        self.end_headers()

class FunkyWebServer(object):

    def __init__(self):
        arg_parser = argparse.ArgumentParser(description='FunkyWebServer')
        arg_parser.add_argument('--process_number', type=int)
        arg_parser.add_argument('--num_children', type=int)
        args = arg_parser.parse_args()
        self.process_number = args.process_number or 0
        self.num_children = args.num_children or 1
        port = Config.get_starting_port_nr() + self.process_number
        logging.info("Process %d listening on port %d", self.process_number, port)
        MyHTTPRequestHandler.funkyserver = self
        self.httpd = BaseHTTPServer.HTTPServer(("", port), MyHTTPRequestHandler)


    def run(self):
        self.httpd.serve_forever()

    def stop(self):
        self.httpd.shutdown()