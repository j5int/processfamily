__author__ = 'matth'

import sys
import subprocess
import time
import uuid
import logging
import json

def start_child_process(child_process_instance):
    pass

class ChildProcess(object):
    """
    Subclass this for the implementation of the child process. You must also include an appropriate main entry point.

    You should do something like this in your implementation:

        if __name__ == '__main__':
            start_child_process(MyChildProcess())

    """

    def run(self):
        """
        Method representing the thread's activity. You may override this method in a subclass.

        This will be called from the processes main method, after initialising some other stuff.
        """

    def stop_command(self, timeout):
        """
        Will be called from a new thread. The process should do its best to shutdown cleanly if this is called.

        :param timeout The number of milliseconds that the parent process will wait before killing this process.
        """

    def custom_command(self, command, timeout, **kwargs):
        """
        Will be called in a new thread when a custom command is sent from the parent process

        :param command: a string
        :param timeout: The number of milliseconds that the parent process expects the child to take
        :param kwargs: custom keyword arguments (parsed from a json string)
        :return: a json friendly object to return to the parent
        """

    def request_more_time(self, millis):
        """
        During the processing of a command (including the stop command), call this method to request more time.

        :param millis
        """


class ChildProcessProxy(object):
    """
    A proxy to the child process that can be used from the parent process
    """

    def __init__(self, process_instance):
        self._process_instance = process_instance

    def send_custom_command(self, command, initial_timeout, **kwargs):
        """
        send a custom command to the child, and wait for a response (blocking)
        :param command: a string - the name of the command
        :param initial_timeout: the initial timeout period (this may be extended by the child process calling request_more_time)
        :param kwargs: a set of keyword arguments - they should all be json friendly

        :raises This will raise a timeout exception the timeout period is exceeded.
        :returns an object restored from a json string
        """

    def send_stop_command(self):
        self._send_command("stop")

    def _send_command(self, command, initial_timeout, *args, **kwargs):
        response_id = str(uuid.uuid4())
        cmd = [command, response_id, initial_timeout] + list(args)
        if kwargs:
            cmd.append(json.dumps(kwargs))
        self._process_instance.stdin.write("%s\n" % " ".join(cmd))

    def handle_sys_err_line(self, line):
        sys.stderr.writelines([line])

    def _sys_err_thread(self):
        line = self._process_instance.stderr.readline()
        while line is not None:
            self.handle_sys_err_line(line)
            line = self._process_instance.stderr.readline()

    def _sys_out_thread(self):
        line = self._process_instance.stdout.readline()
        while line is not None:
            self._handle_response_line(line)
            line = self._process_instance.stdout.readline()

    def _handle_response_line(self, line):
        pass


class ProcessFamily(object):
    """
    Manages the launching of a set of child processes
    """

    def __init__(self, child_process_module_name=None, number_of_child_processes=None):
        self.child_process_module_name = child_process_module_name
        self.number_of_child_processes = number_of_child_processes
        self.child_processes = []

    def get_child_process_cmd(self):
        return [sys.executable, '-m', self.child_process_module_name]

    def start(self):
        assert not self.child_processes
        self.child_processes = []
        for i in range(self.number_of_child_processes):
            p = subprocess.Popen(
                    self.get_child_process_cmd(),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    close_fds=True)
            self.child_processes.append(ChildProcessProxy(p))

    def stop(self):
        for p in self.child_processes:
            p.send_stop_command()

        while self.child_processes:
            for p in list(self.child_processes):
                if p.poll() is not None:
                    self.child_processes.remove(p)
            time.sleep(0.1)

