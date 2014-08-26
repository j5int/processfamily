__author__ = 'matth'

import os
import sys

test_command = None
if __name__ == '__main__':
    pid = os.getpid()
    pid_filename = os.path.join(os.path.dirname(__file__), 'tmp', 'pid', 'c%s.pid' % pid)
    if not os.path.exists(os.path.dirname(pid_filename)):
        os.makedirs(os.path.dirname(pid_filename))
    with open(pid_filename, "w") as pid_f:
        pid_f.write("%s\n" % pid)
    if sys.argv[-1] == '2':
        command_file = os.path.join(os.path.dirname(__file__), 'tmp', 'command.txt')
        if os.path.exists(command_file):
            with open(command_file, "r") as f:
                command = f.read()
            if command == 'child_exit_on_start':
                os._exit(25)
            elif command == 'child_freeze_on_start':
                from processfamily.test.FunkyWebServer import hold_gil
                hold_gil(10*60)
            elif command == 'child_error_on_start':
                import middle.child.syndrome
            elif command == 'child_crash_on_start':
                from processfamily.test.FunkyWebServer import crash
                crash()
            else:
                test_command = command

from processfamily import ChildProcess, start_child_process
import logging
from processfamily.test.FunkyWebServer import FunkyWebServer, hold_gil

class ChildProcessForTests(ChildProcess):

    def init(self):
        if test_command == 'child_error_during_init':
            #Pretend we were actually doing something
            FunkyWebServer.parse_args_and_setup_logging()
            logging.info("Child about to fail")
            raise ValueError('I was told to fail')
        elif test_command == 'child_freeze_during_init':
            FunkyWebServer.parse_args_and_setup_logging()
            hold_gil(10*60)
        self.server = FunkyWebServer()

    def run(self):
        if test_command == 'child_error_during_run':
            raise ValueError('I was told to fail')
        self.server.run()

    def stop(self, timeout=None):
        if hasattr(self, 'server'):
            self.server.stop()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    start_child_process(ChildProcessForTests())