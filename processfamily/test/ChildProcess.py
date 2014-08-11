__author__ = 'matth'

from processfamily import ChildProcess, start_child_process
import threading
import logging

class ChildProcessForTests(ChildProcess):

    def __init__(self):
        self.stop_event = threading.Event()

    def run(self):
        while not self.stop_event.is_set():
            logging.info("Child doing stuff")
            self.stop_event.wait(2)

    def stop(self, timeout=None):
        self.stop_event.set()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    start_child_process(ChildProcessForTests())