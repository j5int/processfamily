__author__ = 'Administrator'

from processfamily import ChildProcess, start_child_process
import threading
import sys

class ChildProcessForTests(ChildProcess):

    def __init__(self):
        self.stop_event = threading.Event()

    def run(self):
        while not self.stop_event.is_set():
            sys.stderr.write("Child doing stuff\n")
            self.stop_event.wait(3)


    def stop(self, timeout=None):
        self.stop_event.set()

if __name__ == '__main__':
    start_child_process(ChildProcessForTests())