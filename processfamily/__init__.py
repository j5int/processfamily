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
try:
    import queue
except ImportError:
    import Queue as queue
import pkgutil
from processfamily.threads import stop_threads
from processfamily.processes import kill_process, process_exists, set_processor_affinity, cpu_count
import signal
import functools

if sys.platform.startswith('win'):
    import win32job
    import win32api
    import win32security
    import pywintypes
    import winerror

    from processfamily import win32Popen
else:
    from . import ctypes_prctl as prctl

SIGNAL_NAMES = {getattr(signal, k): k for k in dir(signal) if k.startswith("SIG")}

logger = logging.getLogger("processfamily")

class JobObjectAssignError(Exception):
    def __init__(self, message, cause, already_in_job):
        super(JobObjectAssignError, self).__init__(message)
        self.cause = cause
        self.already_in_job = already_in_job

def start_child_process(child_process_instance):
    host = _ChildProcessHost(child_process_instance)
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

class _ChildProcessHost(object):
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
        self._sys_in_thread = threading.Thread(target=self._sys_in_thread_target, name="pf_%s_stdin" % repr(child_process))
        self._sys_in_thread.daemon = True
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
                time.sleep(5)

        self._should_stop = True
        self._started_event.wait(1)
        stop_thread = threading.Thread(target=self._stop_thread_target, name="pf_%s_stop" % repr(self.child_process))
        stop_thread.daemon = True
        stop_thread.start()
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
            if '\n' in rsp:
                raise ValueError('Invalid response string (new lines are not allowed): "%r"' % rsp)
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
            threading.Thread(target=self._dispatch_rpc_call_thread_target, args=(line, request_id)).start()
            return True

    def _dispatch_rpc_call(self, line, request_id):
        try:
            rsp = jsonrpc.JSONRPCResponseManager.handle(line, self.dispatcher)
            if rsp is not None:
                self._send_response(rsp.json)
        except Exception as e:
            logger.error("Error handling command string: %s\n%s", e, _traceback_str())
            self._send_response('{"jsonrpc": "2.0", "error": {"code": 32603, "message": "Error handling request"}, "id": %s}'%request_id)

    def _dispatch_rpc_call_thread_target(self, line, request_id):
        try:
            self._dispatch_rpc_call(line, request_id)
        except Exception as e:
            logger.error("Error handling command string: %s\n%s", e, _traceback_str())


class ChildCommsStrategy(object):
    """
    A proxy to the child process that can be used from the parent process
    """
    MONITOR_STDOUT = True
    SENDS_STDOUT_RESPONSES = False
    CAN_WAIT_FOR_TERMINATE = True

    def __init__(self, process_instance, echo_std_err, child_index, process_family):
        if type(self) == ChildCommsStrategy:
            raise NotImplementedError("A concrete strategy needs to be chosen")
        self.process_family = process_family
        self.child_index = child_index
        self.name = self.process_family.get_child_name(child_index)
        self._process_instance = process_instance

        self._rsp_queues_lock = threading.RLock()
        self._rsp_queues = {}
        self._stdin_lock = threading.RLock()

        self.echo_std_err = echo_std_err
        if self.echo_std_err:
            self._sys_err_thread = threading.Thread(target=self._sys_err_thread_target, name="pf_%s_stderr" % self.name)
            self._sys_err_thread.daemon = True
            self._sys_err_thread.start()
        if self.MONITOR_STDOUT:
            self._sys_out_thread = threading.Thread(target=self._sys_out_thread_target, name="pf_%s_stdout" % self.name)
            self._sys_out_thread.daemon = True
            self._sys_out_thread.start()

    def __repr__(self):
        return "%s (%s: %r)" % (self.name, type(self).__name__, self._process_instance)

    @property
    def pid(self):
        return self._process_instance.pid

    def is_stopped(self):
        """return whether the governed process has stopped"""
        return self._process_instance.poll() is not None

    @staticmethod
    def get_popen_streams(echo_std_err):
        """Returns kwargs for stdin, stdout and stderr to pass to subprocess.Popen"""
        PIPE = subprocess.PIPE
        streams = {"stdin": PIPE, "stdout": PIPE, "stderr": PIPE}
        if not echo_std_err:
            streams["stderr"] = open(os.devnull, 'w')
        return streams

    def monitor_child_startup(self, end_time):
        """generator method to monitor process startup, with the first yield after sending a ping,
        the next after receiving a response, and stopping after cleanup"""
        yield
        yield

    def stop_child(self, end_time):
        """generator method to send stop to child, with the first yield after sending the shutdown command,
        the next after receiving a response, and stopping after cleanup"""
        yield
        yield

    def _sys_err_thread_target(self):
        while True:
            try:
                line = self._process_instance.stderr.readline()
                if not line:
                    break
                try:
                    self.process_family.handle_sys_err_line(self.child_index, line)
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
                        if self.SENDS_STDOUT_RESPONSES:
                            self._handle_response_line(line)
                        else:
                            self.process_family.handle_sys_out_line(self.child_index, line)
                    except Exception as e:
                        logger.error("Error handling %s stdout output: %s\n%s", self.name, e,  _traceback_str())
                except Exception as e:
                    logger.error("Exception reading stdout output for %s: %s\n%s", self.name, e,  _traceback_str())
                    # This is a bit ugly, but I'm not sure what kind of error could cause this exception to occur,
                    # so it might get in to a tight loop which I want to avoid
                    time.sleep(5)
            logger.debug("Subprocess stdout closed - expecting termination")
            start_time = time.time()
            while self._process_instance.poll() is None and time.time() - start_time < 5:
                time.sleep(0.1)
            if self.echo_std_err:
                self._sys_err_thread.join(5)
            if self._process_instance.poll() is None:
                logger.error("Stdout stream closed for %s, but process is not terminated (PID:%s)", self.name, self.pid)
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


class NoCommsStrategy(ChildCommsStrategy):
    MONITOR_STDOUT = False
    CAN_WAIT_FOR_TERMINATE = False

    @staticmethod
    def get_popen_streams(echo_std_err):
        """Returns kwargs for stdin, stdout and stderr to pass to subprocess.Popen"""
        return {"stdin": None, "stdout": None, "stderr": None}

class ClosePipesCommsStrategy(ChildCommsStrategy):
    def stop_child(self, end_time):
        p = self._process_instance
        logger.info("Closing stdin for process %r", self)
        try:
            p.stdin.close()
        except Exception as e:
            logger.warning("Failed to close child process input stream with PID %s: %s\n%s", self.pid, e, _traceback_str())
        yield
        yield


class ProcessFamilyRPCProtocolStrategy(ChildCommsStrategy):
    SENDS_STDOUT_RESPONSES = True

    def monitor_child_startup(self, end_time):
        """generator method to monitor process startup, with the first yield after sending a ping,
        the next after receiving a response, and stopping after cleanup"""
        response_id = str(uuid.uuid4())
        try:
            yield self._send_command_req(response_id, "wait_for_start")
            response = self._wait_for_response(response_id, end_time - time.time())
            yield response
        finally:
            self._cleanup_queue(response_id)
        if response is None:
            poll_result = self._process_instance.poll()
            if poll_result is None:
                logger.error("Timed out waiting for %s (PID %d) to complete initialisation",
                             self.name, self.pid)
            else:
                logger.error("%s terminated with response code %d before completing initialisation",
                             self.name, poll_result)

    def stop_child(self, end_time):
        """generator method to send stop to child, with the first yield after sending the shutdown command,
        the next after receiving a response, and stopping after cleanup"""
        response_id = str(uuid.uuid4())
        try:
            yield self._send_command_req(response_id, "stop")
            yield self._wait_for_response(response_id, end_time - time.time())
        finally:
            self._cleanup_queue(response_id)

    def _send_command_req(self, response_id, command, params=None):
        with self._rsp_queues_lock:
            if self._rsp_queues is None:
                return
            self._rsp_queues[response_id] = queue.Queue()
        cmd = {
            "method": command,
            "id": response_id,
            "jsonrpc": "2.0"
        }
        if params is not None:
            cmd["params"] = params

        req = json.dumps(cmd)
        if '\n' in req:
            raise ValueError('Invalid request string (new lines are not allowed): "%r"' % req)

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
        except queue.Empty as e:
            return None

    def _cleanup_queue(self, response_id):
        with self._rsp_queues_lock:
            if self._rsp_queues is not None:
                self._rsp_queues.pop(response_id, None)


class SignalStrategy(ChildCommsStrategy):
    def stop_child(self, end_time):
        """generator method to send stop to child, with the first yield after sending the shutdown command,
        the next after receiving a response, and stopping after cleanup"""
        signum = self.process_family.CHILD_STOP_SIGNAL
        signal_name = SIGNAL_NAMES.get(signum, str(signum))
        logger.info("Sending signal %s to process %r", signal_name, self)
        os.kill(self.pid, signum)
        yield
        yield

class ForkingChildSignalStrategy(SignalStrategy):
    # requires the process_family instance to have a pid_file attribute added...
    MONITOR_STDOUT = False

    @property
    def pid(self):
        return getattr(self, "forked_pid", None) or self._process_instance.pid

    def is_stopped(self):
        return not process_exists(self.pid)

    def monitor_child_startup(self, end_time):
        """generator method to monitor process startup, with the first yield after sending a ping,
        the next after receiving a response, and stopping after cleanup"""
        while (self._process_instance.poll() is None) and time.time() < end_time:
            # Python 2.7 has the timeout parameter for wait, but it is not documented
            # try:
            #     subprocess.Popen().wait(end_time - time.time())
            # except Exception, e:
            #     pass
            time.sleep(0.05)
        yield
        if os.path.exists(self.process_family.pid_file):
            with open(self.process_family.pid_file, 'rb') as f:
                pid_str = f.read().strip()
                self.forked_pid = int(pid_str) if pid_str and pid_str.isdigit() else None
                if not self.forked_pid:
                    logger.error("Unexpected pid found in file %s for %r: %r", self.process_family.pid_file, self, pid_str)
                yield
        else:
            self.forked_pid = None
            logger.error("PID file %s was not created: Child for %r probably failed to start", self.process_family.pid_file, self)
            raise ValueError("Could not find child process for %s (probably failed to start)" % self.name)


CHILD_COMMS_STRATEGY_NONE = NoCommsStrategy
CHILD_COMMS_STRATEGY_PIPES_CLOSE = ClosePipesCommsStrategy
CHILD_COMMS_STRATEGY_PROCESSFAMILY_RPC_PROTOCOL = ProcessFamilyRPCProtocolStrategy
CHILD_COMMS_STRATEGY_SIGNAL = SignalStrategy

class ProcessFamily(object):
    """
    Manages the launching of a set of child processes
    """

    ECHO_STD_ERR = False
    CPU_AFFINITY_STRATEGY = CPU_AFFINITY_STRATEGY_PARENT_INCLUDED
    CLOSE_FDS = True
    CHILD_STOP_SIGNAL = signal.SIGINT
    WIN_PASS_HANDLES_OVER_COMMANDLINE = False
    WIN_USE_JOB_OBJECT = True
    LINUX_USE_PDEATHSIG = True
    NEW_PROCESS_GROUP = True
    CHILD_COMMS_STRATEGY = CHILD_COMMS_STRATEGY_PROCESSFAMILY_RPC_PROTOCOL

    def __init__(self, child_process_module_name=None, number_of_child_processes=None, run_as_script=True):
        self.child_process_module_name = child_process_module_name
        self.run_as_script = run_as_script

        self.cpu_count = cpu_count()
        if number_of_child_processes:
            self.number_of_child_processes = number_of_child_processes
        else:
            if self.CPU_AFFINITY_STRATEGY == CPU_AFFINITY_STRATEGY_PARENT_INCLUDED:
                self.number_of_child_processes = self.cpu_count-1
            elif self.CPU_AFFINITY_STRATEGY == CPU_AFFINITY_STRATEGY_CHILDREN_ONLY:
                self.number_of_child_processes = self.cpu_count
            else:
                self.number_of_child_processes = self.cpu_count

        self.child_processes = []
        self._child_process_group_id = None

    def get_child_process_cmd(self, child_number):
        """
        :param child_number zero-indexed
        """
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

    def handle_sys_err_line(self, child_index, line):
        sys.stderr.write(line)

    def handle_sys_out_line(self, child_index, line):
        """
        This is only relevant if CHILD_COMMS_STRATEGY_PIPES_CLOSE is used
        """
        pass

    def _add_to_job_object(self):
        global _global_process_job_handle
        if _global_process_job_handle is not None:
            #This means that we are creating another process family - we'll all be in the same job
            return

        already_in_job = win32job.IsProcessInJob(win32api.GetCurrentProcess(), None)

        #Create a new job and put us in it before we create any children
        logger.debug("Creating job object and adding parent process to it")
        security_attrs = win32security.SECURITY_ATTRIBUTES()
        security_attrs.bInheritHandle = 0
        _global_process_job_handle = win32job.CreateJobObject(security_attrs, self.get_job_object_name())
        extended_info = win32job.QueryInformationJobObject(_global_process_job_handle, win32job.JobObjectExtendedLimitInformation)
        extended_info['BasicLimitInformation']['LimitFlags'] = win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        win32job.SetInformationJobObject(_global_process_job_handle, win32job.JobObjectExtendedLimitInformation, extended_info)
        try:
            win32job.AssignProcessToJobObject(_global_process_job_handle, win32api.GetCurrentProcess())
        except Exception as e:
            winv = sys.getwindowsversion()
            logger.error("Error raised during assignment of the current process to a new job object. " +\
                         "The process %s already in a job. " +\
                         "The windows version is %d.%d.\nError: %s",
                            "is" if already_in_job else "is not",
                            winv.major,
                            winv.minor,
                            _exception_str())

            if already_in_job and not (winv.major >= 6 and winv.minor >= 2):
                raise JobObjectAssignError("On Windows versions older than Windows 8 / Windows Server 2012, ProcessFamily relies on the parent process NOT being in a job already", e, already_in_job)

            raise JobObjectAssignError("Error raised during assignment of the current process to a new job object.", e, already_in_job)


        logger.debug("Added to job object")

    def get_Popen_kwargs(self, i, **kwargs):
        popen_streams = self.CHILD_COMMS_STRATEGY.get_popen_streams(self.ECHO_STD_ERR)
        kwargs.update(popen_streams)
        if sys.platform.startswith('win'):
            if self.WIN_PASS_HANDLES_OVER_COMMANDLINE:
                kwargs['timeout_for_child_stream_duplication_event'] = None
                if self.NEW_PROCESS_GROUP:
                    kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
            return kwargs
        else:
            kwargs['preexec_fn'] = functools.partial(self.pre_exec_fn, i)
            return kwargs

    def get_Popen_class(self):
        if sys.platform.startswith('win'):
            if self.WIN_PASS_HANDLES_OVER_COMMANDLINE:
                logger.debug("Using HandlesOverCommandLinePopen")
                return win32Popen.HandlesOverCommandLinePopen
            else:
                logger.debug("Using ProcThreadAttributeHandleListPopen")
                return win32Popen.ProcThreadAttributeHandleListPopen
        else:
            return subprocess.Popen

    def pre_exec_fn(self, i):
        #This is called after fork(), but before exec()
        #Assign this new process to a new group
        if self.NEW_PROCESS_GROUP:
            os.setpgrp()
        if self.LINUX_USE_PDEATHSIG:
            prctl.set_pdeathsig(self.get_pdeath_sig())

    def get_pdeath_sig(self):
        return signal.SIGKILL

    def set_parent_affinity_mask(self):
        if self.CPU_AFFINITY_STRATEGY == CPU_AFFINITY_STRATEGY_PARENT_INCLUDED:
            set_processor_affinity([0])

    def set_child_affinity_mask(self, pid, child_index):
        i = child_index+1 if self.CPU_AFFINITY_STRATEGY == CPU_AFFINITY_STRATEGY_PARENT_INCLUDED else child_index
        set_processor_affinity([i%self.cpu_count], pid=pid)

    def start(self, timeout=30):
        if self.child_processes:
            raise Exception("Invalid state: start() can only be called once")
        s = time.time()

        if self.CPU_AFFINITY_STRATEGY:
            self.set_parent_affinity_mask()

        if sys.platform.startswith('win') and self.WIN_USE_JOB_OBJECT:
            self._add_to_job_object()

        self.child_processes = []
        for i in range(self.number_of_child_processes):
            logger.info("Starting %s", self.get_child_name(i))
            cmd = self.get_child_process_cmd(i)
            logger.debug("Commandline for %s: %s", self.get_child_name(i), json.dumps(cmd))
            p = self.get_Popen_class()(cmd, **self.get_Popen_kwargs(i, close_fds=self.CLOSE_FDS))

            if self.CPU_AFFINITY_STRATEGY and p.poll() is None:
                try:
                    self.set_child_affinity_mask(p.pid, i)
                except Exception as e:
                    logger.error("Unable to set affinity for %s process %d: %s", self.get_child_name(i), p.pid, e)
            self.child_processes.append(self.CHILD_COMMS_STRATEGY(p, self.ECHO_STD_ERR, i, self))

        if sys.platform.startswith('win') and self.WIN_PASS_HANDLES_OVER_COMMANDLINE:
            logger.debug("Waiting for child stream duplication events")
            for c in self.child_processes:
                c._process_instance.wait_for_child_stream_duplication_event(timeout=timeout-(time.time()-s)-3)

        self.wait_for_start(timeout - (time.time()-s))
        logger.info("All child processes initialised with strategy %s", self.CHILD_COMMS_STRATEGY.__name__)

    def wait_for_start(self, timeout):
        """Waits (a maximum of timeout) until all children of process_family have started"""
        end_time = time.time() + timeout
        command_processes = []
        try:
            for child_process in self.child_processes:
                command_processes.append(child_process.monitor_child_startup(end_time))
            for c in command_processes:
                # ping the process
                next(c)
            # results
            return [next(c) for c in command_processes]
        finally:
            for c in command_processes:
                c.close()


    def stop(self, timeout=30, wait=True):
        """Stops children. Returns the number that required termination (or None if wait=False)"""
        clean_timeout = timeout - 1
        start_time = time.time()
        self.send_stop(clean_timeout)
        if wait:
            remaining_time = timeout - (time.time() - start_time)
            return self.wait_for_stop_and_then_terminate(timeout=remaining_time)

    def send_stop(self, timeout):
        """Instructs all process_family children to stop"""
        end_time = time.time() + timeout
        command_processes = []
        try:
            for child_process in self.child_processes:
                if not child_process.is_stopped():
                    command_processes.append(child_process.stop_child(end_time))
            for c in command_processes:
                # ping the process
                next(c)
            # results
            return [next(c) for c in command_processes]
        finally:
            for c in command_processes:
                c.close()

    def wait_for_stop_and_then_terminate(self, timeout=30):
        """Waits for children to stop, but terminates them if necessary. Returns the number terminated"""
        clean_timeout = timeout - 1
        start_time = time.time()
        if self.CHILD_COMMS_STRATEGY.CAN_WAIT_FOR_TERMINATE:
            logger.debug("Waiting for child processes to terminate")
            self._wait_for_children_to_terminate(start_time, clean_timeout)

        num_terminated = 0
        if self.child_processes:
            #We've nearly run out of time - let's try and kill them:
            logger.info("Attempting to kill child processes")
            for p in list(self.child_processes):
                try:
                    num_terminated += 1
                    if process_exists(p.pid):
                        kill_process(p.pid)
                except Exception as e:
                    logger.warning("Failed to kill child process %s with PID %s: %s\n%s", p.name, p.pid, e, _traceback_str())
            self._wait_for_children_to_terminate(start_time, timeout)
        return num_terminated

    def _wait_for_children_to_terminate(self, start_time, timeout):
        first_run = True
        while self.child_processes and (first_run or time.time() - start_time < timeout):
            for p in list(self.child_processes):
                if p.is_stopped():
                    self.child_processes.remove(p)
            if first_run:
                first_run = False
            else:
                time.sleep(0.1)


    def _find_module_filename(self, modulename):
        """finds the filename of the module with the given name (supports submodules)"""
        loader = pkgutil.find_loader(modulename)
        if loader is None:
            raise ImportError(modulename)
        search_path = loader.get_filename(modulename)
        return search_path
