import pkgutil

__author__ = 'matth'

import threading
import traceback
import sys
import subprocess
import time
import uuid
import logging
import json
import argparse
import shlex
import os

def start_child_process(child_process_instance):
    host = _BaseChildProcessHost(child_process_instance)
    host.run()

def _traceback_str():
    exc_info = sys.exc_info()
    return "".join(traceback.format_exception(exc_info[0], exc_info[1], exc_info[2]))

def _exception_str():
    exc_info = sys.exc_info()
    return "".join(traceback.format_exception_only(exc_info[0], exc_info[1]))

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

    def stop(self, timeout=None):
        """
        Will be called from a new thread. The process should do its best to shutdown cleanly if this is called.

        :param timeout The number of milliseconds that the parent process will wait before killing this process.
        """

    def request_more_time(self, millis):
        """
        During the processing of a command (including the stop command), call this method to request more time.

        :param millis
        """

class _BaseChildProcessHost(object):
    def __init__(self, child_process):
        self.child_process = child_process
        self.command_arg_parser = argparse.ArgumentParser(description='Processes a command')
        self.command_arg_parser.add_argument('command', choices=['stop'])
        self.command_arg_parser.add_argument('--responseid', '-r', dest='response_id')
        self.command_arg_parser.add_argument('--timeout', '-t', dest='timeout')
        self.stdin = sys.stdin
        sys.stdin = open(os.devnull, 'r')
        self.stdout = sys.stdout
        sys.stdout = open(os.devnull, 'w')
        self._sys_in_thread = threading.Thread(target=self._sys_in_thread_target)
        self._sys_in_thread.start()

    def run(self):
        self.child_process.run()

    def _sys_in_thread_target(self):
        try:
            line = self.stdin.readline()
            while line is not None:
                if not self._handle_command_line(line):
                    break
                line = self.stdin.readline()
        except Exception as e:
            sys.stderr.write("%s\n" % e)

    def _handle_command_line(self, line):
        args = self.command_arg_parser.parse_args(shlex.split(line))
        if args.command == 'stop':
            self.child_process.stop()
            return False
        return True


class ChildProcessProxy(object):
    """
    A proxy to the child process that can be used from the parent process
    """

    def __init__(self, process_instance):
        self._process_instance = process_instance
        self._sys_err_thread = threading.Thread(target=self._sys_err_thread_target)
        self._sys_out_thread = threading.Thread(target=self._sys_out_thread_target)
        self._sys_err_thread.start()
        self._sys_out_thread.start()

    def send_stop_command(self, timeout=None):
        if self._process_instance.poll() is None:
            self._send_command("stop", timeout=timeout)

    def _send_command(self, command, timeout=None):
        response_id = str(uuid.uuid4())
        cmd = [command, '-r', response_id]
        if timeout is not None:
            cmd += ['-t', timeout]
        self._process_instance.stdin.write("%s\n" % " ".join(cmd))
        return response_id

    def handle_sys_err_line(self, line):
        sys.stderr.write(line)

    def _sys_err_thread_target(self):
        try:
            while self._process_instance.poll() is None:
                line = self._process_instance.stderr.readline()
                if line:
                    self.handle_sys_err_line(line)
        except Exception as e:
            print e

    def _sys_out_thread_target(self):
        try:
            while self._process_instance.poll() is None:
                line = self._process_instance.stdout.readline()
                if line:
                    self._handle_response_line(line)
        except Exception as e:
            print e


    def _handle_response_line(self, line):
        pass


class ProcessFamily(object):
    """
    Manages the launching of a set of child processes
    """

    def __init__(self, child_process_module_name=None, number_of_child_processes=None, run_as_script=False):
        self.child_process_module_name = child_process_module_name
        self.run_as_script = run_as_script
        self.number_of_child_processes = number_of_child_processes
        self.child_processes = []

    def get_child_process_cmd(self):
        if self.run_as_script:
            return [sys.executable, self._find_module_filename(self.child_process_module_name)]
        else:
            return [sys.executable, '-m', self.child_process_module_name]

    def start(self):
        assert not self.child_processes
        self.child_processes = []
        for i in range(self.number_of_child_processes):
            p = subprocess.Popen(
                    self.get_child_process_cmd(),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE)
            self.child_processes.append(ChildProcessProxy(p))

    def stop(self):
        for p in self.child_processes:
            p.send_stop_command()

        while self.child_processes:
            for p in list(self.child_processes):
                if p._process_instance.poll() is not None:
                    self.child_processes.remove(p)
            time.sleep(0.1)

    def _find_module_filename(self, modulename):
        """finds the filename of the module with the given name (supports submodules)"""
        module_parts = modulename.split(".")
        search_path = None
        for i, part in enumerate(module_parts):
            search_module = ".".join(module_parts[:i+1])
            try:
                loader = pkgutil.find_loader(search_module)
                if loader is None:
                    raise ImportError(search_module)
                search_path = loader.get_filename(search_module)
            except ImportError:
                raise ValueError("Could not find %s (reached %s at %s)" % (modulename, part, search_path))
        return search_path
