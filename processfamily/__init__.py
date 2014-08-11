# -*- coding: utf-8 -*-
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
import jsonrpc
import Queue
import pkgutil

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

class _ArgumentParser(argparse.ArgumentParser):

    def exit(self, status=0, message=None):
        pass

    def error(self, message):
        raise ValueError(message)

class _BaseChildProcessHost(object):
    def __init__(self, child_process):
        self.child_process = child_process
        self.command_arg_parser = _ArgumentParser(description='Execute an RPC method on the child')
        self.command_arg_parser.add_argument('method', choices=['stop'])
        self.command_arg_parser.add_argument('--id', '-i', dest='json_rpc_id')
        self.command_arg_parser.add_argument('--params', '-p', dest='params')
        self.dispatcher = jsonrpc.Dispatcher()
        self.dispatcher["stop"] = self._stop
        self.stdin = sys.stdin
        sys.stdin = open(os.devnull, 'r')
        self.stdout = sys.stdout
        sys.stdout = open(os.devnull, 'w')
        self._sys_in_thread = threading.Thread(target=self._sys_in_thread_target)
        self._sys_in_thread.start()
        self._should_stop = False

    def run(self):
        self.child_process.run()

    def _sys_in_thread_target(self):
        while True:
            try:
                line = self.stdin.readline()
                if not line:
                    break
                try:
                    rsp = self._handle_command_line(line)
                    if rsp:
                        assert not '\n' in rsp
                        self.stdout.write("%s\n"%rsp)
                except Exception as e:
                    logging.error("Error handling processfamily command on input: %s\n%s", e,  _traceback_str())
                if self._should_stop:
                    break
            except Exception as e:
                logging.error("Exception reading input for processfamily: %s\n%s", e,  _traceback_str())
                # This is a bit ugly, but I'm not sure what kind of error could cause this exception to occur,
                # so it might get in to a tight loop which I want to avoid
                time.sleep(1)

    def _stop(self):
        self._should_stop = True
        self.child_process.stop()
        return 0

    def _handle_command_line(self, line):
        try:
            line = line.strip()
            if not line.startswith('{'):
                args = self.command_arg_parser.parse_args(shlex.split(line))
                request = {
                    'jsonrpc': '2.0',
                    'method': args.method,
                }
                if args.json_rpc_id:
                    request['id'] = args.json_rpc_id
                if args.params:
                    request['params'] = args.params
                line = json.dumps(request)
        except Exception as e:
            logging.error("Error parsing command string: %s\n%s", e, _traceback_str())
            return '{"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": null}'

        try:
            rsp = jsonrpc.JSONRPCResponseManager.handle(line, self.dispatcher)
            if rsp:
                return rsp.json
            else:
                return None
        except Exception as e:
            logging.error("Error handling command string: %s\n%s", e, _traceback_str())
            return '{"jsonrpc": "2.0", "error": {"code": 32603, "message": "Error handling request"}, "id": null}'


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
        self._rsp_queues = {}
        self._stdin_lock = threading.RLock()

    def send_stop_command(self, timeout=None):
        self._send_command("stop", timeout=timeout, ignore_write_error=True)

    def _send_command(self, command, timeout=None, params=None, ignore_write_error=False):
        response_id = str(uuid.uuid4())
        cmd = {
            "method": command,
            "id": response_id,
            "jsonrpc": "2.0"
        }
        if params is not None:
            cmd["params"] = params

        req = json.dumps(cmd)
        assert not '\n' in req
        self._rsp_queues[response_id] = Queue.Queue()
        try:
            try:
                with self._stdin_lock:
                    self._process_instance.stdin.write("%s\n" % req)
            except Exception as e:
                if ignore_write_error:
                    return None
                raise
            return self._rsp_queues[response_id].get(True, timeout)
        finally:
            del self._rsp_queues[response_id]

    def handle_sys_err_line(self, line):
        sys.stderr.write(line)

    def _sys_err_thread_target(self):
        while True:
            try:
                line = self._process_instance.stderr.readline()
                if not line:
                    break
                try:
                    self.handle_sys_err_line(line)
                except Exception as e:
                    logging.error("Error handling child process stderr output: %s\n%s", e,  _traceback_str())
            except Exception as e:
                logging.error("Exception reading stderr output for processfamily: %s\n%s", e,  _traceback_str())
                # This is a bit ugly, but I'm not sure what kind of error could cause this exception to occur,
                # so it might get in to a tight loop which I want to avoid
                time.sleep(1)

    def _sys_out_thread_target(self):
        while True:
            try:
                line = self._process_instance.stdout.readline()
                if not line:
                    break
                try:
                    self._handle_response_line(line)
                except Exception as e:
                    logging.error("Error handling child process stdout output: %s\n%s", e,  _traceback_str())
            except Exception as e:
                logging.error("Exception reading stdout output for processfamily: %s\n%s", e,  _traceback_str())
                # This is a bit ugly, but I'm not sure what kind of error could cause this exception to occur,
                # so it might get in to a tight loop which I want to avoid
                time.sleep(1)

    def _handle_response_line(self, line):
        rsp = json.loads(line)
        if "id" in rsp:
            rsp_queue = self._rsp_queues.get(rsp["id"], None)
            if rsp_queue is not None:
                rsp_queue.put_nowait(rsp)


class ProcessFamily(object):
    """
    Manages the launching of a set of child processes
    """

    def __init__(self, child_process_module_name=None, number_of_child_processes=None, run_as_script=True):
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
