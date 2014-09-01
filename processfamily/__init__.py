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
from processfamily.threads import stop_threads
from processfamily.processes import kill_process, set_processor_affinity, cpu_count
import signal
import functools

if sys.platform.startswith('win'):
    import win32job
    import win32api
    import win32con
    import win32security
    import win32file
    import msvcrt

    from processfamily import win32Popen
    from processfamily import _winprocess_ctypes

    Popen = win32Popen.HandlesOverCommandLinePopen
    CAN_USE_EXTENDED_STARTUPINFO = _winprocess_ctypes.CAN_USE_EXTENDED_STARTUPINFO
else:
    import prctl
    Popen = subprocess.Popen

logger = logging.getLogger("processfamily")

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

    def init(self):
        """
        Do any initialisation. The parent will wait for this to be complete before considering the process to be
        running.
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

if sys.platform.startswith('win'):
    class _Win32File(object):

        def __init__(self, handle):
            self._handle = handle
            self._read_buffer = ""

        def write(self, s):
            (errCode, nBytesWritten) = win32file.WriteFile(self._handle, s)

        def flush(self):
            win32file.FlushFileBuffers(self._handle)

        def readline(self):
            while True:
                eol = self._read_buffer.find("\n")
                if eol >= 0:
                    l = self._read_buffer[:eol+1]
                    self._read_buffer = self._read_buffer[eol+1:]
                    return l
                (hr, data) = win32file.ReadFile(self._handle, 1024)
                if not data:
                    return ""
                self._read_buffer += data



class _BaseChildProcessHost(object):
    def __init__(self, child_process):
        self.child_process = child_process
        self.command_arg_parser = _ArgumentParser(description='Execute an RPC method on the child')
        self.command_arg_parser.add_argument('method')
        self.command_arg_parser.add_argument('--id', '-i', dest='json_rpc_id')
        self.command_arg_parser.add_argument('--params', '-p', dest='params')
        self._started_event = threading.Event()
        self._stopped_event = threading.Event()
        self.dispatcher = jsonrpc.Dispatcher()
        self.dispatcher["stop"] = self._respond_immediately_for_stop
        self.dispatcher["wait_for_start"] = self._wait_for_start

        self.stdin = sys.stdin
        sys.stdin = open(os.devnull, 'r')

        self.stdout = sys.stdout
        sys.stdout = open(os.devnull, 'w')

        self._stdout_lock = threading.RLock()
        self._sys_in_thread = threading.Thread(target=self._sys_in_thread_target)
        self._sys_in_thread.setDaemon(True)
        self._should_stop = False

    def run(self):
        #This is in the main thread
        try:
            self._sys_in_thread.start()
            try:
                if self._should_stop:
                    return
                self.child_process.init()
            finally:
                self._started_event.set()

            if self._should_stop:
                return
            self.child_process.run()
        except Exception as e:
            logger.error("Error: %s\n%s", e, _traceback_str())
            raise
        finally:
            self._stopped_event.set()

    def _wait_for_start(self):
        self._started_event.wait()
        return 0

    def _sys_in_thread_target(self):
        should_continue = True
        while should_continue:
            try:
                line = self.stdin.readline()
                if not line:
                    #TODO: in the code review - Please consider whether this is correct
                    #i.e. should we shut everything down when this happens?
                    should_continue = False
                else:
                    try:
                        should_continue = self._handle_command_line(line)
                    except Exception as e:
                        logger.error("Error handling processfamily command on input: %s\n%s", e,  _traceback_str())
            except Exception as e:
                logger.error("Exception reading input for processfamily: %s\n%s", e,  _traceback_str())
                # This is a bit ugly, but I'm not sure what kind of error could cause this exception to occur,
                # so it might get in to a tight loop which I want to avoid
                time.sleep(1)

        self._should_stop = True
        self._started_event.wait(1)
        threading.Thread(target=self._stop_thread_target).start()
        self._stopped_event.wait(3)
        #Give her ten seconds to stop
        #This will not actually stop the process from terminating as this is a daemon thread
        time.sleep(10)
        #Now try and force things
        stop_threads()

    def _stop_thread_target(self):
        try:
            self.child_process.stop()
        except Exception as e:
            logger.error("Error handling processfamily stop command: %s\n%s", e,  _traceback_str())

    def _respond_immediately_for_stop(self):
        logger.info("Received stop instruction from parent process")
        self._should_stop = True
        return 0

    def _send_response(self, rsp):
        if rsp:
            assert not '\n' in rsp
            with self._stdout_lock:
                logger.debug("Sending response: %s", rsp)
                self.stdout.write("%s\n"%rsp)
                self.stdout.flush()

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
            else:
                request = json.loads(line)
            request_id = json.dumps(request.get("id"))
        except Exception as e:
            logger.error("Error parsing command string: %s\n%s", e, _traceback_str())
            self._send_response('{"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": null}')
            return True

        if request.get('method') == 'stop':
            #I have to process the stop method in this thread!

            #This is a bit lame - but I'm just using this to form a valid response and send it immediately
            #
            self._dispatch_rpc_call(line, request_id)
            return False
        else:
            #Others should be processed from a new thread:
            threading.Thread(target=self._dispatch_rpc_call, args=(line, request_id)).start()
            return True

    def _dispatch_rpc_call(self, line, request_id):
        try:
            rsp = jsonrpc.JSONRPCResponseManager.handle(line, self.dispatcher)
            if rsp is not None:
                self._send_response(rsp.json)
        except Exception as e:
            logger.error("Error handling command string: %s\n%s", e, _traceback_str())
            self._send_response('{"jsonrpc": "2.0", "error": {"code": 32603, "message": "Error handling request"}, "id": %s}'%request_id)


class ChildProcessProxy(object):
    """
    A proxy to the child process that can be used from the parent process
    """

    def __init__(self, process_instance, echo_std_err, child_index, process_family):
        self.process_family = process_family
        self.child_index = child_index
        self.name = self.process_family.get_child_name(child_index)
        self._process_instance = process_instance
        self.echo_std_err = echo_std_err
        if self.echo_std_err:
            self._sys_err_thread = threading.Thread(target=self._sys_err_thread_target)
            self._sys_err_thread.start()
        self._sys_out_thread = threading.Thread(target=self._sys_out_thread_target)
        self._sys_out_thread.start()
        self._rsp_queues_lock = threading.RLock()
        self._rsp_queues = {}
        self._stdin_lock = threading.RLock()

    def send_command(self, command, timeout, params=None):
        response_id = str(uuid.uuid4())
        try:
            self._send_command_req(response_id, command, params=params)
            return self._wait_for_response(response_id, timeout)
        finally:
            self._cleanup_queue(response_id)

    def _send_command_req(self, response_id, command, params=None):
        with self._rsp_queues_lock:
            if self._rsp_queues is None:
                return
            self._rsp_queues[response_id] = Queue.Queue()
        cmd = {
            "method": command,
            "id": response_id,
            "jsonrpc": "2.0"
        }
        if params is not None:
            cmd["params"] = params

        req = json.dumps(cmd)
        assert not '\n' in req
        try:
            with self._stdin_lock:
                self._process_instance.stdin.write("%s\n" % req)
                self._process_instance.stdin.flush()
                if command == 'stop':
                    #Now close the stream - we are done
                    self._process_instance.stdin.close()
        except Exception as e:
            if self._process_instance.poll() is None:
                #The process is running, so something is wrong:
                raise

    def _wait_for_response(self, response_id, timeout):
        with self._rsp_queues_lock:
            if self._rsp_queues is None:
                return None
            q = self._rsp_queues.get(response_id, None)
        if q is None:
            return None
        try:
            if timeout <= 0:
                return q.get_nowait()
            else:
                return q.get(True, timeout)
        except Queue.Empty as e:
            return None

    def _cleanup_queue(self, response_id):
        with self._rsp_queues_lock:
            if self._rsp_queues is not None:
                self._rsp_queues.pop(response_id, None)

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
                    logger.error("Error handling %s stderr output: %s\n%s", self.name, e,  _traceback_str())
            except Exception as e:
                logger.error("Exception reading stderr output for %s: %s\n%s", self.name, e,  _traceback_str())
                # This is a bit ugly, but I'm not sure what kind of error could cause this exception to occur,
                # so it might get in to a tight loop which I want to avoid
                time.sleep(5)
        logger.debug("Subprocess stderr closed")

    def _sys_out_thread_target(self):
        try:
            while True:
                try:
                    line = self._process_instance.stdout.readline()
                    if not line:
                        break
                    try:
                        self._handle_response_line(line)
                    except Exception as e:
                        logger.error("Error handling %s stdout output: %s\n%s", self.name, e,  _traceback_str())
                except Exception as e:
                    logger.error("Exception reading stdout output for %s: %s\n%s", self.name, e,  _traceback_str())
                    # This is a bit ugly, but I'm not sure what kind of error could cause this exception to occur,
                    # so it might get in to a tight loop which I want to avoid
                    time.sleep(1)
            logger.debug("Subprocess stdout closed - expecting termination")
            start_time = time.time()
            while self._process_instance.poll() is None and time.time() - start_time < 5:
                time.sleep(0.1)
            if self.echo_std_err:
                self._sys_err_thread.join(5)
            if self._process_instance.poll() is None:
                logger.error("Stdout stream closed for %s, but process is not terminated (PID:%s)", self.name, self._process_instance.pid)
            else:
                logger.info("%s terminated (return code: %d)", self.name, self._process_instance.returncode)
        finally:
            #Unstick any waiting command threads:
            with self._rsp_queues_lock:
                for q in self._rsp_queues.values():
                    if q.empty():
                        q.put_nowait(None)
                self._rsp_queues = None

    def _handle_response_line(self, line):
        rsp = json.loads(line)
        if "id" in rsp:
            with self._rsp_queues_lock:
                if self._rsp_queues is None:
                    return
                rsp_queue = self._rsp_queues.get(rsp["id"], None)
            if rsp_queue is not None:
                rsp_queue.put_nowait(rsp)

#We need to keep the job handle in a global variable so that can't go out of scope and result in our process
#being killed
_global_process_job_handle = None

CPU_AFFINITY_STRATEGY_NONE = 0
CPU_AFFINITY_STRATEGY_CHILDREN_ONLY = 1
CPU_AFFINITY_STRATEGY_PARENT_INCLUDED = 2

class ProcessFamily(object):
    """
    Manages the launching of a set of child processes
    """

    ECHO_STD_ERR = True
    CPU_AFFINITY_STRATEGY = CPU_AFFINITY_STRATEGY_PARENT_INCLUDED

    def __init__(self, child_process_module_name=None, number_of_child_processes=None, run_as_script=True):
        self.child_process_module_name = child_process_module_name
        self.run_as_script = run_as_script

        if self.CPU_AFFINITY_STRATEGY:
            self.cpu_count = cpu_count()
            if number_of_child_processes:
                self.number_of_child_processes = number_of_child_processes
            elif self.CPU_AFFINITY_STRATEGY == CPU_AFFINITY_STRATEGY_PARENT_INCLUDED:
                self.number_of_child_processes = self.cpu_count-1
            else:
                self.number_of_child_processes = self.cpu_count

        self.child_processes = []
        self._child_process_group_id = None

    def get_child_process_cmd(self, child_number):
        if self.run_as_script:
            return [self.get_sys_executable(), self._find_module_filename(self.child_process_module_name)]
        else:
            return [self.get_sys_executable(), '-m', self.child_process_module_name]

    def get_sys_executable(self):
        return sys.executable

    def get_job_object_name(self):
        return "py_processfamily_%s" % (str(uuid.uuid4()))

    def get_child_name(self, i):
        return 'Child Process %d' % (i+1)

    def _add_to_job_object(self):
        global _global_process_job_handle
        if _global_process_job_handle is not None:
            #This means that we are creating another process family - we'll all be in the same job
            return

        if win32job.IsProcessInJob(win32api.GetCurrentProcess(), None):
            raise ValueError("ProcessFamily relies on the parent process NOT being in a job already")

        #Create a new job and put us in it before we create any children
        logger.debug("Creating job object and adding parent process to it")
        security_attrs = win32security.SECURITY_ATTRIBUTES()
        security_attrs.bInheritHandle = 0
        _global_process_job_handle = win32job.CreateJobObject(security_attrs, self.get_job_object_name())
        extended_info = win32job.QueryInformationJobObject(_global_process_job_handle, win32job.JobObjectExtendedLimitInformation)
        extended_info['BasicLimitInformation']['LimitFlags'] = win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        win32job.SetInformationJobObject(_global_process_job_handle, win32job.JobObjectExtendedLimitInformation, extended_info)
        win32job.AssignProcessToJobObject(_global_process_job_handle, win32api.GetCurrentProcess())
        logger.debug("Added to job object")

    def get_Popen_kwargs(self, i, **kwargs):
        if sys.platform.startswith('win'):
            kwargs['close_fds'] = True
            return kwargs
        else:

            kwargs['close_fds'] = True
            kwargs['preexec_fn'] = functools.partial(self.pre_exec_fn, i)
            return kwargs


    def pre_exec_fn(self, i):
        #This is called after fork(), but before exec()
        #Assign this new process to a new group
        os.setpgrp()
        prctl.set_pdeathsig(signal.SIGKILL)


    def set_parent_affinity_mask(self):
        if self.CPU_AFFINITY_STRATEGY == CPU_AFFINITY_STRATEGY_PARENT_INCLUDED:
            set_processor_affinity([0])

    def set_child_affinity_mask(self, pid, child_index):
        i = child_index+1 if self.CPU_AFFINITY_STRATEGY == CPU_AFFINITY_STRATEGY_PARENT_INCLUDED else child_index
        set_processor_affinity([i%self.cpu_count], pid=pid)

    def start(self, timeout=30):
        assert not self.child_processes

        if self.CPU_AFFINITY_STRATEGY:
            self.set_parent_affinity_mask()

        if sys.platform.startswith('win'):
            self._add_to_job_object()

        self.child_processes = []
        for i in range(self.number_of_child_processes):
            logger.info("Starting %s", self.get_child_name(i))
            cmd = self.get_child_process_cmd(i)
            logger.debug("Commandline for %s: %s", self.get_child_name(i), json.dumps(cmd))
            FNULL = open(os.devnull, 'w')
            p = Popen(
                    cmd,
                    **self.get_Popen_kwargs(i,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE if self.ECHO_STD_ERR else FNULL))

            if self.CPU_AFFINITY_STRATEGY:
                self.set_child_affinity_mask(p.pid, i)
            self.child_processes.append(ChildProcessProxy(p, self.ECHO_STD_ERR, i, self))

        logger.debug("Waiting for child start events")
        responses = self.send_command_to_all("wait_for_start", timeout=timeout)
        for i, r in enumerate(responses):
            if r is None:
                if self.child_processes[i]._process_instance.poll() is None:
                    logger.error(
                        "Timed out waiting for %s (PID %d) to complete initialisation",
                        self.get_child_name(i),
                        self.child_processes[i]._process_instance.pid)
                else:
                    logger.error(
                        "%s terminated with response code %d before completing initialisation",
                        self.get_child_name(i),
                        self.child_processes[i]._process_instance.poll())
        logger.info("All child processes initialised")

    def stop(self, timeout=30):
        clean_timeout = timeout - 1
        start_time = time.time()
        logger.info("Sending stop commands to child processes")
        self.send_command_to_all("stop", timeout=clean_timeout)

        logger.debug("Waiting for child processes to terminate")
        self._wait_for_children_to_terminate(start_time, clean_timeout)

        if self.child_processes:
            #We've nearly run out of time - let's try and kill them:
            logger.debug("Attempting to kill stubborn child processes")
            for p in list(self.child_processes):
                try:
                    kill_process(p._process_instance.pid)
                except Exception as e:
                    logger.warning("Failed to kill child process with PID %s: %s\n%s", p._process_instance.pid, e, _traceback_str())
            self._wait_for_children_to_terminate(start_time, timeout)

    def _wait_for_children_to_terminate(self, start_time, timeout):
        first_run = True
        while self.child_processes and (first_run or time.time() - start_time < timeout):
            for p in list(self.child_processes):
                if p._process_instance.poll() is not None:
                    self.child_processes.remove(p)
            if first_run:
                first_run = False
            else:
                time.sleep(0.1)


    def send_command_to_all(self, command, timeout=30, params=None):
        start_time = time.time()
        response_id = str(uuid.uuid4())
        responses = [None]*len(self.child_processes)
        try:
            for p in self.child_processes:
                p._send_command_req(response_id, command, params=params)

            for i, p in enumerate(self.child_processes):
                time_left = timeout - (time.time() - start_time)
                responses[i] = p._wait_for_response(response_id, time_left)
            return responses
        finally:
            for p in self.child_processes:
                p._cleanup_queue(response_id)

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
