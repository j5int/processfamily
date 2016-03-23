__author__ = 'matth'

import unittest
import sys
from processfamily.test import ParentProcess, Config
import os
import subprocess
import requests
import time
import socket
import logging
import glob
from processfamily.processes import process_exists, kill_process, AccessDeniedError
from processfamily import _traceback_str
import signal
import threading

if sys.platform.startswith('win'):
    from processfamily._winprocess_ctypes import CAN_USE_EXTENDED_STARTUPINFO, CREATE_BREAKAWAY_FROM_JOB

class _BaseProcessFamilyFunkyWebServerTestSuite(unittest.TestCase):

    skip_crash_test = None

    def setUp(self):
        self.pid_dir = os.path.join(os.path.dirname(__file__), 'test', 'tmp', 'pid')
        if not os.path.exists(self.pid_dir):
            os.makedirs(self.pid_dir)
        for pid_file in self.get_pid_files():
            with open(pid_file, "r") as f:
                pid = f.read().strip()
            if pid and self.process_exists_or_access_denied(int(pid)):
                logging.warning(
                    ("Process with pid %s is stilling running. This could be a problem " + \
                    "(but it might be a new process with a recycled pid so I'm not killing it).") % pid )
            else:
                os.remove(pid_file)
        self.check_server_ports_unbound()

    def process_exists_or_access_denied(self, pid):
        try:
            return process_exists(pid)
        except AccessDeniedError as e:
            #It is most likely that this process does exist!
            return True

    def kill_process_ignore_access_denied(self, pid):
        try:
            return kill_process(pid)
        except AccessDeniedError as e:
            #Can't do anything about this
            pass

    def try_and_stop_everything_for_tear_down(self):
        #Override this if you can do something about stopping everything
        pass

    def tearDown(self):
        command_file = os.path.join(os.path.dirname(__file__), 'test', 'tmp', 'command.txt')
        if os.path.exists(command_file):
            os.remove(command_file)

        self.wait_for_parent_to_stop(5)

        #Now check that no processes are left over:
        start_time = time.time()
        processes_left_running = []
        for pid_file in self.get_pid_files():
            with open(pid_file, "r") as f:
                pid = f.read().strip()
            if pid:
                while self.process_exists_or_access_denied(int(pid)) and time.time() - start_time < 5:
                    time.sleep(0.3)
                if self.process_exists_or_access_denied(int(pid)):
                    processes_left_running.append(int(pid))
            os.remove(pid_file)

        if processes_left_running:
            for pid in processes_left_running:
                try:
                    self.kill_process_ignore_access_denied(pid)
                except Exception as e:
                    logging.warning("Error killing process with pid %d: %s", pid, _traceback_str())

            self.try_and_stop_everything_for_tear_down()

            start_time = time.time()
            for pid in processes_left_running:
                while self.process_exists_or_access_denied(int(pid)) and time.time() - start_time < 40:
                    time.sleep(0.3)

        self.check_server_ports_unbound()
        self.assertFalse(processes_left_running, msg="There should have been no PIDs left running but there were: %s" % (', '.join([str(p) for p in processes_left_running])))


    def start_up(self, test_command=None, wait_for_middle_child=True, wait_for_children=True, parent_timeout=None):
        command_file = os.path.join(os.path.dirname(__file__), 'test', 'tmp', 'command.txt')
        if test_command:
            with open(command_file, "w") as f:
                f.write(test_command)
        elif os.path.exists(command_file):
            os.remove(command_file)

        self.start_parent_process(timeout=parent_timeout)
        #Wait up to 15 secs for the all ports to be available (the parent might wait 10 for a middle child):
        start_time = time.time()
        still_waiting = True
        ports_to_wait = range(4) if wait_for_children else [0]
        if not wait_for_middle_child:
            ports_to_wait.remove(2)
        while still_waiting and time.time() - start_time < 15:
            still_waiting = False
            for i in ports_to_wait:
                try:
                    s = socket.socket()
                    try:
                        s.connect(("localhost", Config.get_starting_port_nr()+i))
                    except socket.error, e:
                        still_waiting = True
                        break
                finally:
                    s.close()
            if still_waiting:
                time.sleep(0.3)
        self.assertFalse(still_waiting, "Waited 10 seconds and some http ports are still not accessible")

    def assert_middle_child_port_unbound(self):
        port = Config.get_starting_port_nr()+2
        logging.info("Checking for ability to bind to port %d", port)
        serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if not sys.platform.startswith('win'):
                #On linux I need this setting cos we are starting and stopping things
                #so frequently that they are still in a STOP_WAIT state when I get here
                serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            serversocket.bind(("", port))
        except Exception as e:
            self.fail("Middle child port is not unbound as expected")
        finally:
            serversocket.close()

    def get_pid_files(self):
        return glob.glob(os.path.join(self.pid_dir, "*.pid"))

    def kill_parent(self):
        for pid_file in self.get_pid_files():
            if os.path.basename(pid_file).startswith('c'):
                continue
            with open(pid_file, "r") as f:
                pid = f.read().strip()
            kill_process(int(pid))

    def check_stop(self, force_kills=0, timeout=None):
        """Checks that a stop succeeds, and that the number of child processes that had to be terminated is as expected"""
        params = {"timeout": str(timeout)} if timeout else {}
        child_processes_terminated = self.send_parent_http_command("stop", params=params)
        if child_processes_terminated != str(force_kills):
            raise ValueError("Stop received, but parent reports %r instead of %r child processes terminated",
                             child_processes_terminated, force_kills)

    def test_parent_stop(self):
        self.start_up()
        self.check_stop()

    def test_parent_exit(self):
        self.start_up()
        self.send_parent_http_command("exit")

    def test_parent_crash(self):
        if self.skip_crash_test:
            self.skipTest(self.skip_crash_test)
        self.start_up()
        self.send_parent_http_command("crash")

    def test_parent_interrupt_main(self):
        self.start_up()
        self.send_parent_http_command("interrupt_main")

    def test_parent_kill(self):
        self.start_up()
        self.kill_parent()

    def test_parent_stop_child_locked_up(self):
        self.start_up()
        self.freeze_up_middle_child()
        self.check_stop(1, timeout=5)
        #This needs time to wait for the child for 10 seconds:
        self.wait_for_parent_to_stop(11)

    def test_parent_exit_child_locked_up(self):
        self.start_up()
        self.freeze_up_middle_child()
        self.send_parent_http_command("exit")

    def test_parent_crash_child_locked_up(self):
        if self.skip_crash_test:
            self.skipTest(self.skip_crash_test)
        self.start_up()
        self.freeze_up_middle_child()
        self.send_parent_http_command("crash")

    def test_parent_interrupt_main_child_locked_up(self):
        self.start_up()
        self.freeze_up_middle_child()
        self.send_parent_http_command("interrupt_main")
        #This needs time to wait for the child for 10 seconds:
        self.wait_for_parent_to_stop(11)

    def test_parent_kill_child_locked_up(self):
        self.start_up()
        self.freeze_up_middle_child()
        self.kill_parent()

    def test_parent_exit_child_locked_up(self):
        self.start_up()
        self.freeze_up_middle_child()
        self.send_parent_http_command("exit")

    def test_child_exit_on_start(self):
        self.start_up(test_command='child_exit_on_start', wait_for_middle_child=False)
        self.assert_middle_child_port_unbound()
        self.check_stop()

    def test_child_error_during_run(self):
        self.start_up(test_command='child_error_during_run', wait_for_middle_child=False)
        self.check_stop()

    def test_child_freeze_on_start(self):
        self.start_up(test_command='child_freeze_on_start', wait_for_middle_child=False, parent_timeout=2)
        self.assert_middle_child_port_unbound()
        self.check_stop(1, timeout=5)

    def test_child_error_on_start(self):
        self.start_up(test_command='child_error_on_start', wait_for_middle_child=False)
        self.assert_middle_child_port_unbound()
        self.check_stop()

    def test_child_error_during_init(self):
        self.start_up(test_command='child_error_during_init', wait_for_middle_child=False)
        self.assert_middle_child_port_unbound()
        self.check_stop()

    def test_child_freeze_during_init(self):
        self.start_up(test_command='child_freeze_during_init', wait_for_middle_child=False, parent_timeout=2)
        self.assert_middle_child_port_unbound()
        self.check_stop(1, timeout=5)
        self.wait_for_parent_to_stop(11)

    def test_child_crash_on_start(self):
        if self.skip_crash_test:
            self.skipTest(self.skip_crash_test)
        self.start_up(test_command='child_crash_on_start', wait_for_middle_child=False)
        self.assert_middle_child_port_unbound()
        self.check_stop()

    if not sys.platform.startswith('win'):
        def test_sigint(self):
            self.start_up()
            os.kill(self.parent_process.pid, signal.SIGINT)

        def test_sigint_child_locked_up(self):
            self.start_up()
            self.freeze_up_middle_child()
            os.kill(self.parent_process.pid, signal.SIGINT)
            #This needs time to wait for the child for 10 seconds:
            self.wait_for_parent_to_stop(11)

    def test_file_open_by_parent_before_fork_can_be_closed_and_deleted(self):
        self.start_up()
        result = self.send_parent_http_command("close_file_and_delete_it")
        self.assertEqual("OK", result, "Command to close file and delete it failed (got response: %s)" % result)
        self.check_stop()

    def test_echo_std_err_on(self):
        self.start_up(test_command='echo_std_err')
        self.check_stop()

    def test_handles_over_commandline_off(self):
        if not sys.platform.startswith('win') or not CAN_USE_EXTENDED_STARTUPINFO:
            self.skipTest("This test is not supported on this platform")
        self.start_up(test_command='handles_over_commandline_off')
        self.check_stop()

    def test_handles_over_commandline_off_close_fds_off(self):
        if not sys.platform.startswith('win') or not CAN_USE_EXTENDED_STARTUPINFO:
            self.skipTest("This test is not supported on this platform")
        self.start_up(test_command='handles_over_commandline_off_close_fds_off')
        result = self.send_parent_http_command("close_file_and_delete_it")
        self.assertEqual("FAIL", result, "Command to close file and delete it did not fail (got response: %s)" % result)
        self.check_stop()

    def test_close_fds_off(self):
        self.start_up(test_command='close_fds_off')
        result = self.send_parent_http_command("close_file_and_delete_it")
        if sys.platform.startswith('win'):
            #On linux this works fine
            self.assertEqual("FAIL", result, "Command to close file and delete it did not fail (got response: %s)" % result)
        else:
            #TODO: a relevant test on linux?
            pass
        self.check_stop()

    def test_child_comms_strategy_stdin_close(self):
        self.start_up(test_command='use_cat', wait_for_children=False)
        self.check_stop()

    def test_child_comms_strategy_none(self):
        self.start_up(test_command='use_cat_comms_none', wait_for_children=False)
        # we don't actually have the ability to tell these children to stop
        self.check_stop(3)

    def test_child_comms_strategy_signal(self):
        self.start_up(test_command='use_signal', wait_for_children=False)
        # since we're not waiting for the children to start up, give them a chance to register signal handlers
        time.sleep(0.5)
        self.check_stop()

    def test_use_job_object_off(self):
        self.start_up(test_command=
                      'use_job_object_off')
        self.check_stop()

    def test_cpu_affinity_off(self):
        self.start_up(test_command='cpu_affinity_off')
        self.check_stop()

    def test_handles_over_commandline_off_file_open_by_parent(self):
        if not sys.platform.startswith('win') or not CAN_USE_EXTENDED_STARTUPINFO:
            self.skipTest("This test is not supported on this platform")
        self.start_up(test_command='handles_over_commandline_off')
        result = self.send_parent_http_command("close_file_and_delete_it")
        self.assertEqual("OK", result, "Command to close file and delete it failed (got response: %s)" % result)
        self.check_stop()

    def freeze_up_middle_child(self):
        #First check that we can do this fast (i.e. things aren't stuttering because of environment):
        for i in range(5):
            self.send_middle_child_http_command("", timeout=1)
        self.send_middle_child_http_command("hold_gil?t=%d" % (60*10)) #Freeze up for 10 minutes
        while True:
            #Try and do this request until it takes longer than 1 sec - this would mean that we have successfully got stuck
            try:
                self.send_middle_child_http_command("", timeout=1)
            except requests.exceptions.Timeout as t:
                break

    def check_server_ports_unbound(self):
        bound_ports = []
        for pnumber in range(4):
            port = Config.get_starting_port_nr() + pnumber
            #I just try and bind to the server port and see if I have a problem:
            logging.info("Checking for ability to bind to port %d", port)
            serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                if not sys.platform.startswith('win'):
                    #On linux I need this setting cos we are starting and stopping things
                    #so frequently that they are still in a STOP_WAIT state when I get here
                    serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                serversocket.bind(("", port))
            except Exception as e:
                bound_ports.append(port)
            finally:
                serversocket.close()
        self.assertFalse(bound_ports, "The following ports are still bound: %s" % ', '.join([str(p) for p in bound_ports]))

    def get_path_to_ParentProcessPy(self):
        return os.path.join(os.path.dirname(__file__), 'test', 'ParentProcess.py')

    def send_parent_http_command(self, command, params=None, **kwargs):
        return self.send_http_command(Config.get_starting_port_nr(), command, params=params, **kwargs)

    def send_middle_child_http_command(self, command, params=None, **kwargs):
        return self.send_http_command(Config.get_starting_port_nr()+2, command, params=params, **kwargs)

    def send_http_command(self, port, command, params=None, **kwargs):
        r = requests.get('http://localhost:%d/%s' % (port, command), params=params, **kwargs)
        j = r.json
        if callable(j):
            return j()
        else:
            #This is the old requests api:
            return j

    def wait_for_process_to_stop(self, process, timeout):
        if process is None:
            logging.info("No process to wait for")
            return
        logging.info("Waiting for process (%d) to finish", process.pid)
        start_time = time.time()
        while time.time()-start_time < timeout:
            if process.poll() is None:
                time.sleep(0.3)
            else:
                return


class NormalSubprocessTests(_BaseProcessFamilyFunkyWebServerTestSuite):

    skip_crash_test = "The crash test throws up a dialog in this context" if sys.platform.startswith('win') else None

    def start_parent_process(self, timeout=None):
        kwargs={}
        if sys.platform.startswith('win'):
            kwargs['creationflags'] = CREATE_BREAKAWAY_FROM_JOB
        environ = os.environ.copy()
        if timeout:
            environ["STARTUP_TIMEOUT"] = str(timeout)
        self.parent_process = subprocess.Popen(
            [sys.executable, self.get_path_to_ParentProcessPy()],
            close_fds=True, env=environ, **kwargs)
        threading.Thread(target=self.parent_process.communicate).start()

    def wait_for_parent_to_stop(self, timeout):
        self.wait_for_process_to_stop(getattr(self, 'parent_process', None), timeout)

if sys.platform.startswith('win'):
    import win32service
    import win32serviceutil
    from processfamily.test.ExeBuilder import build_service_exe
    from processfamily.processes import USE_PROCESS_QUERY_LIMITED_INFORMATION

    class PythonWTests(_BaseProcessFamilyFunkyWebServerTestSuite):

        skip_crash_test = "The crash test throws up a dialog in this context" if sys.platform.startswith('win') else None

        def start_parent_process(self, timeout=None):

            self.parent_process = subprocess.Popen(
                [Config.pythonw_exe, self.get_path_to_ParentProcessPy()],
                close_fds=True,
                creationflags=CREATE_BREAKAWAY_FROM_JOB)
            threading.Thread(target=self.parent_process.communicate).start()

        def wait_for_parent_to_stop(self, timeout):
            self.wait_for_process_to_stop(getattr(self, 'parent_process', None), timeout)

    class WindowsServiceTests(_BaseProcessFamilyFunkyWebServerTestSuite):

        @classmethod
        def setUpClass(cls, service_username=None):
            cls.send_stop_and_then_wait_for_service_to_stop_ignore_errors()
            cls.service_exe = build_service_exe()
            subprocess.check_call([cls.service_exe] + (["--username", service_username] if service_username else []) + ["install"])

        @classmethod
        def tearDownClass(cls):
            if hasattr(cls, 'service_exe'):
                subprocess.check_call([cls.service_exe, "remove"])

        def try_and_stop_everything_for_tear_down(self):
            self.send_stop_and_then_wait_for_service_to_stop_ignore_errors()

        def start_parent_process(self, timeout=None):
            win32serviceutil.StartService(Config.svc_name)

        def wait_for_parent_to_stop(self, timeout):
            self.wait_for_service_to_stop(timeout)

        @classmethod
        def wait_for_service_to_stop(cls, timeout):
            start_time = time.time()
            while time.time()-start_time < timeout:
                if win32serviceutil.QueryServiceStatus(Config.svc_name)[1] != win32service.SERVICE_STOPPED:
                    time.sleep(0.3)

        def test_parent_interrupt_main(self):
            self.skipTest("Interrupt main doesn't do anything useful in a windows service")

        def test_parent_interrupt_main_child_locked_up(self):
            self.skipTest("Interrupt main doesn't do anything useful in a windows service")

        def test_service_stop(self):
            self.start_up()
            win32serviceutil.StopService(Config.svc_name)

        def test_service_stop_child_locked_up(self):
            self.start_up()
            self.freeze_up_middle_child()
            win32serviceutil.StopService(Config.svc_name)
            #This needs time to wait for the child for 10 seconds:
            self.wait_for_parent_to_stop(11)

        def test_service_stop_child_freeze_on_start(self):
            self.start_up(test_command='child_freeze_on_start', wait_for_middle_child=False)
            self.assert_middle_child_port_unbound()
            win32serviceutil.StopService(Config.svc_name)
            #This still needs time to wait for the child to stop for 10 seconds:
            self.wait_for_parent_to_stop(11)

        @classmethod
        def send_stop_and_then_wait_for_service_to_stop_ignore_errors(cls):
            try:
                win32serviceutil.StopService(Config.svc_name)
                cls.wait_for_service_to_stop(20)
            except Exception as e:
                pass

        if not USE_PROCESS_QUERY_LIMITED_INFORMATION:
            def test_parent_kill(self):
                self.skipTest("I cannot kill a network service service from here - I get an access denied error")

            def test_parent_kill_child_locked_up(self):
                self.skipTest("I cannot kill a network service service from here - I get an access denied error")

    class WindowsServiceNetworkServiceUserTests(WindowsServiceTests):

        @staticmethod
        def grant_network_service_rights(folder, rights):
            try:
                subprocess.check_call(["cmd.exe", "/C", "icacls", folder, "/grant", "NETWORK SERVICE:(OI)(CI)%s" % rights])
            except Exception as e:
                logging.warning("icacls command returned a non-zero response for folder/file '%s'")

        @classmethod
        def setUpClass(cls):
            #I do this just in case we left the service running by interrupting the tests
            cls.send_stop_and_then_wait_for_service_to_stop_ignore_errors()

            tmp_dir = os.path.join(os.path.dirname(__file__), 'test', 'tmp')
            if not os.path.exists(tmp_dir):
                os.makedirs(tmp_dir)
            #Make sure network service has full access to the tmp folder (and these are inheritable)
            cls.grant_network_service_rights(tmp_dir, "F")
            #And read / execute access to Python, and other folders on the python path:
            cls.grant_network_service_rights(os.path.abspath(sys.prefix), "RX")
            done_paths = [os.path.abspath(sys.prefix)]
            for path_item in sorted(sys.path, key=lambda p: len(os.path.abspath(p))):
                abspath_item = os.path.abspath(path_item)
                already_done = False
                for p in done_paths:
                    if abspath_item.startswith(p):
                        already_done = True
                        break
                if not already_done:
                    cls.grant_network_service_rights(abspath_item, "RX")
                    done_paths.append(abspath_item)

            super(WindowsServiceNetworkServiceUserTests, cls).setUpClass(service_username="NT AUTHORITY\\NetworkService")

        def test_parent_kill(self):
            self.skipTest("I cannot kill a network service service from here - I get an access denied error")

        def test_parent_kill_child_locked_up(self):
            self.skipTest("I cannot kill a network service service from here - I get an access denied error")


#Remove the base class from the module dict so it isn't smelled out by nose:
del(_BaseProcessFamilyFunkyWebServerTestSuite)