__author__ = 'matth'

from processfamily import ChildProcess, start_child_process, ProcessFamily
import logging
import BaseHTTPServer
import argparse
import os
from processfamily.test import Config

class MyHTTPRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):

    def do_GET(self):
        """Serve a GET request."""
        t = self.get_response_text()
        self.send_head(t)
        self.wfile.write(t)

    def do_HEAD(self):
        """Serve a HEAD request."""
        self.send_head(self.get_response_text())

    def get_response_text(self):
        return u"Hello World".encode("UTF-8")

    def send_head(self, content):
        """Common code for GET and HEAD commands.

        This sends the response code and MIME headers.

        """
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", len(content))
        self.end_headers()

class ChildProcessForTests(ChildProcess):

    def init(self):
        arg_parser = argparse.ArgumentParser(description='ChildProcessForTests')
        arg_parser.add_argument('child_number', type=int)
        arg_parser.add_argument('port', type=int)
        arg_parser.add_argument('--cpu_number', type=int)
        args = arg_parser.parse_args()
        self.child_number = args.child_number
        self.httpd = BaseHTTPServer.HTTPServer(("", args.port), MyHTTPRequestHandler)

    def run(self):
        self.httpd.serve_forever()

    def stop(self, timeout=None):
        self.httpd.shutdown()

class ProcessFamilyForTests(ProcessFamily):
    def __init__(self, number_of_child_processes=None, run_as_script=True):
        super(ProcessFamilyForTests, self).__init__(
            child_process_module_name='processfamily.test.ChildProcess',
            number_of_child_processes=number_of_child_processes,
            run_as_script=run_as_script)

    def get_child_process_cmd(self, child_number):
        return super(ProcessFamilyForTests, self).get_child_process_cmd(child_number) + [
            str(child_number),
            str(self.get_port_nr(child_number))]

    def get_port_nr(self, child_number):
        return Config.get_starting_port_nr() + child_number + 1



if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    start_child_process(ChildProcessForTests())