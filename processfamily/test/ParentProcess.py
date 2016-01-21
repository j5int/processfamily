# -*- coding: utf-8 -*-
__author__ = 'matth'

import os
import sys
if __name__ == '__main__':
    #python issue 18298
    if sys.platform.startswith('win'):
        #When running under pythonw.exe you can end up with 'invalid' files for stdin+stdout+stder
        #For this reason, I just open devnull for them
        # (this was a problem because the HTTPServer tries to write to stderr
        if sys.stderr.fileno() < 0:
            sys.stderr = open(os.devnull, "w")
        if sys.stdout.fileno() < 0:
            sys.stdout = open(os.devnull, "w")
        if sys.stdin.fileno() < 0:
            sys.stdin = open(os.devnull, "r")

    pid = os.getpid()
    pid_filename = os.path.join(os.path.dirname(__file__), 'tmp', 'pid', 'p%s.pid' % pid)
    if not os.path.exists(os.path.dirname(pid_filename)):
        os.makedirs(os.path.dirname(pid_filename))
    with open(pid_filename, "w") as pid_f:
        pid_f.write("%s\n" % pid)

import processfamily
from processfamily.test.FunkyWebServer import FunkyWebServer
import logging
from processfamily.threads import stop_threads
import threading

if sys.platform.startswith('win'):
    from processfamily._winprocess_ctypes import CAN_USE_EXTENDED_STARTUPINFO

class ProcessFamilyForTests(processfamily.ProcessFamily):
    WIN_PASS_HANDLES_OVER_COMMANDLINE = True

    def __init__(self, number_of_child_processes=None, run_as_script=True):
        self.override_command_line = None
        command_file = os.path.join(os.path.dirname(__file__), 'tmp', 'command.txt')
        if os.path.exists(command_file):
            with open(command_file, "r") as f:
                command = f.read()
            if command == 'echo_std_err':
                self.ECHO_STD_ERR = True
            elif command == 'handles_over_commandline_off':
                self.WIN_PASS_HANDLES_OVER_COMMANDLINE = False
            elif command == 'handles_over_commandline_off_close_fds_off':
                self.WIN_PASS_HANDLES_OVER_COMMANDLINE = False
                self.CLOSE_FDS = False
            elif command == 'close_fds_off':
                self.CLOSE_FDS = False
            elif command == 'use_job_object_off':
                self.WIN_USE_JOB_OBJECT = False
            elif command == 'cpu_affinity_off':
                self.CPU_AFFINITY_STRATEGY = None
            elif command == 'use_cat' or command == 'use_cat_comms_none':
                self.WIN_PASS_HANDLES_OVER_COMMANDLINE = False
                self.CHILD_COMMS_STRATEGY = processfamily.CHILD_COMMS_STRATEGY_PIPES_CLOSE if command == 'use_cat' else processfamily.CHILD_COMMS_STRATEGY_NONE
                if sys.platform.startswith('win'):
                    if not CAN_USE_EXTENDED_STARTUPINFO and command == 'use_cat':
                        self.CLOSE_FDS = False
                    self.override_command_line = [os.path.join(os.path.dirname(__file__), 'win32', 'cat.exe')]
                else:
                    self.override_command_line = ['cat']
            elif command == 'use_signal':
                self.CHILD_COMMS_STRATEGY = processfamily.CHILD_COMMS_STRATEGY_SIGNAL
        super(ProcessFamilyForTests, self).__init__(
            child_process_module_name='processfamily.test.ChildProcess',
            number_of_child_processes=number_of_child_processes,
            run_as_script=run_as_script)

    def handle_sys_err_line(self, child_index, line):
        logging.info("SYSERR: %d: %s", child_index+1, line.strip())

    def get_child_process_cmd(self, child_number):
        if self.override_command_line:
            return self.override_command_line
        return super(ProcessFamilyForTests, self).get_child_process_cmd(child_number) + [
            '--process_number', str(child_number+1)]

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    STARTUP_TIMEOUT = int(os.environ.get("STARTUP_TIMEOUT", "") or "10")
    logging.info("Starting")
    try:
        try:
            server = FunkyWebServer()
            server_thread = None
            family = ProcessFamilyForTests(number_of_child_processes=server.num_children)
            server.family = family
            try:
                try:
                    family.start(timeout=STARTUP_TIMEOUT)
                    server_thread = threading.Thread(target=server.run)
                    server_thread.start()
                    while server_thread.isAlive():
                        server_thread.join(1)
                except KeyboardInterrupt:
                    logging.info("Stopping...")
                    server.stop()
            finally:
                if server_thread and server_thread.isAlive():
                    server_thread.join(5)
        finally:
            stop_threads()
    except Exception as e:
        logging.error("Error in process family test parent process: %s\n%s", e, processfamily._traceback_str())
    logging.info("Done")