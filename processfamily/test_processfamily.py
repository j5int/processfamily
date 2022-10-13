from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from future import standard_library

standard_library.install_aliases()
from builtins import str
from builtins import range
from builtins import *
from future.utils import text_to_native_str, native_str, PY2

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
import pytest
from pytest_lazyfixture import lazy_fixture

from processfamily.futurecompat import get_env_dict, list_to_native_str
from processfamily.processes import get_process_affinity, set_process_affinity, cpu_count

if sys.platform.startswith('win'):
    from processfamily._winprocess_ctypes import CAN_USE_EXTENDED_STARTUPINFO, CREATE_BREAKAWAY_FROM_JOB
    import win32service
    import win32serviceutil
    from processfamily.test.ExeBuilder import build_service_exe
    from processfamily.processes import USE_PROCESS_QUERY_LIMITED_INFORMATION

pid_dir = os.path.join(os.path.dirname(__file__), 'test', 'tmp', 'pid')
path_to_ParentProcessPy = os.path.join(os.path.dirname(__file__), 'test', 'ParentProcess.py')


def process_exists_or_access_denied(pid):
    try:
        return process_exists(pid)
    except AccessDeniedError as e:
        # It is most likely that this process does exist!
        return True


def kill_process_ignore_access_denied(pid):
    try:
        return kill_process(pid)
    except AccessDeniedError as e:
        # Can't do anything about this
        pass


def assert_middle_child_port_unbound():
    port = Config.get_starting_port_nr() + 2
    logging.info("Checking for ability to bind to port %d", port)
    serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        serversocket.bind(("", port))
    except Exception as e:
        pytest.fail("Middle child port is not unbound as expected")
    finally:
        serversocket.close()


def get_pid_files():
    return glob.glob(os.path.join(pid_dir, "*.pid"))


def get_pids():
    pids = []
    for filename in get_pid_files():
        with open(filename) as pidfile:
            pids.append(int(pidfile.read()))
    return pids


def kill_parent():
    for pid_file in get_pid_files():
        if os.path.basename(pid_file).startswith('c'):
            continue
        with open(pid_file, "r") as f:
            pid = f.read().strip()
        kill_process(int(pid))


def check_server_ports_unbound():
    bound_ports = []
    for pnumber in range(4):
        port = Config.get_starting_port_nr() + pnumber
        # I just try and bind to the server port and see if I have a problem:
        logging.info("Checking for ability to bind to port %d", port)
        serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            serversocket.bind(("", port))
        except Exception as e:
            bound_ports.append(port)
        finally:
            serversocket.close()
    assert not bound_ports, "The following ports are still bound: %s" % ', '.join([str(p) for p in bound_ports])


def send_http_command(port, command, params=None, **kwargs):
    r = requests.get('http://localhost:%d/%s' % (port, command), params=params, **kwargs)
    j = r.json
    if callable(j):
        return j()
    else:
        # This is the old requests api:
        return j


def send_parent_http_command(command, params=None, **kwargs):
    return send_http_command(Config.get_starting_port_nr(), command, params=params, **kwargs)


def send_middle_child_http_command(command, params=None, **kwargs):
    return send_http_command(Config.get_starting_port_nr() + 2, command, params=params, **kwargs)


def freeze_up_middle_child():
    # First check that we can do this fast (i.e. things aren't stuttering because of environment):
    for i in range(5):
        send_middle_child_http_command("", timeout=1)
    send_middle_child_http_command("hold_gil?t=%d" % (60 * 10))  # Freeze up for 10 minutes
    while True:
        # Try and do this request until it takes longer than 1 sec - this would mean that we have successfully got stuck
        try:
            send_middle_child_http_command("", timeout=1)
        except requests.exceptions.Timeout as t:
            break


def wait_for_process_to_stop(process, timeout):
    if process is None:
        logging.info("No process to wait for")
        return
    logging.info("Waiting for process (%d) to finish", process.pid)
    start_time = time.time()
    while time.time() - start_time < timeout:
        if process.poll() is None:
            time.sleep(0.3)
        else:
            return


def check_stop(force_kills=0, timeout=None):
    """Checks that a stop succeeds, and that the number of child processes that had to be terminated is as expected"""
    params = {"timeout": str(timeout)} if timeout else {}
    child_processes_terminated = send_parent_http_command("stop", params=params)
    if child_processes_terminated != str(force_kills):
        raise ValueError("Stop received, but parent reports %r instead of %r child processes terminated",
                         child_processes_terminated, force_kills)


def CanOpenSCManager():
    s = None
    try:
        s = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_ALL_ACCESS)
    except:
        return False
    else:
        return True
    finally:
        if s:
            win32service.CloseServiceHandle(s)


def send_stop_and_then_wait_for_service_to_stop_ignore_errors():
    try:
        win32serviceutil.StopService(Config.svc_name)
        wait_for_service_to_stop(20)
    except Exception as e:
        pass


def wait_for_service_to_stop(timeout):
    start_time = time.time()
    while time.time() - start_time < timeout:
        if win32serviceutil.QueryServiceStatus(Config.svc_name)[1] != win32service.SERVICE_STOPPED:
            time.sleep(0.3)


def grant_network_service_rights(folder, rights):
    try:
        subprocess.check_call(["cmd.exe", "/C", "icacls", folder, "/grant", "NETWORK SERVICE:(OI)(CI)%s" % rights])
    except Exception as e:
        logging.warning("icacls command returned a non-zero response for folder/file '%s'")


class FunkyWebServerFixtureBase(object):
    skip_crash_test = None
    skip_interrupt_main = None

    def __init__(self, *args, **kwargs):
        pass

    def start_parent_process(self, timeout):
        raise NotImplementedError()

    def wait_for_parent_to_stop(self, timeout):
        raise NotImplementedError()

    def try_and_stop_everything_for_tear_down(self):
        # Override this if you can do something about stopping everything
        pass

    @classmethod
    def shouldSkip(cls):
        return None

    def setup(self):
        if not os.path.exists(pid_dir):
            os.makedirs(pid_dir)
        for pid_file in get_pid_files():
            with open(pid_file, "r") as f:
                pid = f.read().strip()
            if pid and process_exists_or_access_denied(int(pid)):
                logging.warning(
                    ("Process with pid %s is stilling running. This could be a problem " + \
                     "(but it might be a new process with a recycled pid so I'm not killing it).") % pid)
            else:
                os.remove(pid_file)
        check_server_ports_unbound()

    def teardown(self):
        command_file = os.path.join(os.path.dirname(__file__), 'test', 'tmp', 'command.txt')
        if os.path.exists(command_file):
            os.remove(command_file)

        self.wait_for_parent_to_stop(5)

        # Now check that no processes are left over:
        start_time = time.time()
        processes_left_running = []
        for pid_file in get_pid_files():
            with open(pid_file, "r") as f:
                pid = f.read().strip()
            if pid:
                while process_exists_or_access_denied(int(pid)) and time.time() - start_time < 5:
                    time.sleep(0.3)
                if process_exists_or_access_denied(int(pid)):
                    processes_left_running.append(int(pid))
            os.remove(pid_file)

        if processes_left_running:
            for pid in processes_left_running:
                try:
                    kill_process_ignore_access_denied(pid)
                    processes_left_running.remove(pid)
                except Exception as e:
                    logging.warning("Error killing process with pid %d: %s", pid, _traceback_str())

            self.try_and_stop_everything_for_tear_down()

            start_time = time.time()
            for pid in processes_left_running:
                while process_exists_or_access_denied(int(pid)) and time.time() - start_time < 40:
                    time.sleep(0.3)


        check_server_ports_unbound()
        assert not processes_left_running, "There should have been no PIDs left running but there were: %s" % (
            ', '.join([str(p) for p in processes_left_running]))

    def start_up(self, test_command=None, wait_for_middle_child=True, wait_for_children=True, parent_timeout=None):
        command_file = os.path.join(os.path.dirname(__file__), 'test', 'tmp', 'command.txt')
        if test_command:
            with open(command_file, "w") as f:
                f.write(test_command)
        elif os.path.exists(command_file):
            os.remove(command_file)

        self.start_parent_process(timeout=parent_timeout)
        # Wait up to 15 secs for the all ports to be available (the parent might wait 10 for a middle child):
        start_time = time.time()
        still_waiting = True
        ports_to_wait = list(range(4)) if wait_for_children else [0]
        if not wait_for_middle_child:
            ports_to_wait.remove(2)
        while still_waiting and time.time() - start_time < 30:
            still_waiting = False
            for i in ports_to_wait:
                try:
                    s = socket.socket()
                    try:
                        s.connect(("localhost", Config.get_starting_port_nr() + i))
                    except socket.error as e:
                        still_waiting = True
                        break
                finally:
                    s.close()
            if still_waiting:
                time.sleep(0.3)
        assert not still_waiting, "Waited 30 seconds and some http ports are still not accessible"

    @classmethod
    def pseudo_fixture(cls, *args, **kwargs):
        reason = cls.shouldSkip()
        if reason is not None:
            pytest.skip(reason)
        instance = cls(*args, **kwargs)
        instance.setup()
        yield instance
        instance.teardown()


class NormalSubprocessFixture(FunkyWebServerFixtureBase):
    skip_crash_test = "The crash test throws up a dialog in this context" if sys.platform.startswith('win') else None

    def start_parent_process(self, timeout=None):
        kwargs = {}
        if sys.platform.startswith('win'):
            kwargs['creationflags'] = CREATE_BREAKAWAY_FROM_JOB
        environ = get_env_dict()
        if timeout:
            environ[text_to_native_str("STARTUP_TIMEOUT")] = native_str(timeout)
        self.parent_process = subprocess.Popen(
            list_to_native_str([sys.executable, path_to_ParentProcessPy]),
            close_fds=True, env=environ, **kwargs)
        threading.Thread(target=self.parent_process.communicate).start()

    def wait_for_parent_to_stop(self, timeout):
        wait_for_process_to_stop(getattr(self, 'parent_process', None), timeout)


@pytest.fixture()
def normal_subprocess():
    for x in NormalSubprocessFixture.pseudo_fixture():
        yield x


class PythonwFixture(FunkyWebServerFixtureBase):
    skip_crash_test = "The crash test throws up a dialog in this context" if sys.platform.startswith('win') else None

    def start_parent_process(self, timeout=None):

        self.parent_process = subprocess.Popen(
            [Config.pythonw_exe, path_to_ParentProcessPy],
            close_fds=True,
            creationflags=CREATE_BREAKAWAY_FROM_JOB)
        threading.Thread(target=self.parent_process.communicate).start()

    def wait_for_parent_to_stop(self, timeout):
        wait_for_process_to_stop(getattr(self, 'parent_process', None), timeout)

    @classmethod
    def shouldSkip(cls):
        if not sys.platform.startswith('win'):
            return "Fixture only runs on windows"
        else:
            return super(PythonwFixture, cls).shouldSkip()


@pytest.fixture()
def pythonw():
    for x in PythonwFixture.pseudo_fixture():
        yield x


# To run the tests with this fixture you must
# make sure the file <env>\python\Lib\site-packages\win32\pywintypes<VER>.dll exists, if it does not you need to
# copy it from <env>\python\Lib\site-packages\pywin32_system32 and put it there.
#
# then you must open an administrator console
# then run pytest -k windows_service
class WindowsServiceFixture(FunkyWebServerFixtureBase):
    skip_interrupt_main = "Interrupt main doesn't do anything useful in a windows service"

    def __init__(self, username, *args, **kwargs):
        self.username = username

    def try_and_stop_everything_for_tear_down(self):
        send_stop_and_then_wait_for_service_to_stop_ignore_errors()

    def start_parent_process(self, timeout=None):
        win32serviceutil.StartService(Config.svc_name)

    def wait_for_parent_to_stop(self, timeout):
        wait_for_service_to_stop(timeout)

    @classmethod
    def shouldSkip(cls):
        if not sys.platform.startswith("win"):
            return "Fixture only runs on windows"
        elif not CanOpenSCManager():
            return "Fixture must be run as an Administrator"
        else:
            return super(WindowsServiceFixture, cls).shouldSkip()


@pytest.fixture(scope="session")
def network_service_user_permissions():
    reason = WindowsServiceFixture.shouldSkip()
    if reason:
        pytest.skip(reason)
    # I do this just in case we left the service running by interrupting the tests
    send_stop_and_then_wait_for_service_to_stop_ignore_errors()
    tmp_dir = os.path.join(os.path.dirname(__file__), 'test', 'tmp')
    if not os.path.exists(tmp_dir):
        os.makedirs(tmp_dir)
    # Make sure network service has full access to the tmp folder (and these are inheritable)
    grant_network_service_rights(tmp_dir, "F")
    # And read / execute access to Python, and other folders on the python path:
    grant_network_service_rights(os.path.abspath(sys.prefix), "RX")
    done_paths = [os.path.abspath(sys.prefix)]
    for path_item in sorted(sys.path, key=lambda p: len(os.path.abspath(p))):
        abspath_item = os.path.abspath(path_item)
        already_done = False
        for p in done_paths:
            if abspath_item.startswith(p):
                already_done = True
                break
        if not already_done:
            grant_network_service_rights(abspath_item, "RX")
            done_paths.append(abspath_item)


@pytest.fixture(scope="session", params=[None, "NT AUTHORITY\\NetworkService"])
def service_exe(request, network_service_user_permissions):
    reason = WindowsServiceFixture.shouldSkip()
    if reason:
        pytest.skip(reason)
    service_username = request.param
    send_stop_and_then_wait_for_service_to_stop_ignore_errors()
    exe = build_service_exe()
    cmd = [exe] + (["--username", service_username] if service_username else []) + ["install"]
    subprocess.check_call(list_to_native_str(cmd))
    yield (exe, service_username)
    subprocess.check_call([exe, "remove"])


@pytest.fixture()
def windows_service(service_exe):
    for x in WindowsServiceFixture.pseudo_fixture(service_exe[1]):
        yield x


# If you only want to run against one fixture specify -k fixture on the command line
# e.g. pytest -k normal_subprocess
@pytest.fixture(params=[
    lazy_fixture('normal_subprocess'),
    lazy_fixture('pythonw'),
    lazy_fixture('windows_service'),
])
def fws(request):
    return request.param


class TestFunkyWebServer():

    def test_parent_stop(self, fws):
        fws.start_up()
        check_stop()

    def test_parent_exit(self, fws):
        fws.start_up()
        send_parent_http_command("exit")

    def test_parent_crash(self, fws):
        if fws.skip_crash_test:
            pytest.skip(fws.skip_crash_test)
        if isinstance(fws, WindowsServiceFixture):
            pytest.xfail("Teardown is failing for some reason. We should figure it out later")
        fws.start_up()
        send_parent_http_command("crash")

    def test_parent_interrupt_main(self, fws):
        if fws.skip_interrupt_main:
            pytest.skip(fws.skip_interrupt_main)
        fws.start_up()
        send_parent_http_command("interrupt_main")

    def test_parent_kill(self, fws, request):
        if isinstance(fws, WindowsServiceFixture):
            if not USE_PROCESS_QUERY_LIMITED_INFORMATION or fws.username is not None:
                pytest.skip("I cannot kill a network service service from here - I get an access denied error")
        fws.start_up()
        kill_parent()

    def test_parent_stop_child_locked_up(self, fws):
        fws.start_up()
        freeze_up_middle_child()
        check_stop(1, timeout=5)
        # This needs time to wait for the child for 10 seconds:
        fws.wait_for_parent_to_stop(11)

    def test_parent_exit_child_locked_up(self, fws):
        fws.start_up()
        freeze_up_middle_child()
        send_parent_http_command("exit")

    def test_parent_crash_child_locked_up(self, fws):
        if fws.skip_crash_test:
            pytest.skip(fws.skip_crash_test)
        if isinstance(fws, WindowsServiceFixture):
            pytest.xfail("Teardown is failing for some reason. Figure it out later")
        fws.start_up()
        freeze_up_middle_child()
        send_parent_http_command("crash")

    def test_parent_interrupt_main_child_locked_up(self, fws):
        if isinstance(fws, WindowsServiceFixture):
            pytest.skip("Interrupt main doesn't do anything useful in a windows service")
        fws.start_up()
        freeze_up_middle_child()
        send_parent_http_command("interrupt_main")
        # This needs time to wait for the child for 10 seconds:
        fws.wait_for_parent_to_stop(11)

    def test_parent_kill_child_locked_up(self, fws, request):
        if isinstance(fws, WindowsServiceFixture):
            if not USE_PROCESS_QUERY_LIMITED_INFORMATION or fws.username is not None:
                pytest.skip("I cannot kill a network service service from here - I get an access denied error")
        fws.start_up()
        freeze_up_middle_child()
        kill_parent()

    def test_parent_exit_child_locked_up(self, fws):
        fws.start_up()
        freeze_up_middle_child()
        send_parent_http_command("exit")

    def test_child_exit_on_start(self, fws):
        fws.start_up(test_command='child_exit_on_start', wait_for_middle_child=False)
        assert_middle_child_port_unbound()
        check_stop()

    def test_child_error_during_run(self, fws):
        fws.start_up(test_command='child_error_during_run', wait_for_middle_child=False)
        check_stop()

    def test_child_freeze_on_start(self, fws):
        fws.start_up(test_command='child_freeze_on_start', wait_for_middle_child=False, parent_timeout=2)
        assert_middle_child_port_unbound()
        check_stop(1, timeout=5)

    def test_child_error_on_start(self, fws):
        fws.start_up(test_command='child_error_on_start', wait_for_middle_child=False)
        assert_middle_child_port_unbound()
        check_stop()

    def test_child_error_during_init(self, fws):
        fws.start_up(test_command='child_error_during_init', wait_for_middle_child=False)
        assert_middle_child_port_unbound()
        check_stop()

    def test_child_freeze_during_init(self, fws):
        fws.start_up(test_command='child_freeze_during_init', wait_for_middle_child=False, parent_timeout=2)
        assert_middle_child_port_unbound()
        check_stop(1, timeout=5)
        fws.wait_for_parent_to_stop(11)

    def test_child_crash_on_start(self, fws):
        if fws.skip_crash_test:
            pytest.skip(fws.skip_crash_test)
        fws.start_up(test_command='child_crash_on_start', wait_for_middle_child=False)
        assert_middle_child_port_unbound()
        check_stop()

    if not sys.platform.startswith('win'):
        def test_sigint(self, fws):
            fws.start_up()
            os.kill(fws.parent_process.pid, signal.SIGINT)

        def test_sigint_child_locked_up(self, fws):
            fws.start_up()
            freeze_up_middle_child()
            os.kill(fws.parent_process.pid, signal.SIGINT)
            # This needs time to wait for the child for 10 seconds:
            fws.wait_for_parent_to_stop(11)

    def test_file_open_by_parent_before_fork_can_be_closed_and_deleted(self, fws):
        fws.start_up()
        result = send_parent_http_command("close_file_and_delete_it")
        assert "OK" == result, "Command to close file and delete it failed (got response: %s)" % result
        check_stop()

    def test_echo_std_err_on(self, fws):
        fws.start_up(test_command='echo_std_err')
        check_stop()

    def test_handles_over_commandline_off(self, fws):
        if not sys.platform.startswith('win') or not CAN_USE_EXTENDED_STARTUPINFO:
            fws.skipTest("This test is not supported on this platform")
        fws.start_up(test_command='handles_over_commandline_off')
        check_stop()

    def test_handles_over_commandline_off_close_fds_off(self, fws):
        if not sys.platform.startswith('win') or not CAN_USE_EXTENDED_STARTUPINFO:
            fws.skipTest("This test is not supported on this platform")
        fws.start_up(test_command='handles_over_commandline_off_close_fds_off')
        result = send_parent_http_command("close_file_and_delete_it")
        assert "FAIL" == result, "Command to close file and delete it did not fail (got response: %s)" % result
        check_stop()

    def test_close_fds_off(self, fws):
        fws.start_up(test_command='close_fds_off')
        result = send_parent_http_command("close_file_and_delete_it")
        if sys.platform.startswith('win'):
            # On linux this works fine
            assert "FAIL" == result, "Command to close file and delete it did not fail (got response: %s)" % result
        else:
            # TODO: a relevant test on linux?
            pass
        check_stop()

    def test_child_comms_strategy_stdin_close(self, fws):
        fws.start_up(test_command='use_cat', wait_for_children=False)
        check_stop()

    def test_child_comms_strategy_none(self, fws):
        fws.start_up(test_command='use_cat_comms_none', wait_for_children=False)
        # we don't actually have the ability to tell these children to stop
        check_stop(3)

    def test_child_comms_strategy_signal(self, fws):
        fws.start_up(test_command='use_signal', wait_for_children=False)
        # since we're not waiting for the children to start up, give them a chance to register signal handlers
        time.sleep(0.5)
        check_stop()

    def test_use_job_object_off(self, fws):
        fws.start_up(test_command=
                     'use_job_object_off')
        check_stop()

    def test_cpu_affinity_inherit(self, fws):
        fws.start_up(test_command='cpu_affinity_inherit')
        check_stop()

    def test_affinity_inherited_by_children(self, fws):
        tied_to_cores = [0]
        set_process_affinity(tied_to_cores)
        fws.start_up(test_command='cpu_affinity_inherit')
        children_pids = []
        for pid in get_pids():
            children_pids.append(list(get_process_affinity(pid)))
        check_stop()
        for child_pids in children_pids:
            assert child_pids == tied_to_cores
        set_process_affinity(range(cpu_count()))

    def test_no_affinity_children_float(self, fws):
        tied_to_cores = {0}
        all_cores = set(range(cpu_count()))
        set_process_affinity(tied_to_cores)
        fws.start_up(test_command='cpu_affinity_off')
        children_affinity = []
        for pid in get_pids():
            children_affinity.append(set(get_process_affinity(pid)))
        check_stop()
        parent_pid_checked = False
        for affinity in children_affinity:
            if affinity == tied_to_cores:
                assert not parent_pid_checked, "More than 1 process detected with parent affinity"
                parent_pid_checked = True
            else:
                assert affinity == all_cores
        set_process_affinity(all_cores)


    def test_handles_over_commandline_off_file_open_by_parent(self, fws):
        if not sys.platform.startswith('win') or not CAN_USE_EXTENDED_STARTUPINFO:
            fws.skipTest("This test is not supported on this platform")
        fws.start_up(test_command='handles_over_commandline_off')
        result = send_parent_http_command("close_file_and_delete_it")
        assert "OK" == result, "Command to close file and delete it failed (got response: %s)" % result
        check_stop()


class TestWindowsService():

    def test_service_stop(self, windows_service):
        windows_service.start_up()
        win32serviceutil.StopService(Config.svc_name)

    def test_service_stop_child_locked_up(self, windows_service):
        windows_service.start_up()
        freeze_up_middle_child()
        win32serviceutil.StopService(Config.svc_name)
        # This needs time to wait for the child for 10 seconds:
        windows_service.wait_for_parent_to_stop(11)

    def test_service_stop_child_freeze_on_start(self, windows_service):
        windows_service.start_up(test_command='child_freeze_on_start', wait_for_middle_child=False)
        assert_middle_child_port_unbound()
        win32serviceutil.StopService(Config.svc_name)
        # This still needs time to wait for the child to stop for 10 seconds:
        windows_service.wait_for_parent_to_stop(11)
