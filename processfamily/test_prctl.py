#!/usr/bin/env python

import ctypes_prctl
try:
    import prctl
except ImportError as prctl_import_error:
    prctl = None
import mmap
import os
import signal
import sys
import tempfile
import threading
import time
import unittest

class TestCtypesPrctl(unittest.TestSuite):
    prctl_module = ctypes_prctl
    prctl_module_name = 'ctypes_prctl'

    def test_pdeathsig_consistent(self):
        # this doesn't actually check that the process death signal changes, just that the function seems to work consistently
        assert self.prctl_module.get_pdeathsig() == 0
        self.prctl_module.set_pdeathsig(signal.SIGKILL)
        assert self.prctl_module.get_pdeathsig() == signal.SIGKILL
        self.prctl_module.set_pdeathsig(0)
        assert self.prctl_module.get_pdeathsig() == 0

    def test_pdeathsig_works(self):
        fd, tmpfile = tempfile.mkstemp()
        os.write(fd, '\x00' * mmap.PAGESIZE)
        os.lseek(fd, 0, os.SEEK_SET)
        buf = mmap.mmap(fd, mmap.PAGESIZE, mmap.MAP_SHARED, mmap.PROT_READ)
        CHILD_SIGNAL = signal.SIGTERM
        KILL_PARENT_WITH_SIGNAL = signal.SIGTERM
        try:
            args = [sys.executable, __file__, 'run_parent', self.prctl_module_name, tmpfile, str(CHILD_SIGNAL)]
            parent_pid = os.spawnv(os.P_NOWAIT, sys.executable, args)
            time.sleep(0.2)
            child_pid_line = buf.readline()
            child_pid = int(child_pid_line.strip())
            os.kill(parent_pid, KILL_PARENT_WITH_SIGNAL)
            _, exit_info = os.waitpid(parent_pid, 0)
            exit_code, received_signal = exit_info >> 8, exit_info & 0xff
            assert exit_code == 0
            assert received_signal == KILL_PARENT_WITH_SIGNAL
            time.sleep(0.2)
            buf.seek(50, os.SEEK_SET)
            child_signal_line = buf.readline()
            child_signum = int(child_signal_line.strip())
            assert child_signum == CHILD_SIGNAL
        finally:
            os.close(fd)
            if os.path.exists(tmpfile):
                os.remove(tmpfile)

    def test_name_consistent(self):
        # this doesn't actually check that the process name changes, just that the function seems to work consistently
        default = os.path.basename(sys.executable)
        assert self.prctl_module.get_name() == default
        self.prctl_module.set_name(default+'-prctl')
        assert self.prctl_module.get_name() == default+'-prctl'
        self.prctl_module.set_name(default)
        assert self.prctl_module.get_name() == default

if prctl is not None:
    class TestPythonPrctl(TestCtypesPrctl):
        prctl_module = prctl
        prctl_module_name = 'python-prctl'

def try_signalling_child_on_death(prctl_module, buf, child_signal):
    # in the parent process
    child_pid = os.fork()
    if not child_pid:
        # in the child process
        prctl_module.set_pdeathsig(child_signal)
        got_signal = threading.Event()
        def handle_signal(signum, frame):
            buf.seek(50, os.SEEK_SET)
            buf.write('%d\n' % signum)
            buf.flush()
            got_signal.set()
        signal.signal(child_signal, handle_signal)
        got_signal.wait(10)
        if got_signal.is_set():
            return
        sys.exit(5)
    else:
        buf.write('%d\n' % child_pid)
        buf.flush()
        time.sleep(2)
        sys.exit(3)

if __name__ == '__main__':
    if sys.argv[1] == 'run_parent':
        prctl_module_name, tmpfile, child_signal = sys.argv[2], sys.argv[3], sys.argv[4]
        if prctl_module_name == 'ctypes_prctl':
            import ctypes_prctl as prctl_module
        elif prctl_module_name == 'python-prctl':
            import prctl as prctl_module
        fd = os.open(tmpfile, os.O_RDWR)
        buf = mmap.mmap(fd, mmap.PAGESIZE, mmap.MAP_SHARED, mmap.PROT_WRITE)
        try:
            try_signalling_child_on_death(prctl_module, buf, int(child_signal))
        finally:
            os.close(fd)