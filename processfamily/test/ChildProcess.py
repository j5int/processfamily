__author__ = 'matth'

from processfamily import ChildProcess, start_child_process
import logging
import BaseHTTPServer

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

    def __init__(self):
        self.httpd = BaseHTTPServer.HTTPServer(("", 9081), MyHTTPRequestHandler)

    def run(self):
        self.httpd.serve_forever()

    def stop(self, timeout=None):
        self.httpd.shutdown()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    start_child_process(ChildProcessForTests())