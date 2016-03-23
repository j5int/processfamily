__author__ = 'matth'

import os
import sys

test_command = None
startup_log_filename = None

def _log_to_file(msg):
    global startup_log_filename
    if startup_log_filename is None:
        return
    with open(startup_log_filename, "a") as pid_log_f:
        pid_log_f.write("%s\n" % msg)

if __name__ == '__main__':
    pid = os.getpid()
    pid_filename = os.path.join(os.path.dirname(__file__), 'tmp', 'pid', 'c%s.pid' % pid)
    if not os.path.exists(os.path.dirname(pid_filename)):
        os.makedirs(os.path.dirname(pid_filename))
    with open(pid_filename, "w") as pid_f:
        pid_f.write("%s\n" % pid)

    if len(sys.argv) >= 3 and sys.argv[1] == '--process_number':
        startup_log_filename = os.path.join(os.path.dirname(__file__), 'tmp', 'logs', 'startup-log-%s.log' % sys.argv[2])
        if not os.path.exists(os.path.dirname(startup_log_filename)):
            os.makedirs(os.path.dirname(startup_log_filename))
        with open(startup_log_filename, "w") as f:
            f.write("Started: %s\n" % pid)

    _log_to_file('Starting up %r' % sys.argv)

    if len(sys.argv) >= 3 and sys.argv[1] == '--process_number' and sys.argv[2] == '2':
        _log_to_file('Trying to read command file')
        command_file = os.path.join(os.path.dirname(__file__), 'tmp', 'command.txt')
        if os.path.exists(command_file):
            with open(command_file, "r") as f:
                command = f.read()
            _log_to_file('Read command %s' % command)
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

_log_to_file('importing traceback')
import traceback
def _traceback_str():
    exc_info = sys.exc_info()
    return "".join(traceback.format_exception(exc_info[0], exc_info[1], exc_info[2]))

try:
    _log_to_file('doing imports')
    from processfamily import ChildProcess, start_child_process
    import logging
    import signal
    from processfamily.test.FunkyWebServer import FunkyWebServer, hold_gil
    if sys.platform.startswith('win'):
        from processfamily.win32Popen import open_commandline_passed_stdio_streams
    _log_to_file('imports finished')
except Exception as e:
    _log_to_file(_traceback_str())
    raise

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
        signal.signal(signal.SIGINT, self.signal_handler)

    def signal_handler(self, signum, frame):
        if signum == signal.SIGINT:
            logging.info("Stopping server - process %d", os.getpid())
            self.server.stop()

    def run(self):
        if test_command == 'child_error_during_run':
            raise ValueError('I was told to fail')
        self.server.run()

    def stop(self, timeout=None):
        if hasattr(self, 'server'):
            self.server.stop()

_log_to_file('ChildProcessForTests defined')

if __name__ == '__main__':
    if len(sys.argv) > 5:
        _log_to_file('Trying to open stdio streams')
        open_commandline_passed_stdio_streams()
    _log_to_file("Setting up regular logging")
    logging.basicConfig(level=logging.INFO)
    _log_to_file("Starting child process")
    start_child_process(ChildProcessForTests())