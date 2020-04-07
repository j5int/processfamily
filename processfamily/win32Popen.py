from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

native_int = int

from future import standard_library
standard_library.install_aliases()
from builtins import str
from past.builtins import basestring
from builtins import *
from builtins import object
from future.utils import PY2
__author__ = 'matth'

from processfamily import _winprocess_ctypes
import subprocess
import os
import sys
import msvcrt
import win32api
import win32con
import win32event
import logging
import time

logger = logging.getLogger("processfamily.win32Popen")

# TODO Revert file to before futurize and only use these in Python 2

class HandlesOverCommandLinePopen(subprocess.Popen):
    """
    This class can be used to more closely match the behaviour
    on linux when the input and output streams are redirected, but you
    want close_fds to be True. (This is 'not supported' in the standard
    implementation.)

    This is achieved by passing the stream handles over the commandline
    and duplicating them manually in the child application.

    In order for this to work, you need to call
    'open_commandline_passed_stdio_streams()' from the child application.

    wait_for_child_stream_duplication_event is the number of seconds to wait for the child
    to duplicate the streams before returning from this method

    Relevant python docs:
    http://bugs.python.org/issue19764
    http://legacy.python.org/dev/peps/pep-0446/
    """

    def __init__(self, args,  bufsize=0, stdin=None, stdout=None, stderr=None,
                 universal_newlines=False, close_fds=False, timeout_for_child_stream_duplication_event=30, **kwargs):
        if not isinstance(bufsize, int):
            raise TypeError("bufsize must be an integer")

        self.commandline_passed = {}
        self._cleanup_on_terminate = []
        for s, p, m in [('stdin', stdin, 'w'), ('stdout', stdout, 'r'), ('stderr', stderr, 'r')]:
            if p is None:
                self.commandline_passed[s] = (None, 'null')

            elif p == subprocess.PIPE:

                if m == 'r':
                    mode = 'rU' if universal_newlines else 'rb'
                else:
                    mode = 'wb'

                piperead, pipewrite = os.pipe()
                myfile = os.fdopen(pipewrite if m == 'w' else piperead, mode, bufsize)
                childhandle = str(int(msvcrt.get_osfhandle(pipewrite if m == 'r' else piperead)))
                self._cleanup_on_terminate.append(pipewrite if m == 'r' else piperead)
                self.commandline_passed[s] = (myfile, childhandle, piperead, pipewrite)
            else:
                if isinstance(p, int):
                    childhandle = msvcrt.get_osfhandle(stdin)
                else:
                    # Assuming file-like object
                    childhandle = msvcrt.get_osfhandle(p.fileno())

                #The base implementation duplicates the handle, so we will too
                #It doesn't need to be inheritable for us, though
                cp = win32api.GetCurrentProcess()
                childhandle = win32api.DuplicateHandle(
                           cp,
                           childhandle,
                           cp,
                           0, #desiredAccess ignored because of DUPLICATE_SAME_ACCESS
                           0, #Inheritable
                           win32con.DUPLICATE_SAME_ACCESS)

                self.commandline_passed[s] = (None, str(int(childhandle)), childhandle, p)

        self._wait_for_child_duplication_event = win32event.CreateEvent(
            None,
            1,#bManualReset
            0,
            None)

        args += [str(os.getpid()),
                 str(int(self._wait_for_child_duplication_event)),
                 self.commandline_passed['stdin'][1],
                 self.commandline_passed['stdout'][1],
                 self.commandline_passed['stderr'][1],
                 ]

        super(HandlesOverCommandLinePopen, self).__init__(args, bufsize=bufsize,
                 stdin=None, stdout=None, stderr=None,
                 close_fds=close_fds, universal_newlines=universal_newlines, **kwargs)

        if timeout_for_child_stream_duplication_event:
            if not self.wait_for_child_stream_duplication_event(timeout_for_child_stream_duplication_event):
                logger.warning("Timed out waiting for child process to duplicate its io streams")

        self.stdin = self.commandline_passed['stdin'][0]
        self.stdout = self.commandline_passed['stdout'][0]
        self.stderr = self.commandline_passed['stderr'][0]

    def wait_for_child_stream_duplication_event(self, timeout):
        s = time.time()
        while time.time() - s < timeout:
            r = win32event.WaitForSingleObject(self._wait_for_child_duplication_event, 333)
            if r != win32event.WAIT_TIMEOUT:
                return True
            if self.poll() is not None:
                return True
        return False

    def poll(self, *args, **kwargs):
        return self._cleanup_on_returncode(super(HandlesOverCommandLinePopen, self).poll(*args, **kwargs))

    def wait(self, *args, **kwargs):
        return self._cleanup_on_returncode(super(HandlesOverCommandLinePopen, self).wait(*args, **kwargs))

    def _internal_poll(self, *args, **kwargs):
        return self._cleanup_on_returncode(super(HandlesOverCommandLinePopen, self)._internal_poll(*args, **kwargs))

    def _cleanup_on_returncode(self, r):
        if r is not None:
            while self._cleanup_on_terminate:
                c = self._cleanup_on_terminate.pop(-1)
                try:
                    os.close(c)
                except:
                    pass
        return r



class _ParentPassedFile(object):

    def __init__(self, f, win_file_handle):
        self.f = f
        self.win_file_handle = win_file_handle

    def __getattr__(self, item):
        return getattr(self.f, item)

def _open_parent_file_handle(parent_process_handle, parent_file_handle, mode='r'):
    if mode not in ['r', 'w']:
        raise ValueError("mode must be 'r' or 'w'")
    my_file_handle = win32api.DuplicateHandle(
                           parent_process_handle,
                           parent_file_handle,
                           win32api.GetCurrentProcess(),
                           0, #desiredAccess ignored because of DUPLICATE_SAME_ACCESS
                           0, #Inheritable
                           win32con.DUPLICATE_SAME_ACCESS | win32con.DUPLICATE_CLOSE_SOURCE)
    infd = msvcrt.open_osfhandle(int(my_file_handle), os.O_RDONLY if mode == 'r' else os.O_WRONLY)
    f = _ParentPassedFile(os.fdopen(infd, mode), my_file_handle)
    return f

def open_commandline_passed_stdio_streams(args=None):
    a = args or sys.argv

    if len(a) < 6:
        raise ValueError("Expected at least 6 arguments")

    a, ppid, event_handle_s, pipe_handles = a[:-5], a[-5], a[-4], a[-3:]
    parent_process = win32api.OpenProcess(win32con.PROCESS_DUP_HANDLE, 0, int(ppid))
    event_handle = win32api.DuplicateHandle(
                       parent_process,
                       int(event_handle_s),
                       win32api.GetCurrentProcess(),
                       0, #desiredAccess ignored because of DUPLICATE_SAME_ACCESS
                       0, #Inheritable
                       win32con.DUPLICATE_SAME_ACCESS)

    if pipe_handles[0] != 'null':
        sys.stdin = _open_parent_file_handle(parent_process, int(pipe_handles[0]), 'r')
    if pipe_handles[1] != 'null':
        sys.stdout = _open_parent_file_handle(parent_process, int(pipe_handles[1]), 'w')
    if pipe_handles[2] != 'null':
        sys.stderr = _open_parent_file_handle(parent_process, int(pipe_handles[2]), 'w')

    if args is None:
        sys.argv = a

    win32event.SetEvent(event_handle)

if PY2:
    class ProcThreadAttributeHandleListPopen(subprocess.Popen):
        """
        Uses the STARTUPINFOEX struct to pass through an explicit list of
        handles to inherit. This is used to more closely match the behaviour
        on linux when the input and output streams are redirected, but you
        want close_fds to be True. (This is 'not supported' in the standard
        implementation.)

        Please note that this functionality requires Windows version > XP/2003.

        Relevant python docs:
        http://bugs.python.org/issue19764
        http://legacy.python.org/dev/peps/pep-0446/
        """

        def __init__(self, args, stdin=None, stdout=None, stderr=None, close_fds=False, shell=False, **kwargs):
            self.__really_close_fds = close_fds
            if close_fds and (stdin is not None or stdout is not None or stderr is not None):
                if not _winprocess_ctypes.CAN_USE_EXTENDED_STARTUPINFO:
                    raise ValueError("close_fds is not supported on Windows "
                                     "platforms XP/2003 and below, if you redirect stdin/stdout/stderr")
                if shell:
                    raise ValueError("close_fds is not supported on Windows "
                                     "if you redirect stdin/stdout/stderr, and use shell=True")
                self.__really_close_fds = True
                close_fds = False

            super(ProcThreadAttributeHandleListPopen, self).__init__(
                args, stdin=stdin, stdout=stdout, stderr=stderr, close_fds=close_fds, shell=shell, **kwargs)


        # This Source Code Form is subject to the terms of the Mozilla Public
        # License, v. 2.0. If a copy of the MPL was not distributed with this file,
        # You can obtain one at http://mozilla.org/MPL/2.0/.
        #
        # This snippet is a modified method taken from : https://hg.mozilla.org/mozilla-central/raw-file/0753f7b93ab7/testing/mozbase/mozprocess/mozprocess/processhandler.py
        def _execute_child(self, *args_tuple):
            if sys.hexversion < 0x02070600: # prior to 2.7.6
                (args, executable, preexec_fn, close_fds,
                 cwd, env, universal_newlines, input_startupinfo,
                 creationflags, shell,
                 p2cread, p2cwrite,
                 c2pread, c2pwrite,
                 errread, errwrite) = args_tuple
                to_close = None
            elif sys.hexversion > 0x03040000: # 3.4.0 and later
                (args, executable, preexec_fn, close_fds,
                                    pass_fds, cwd, env,
                                    input_startupinfo, creationflags, shell,
                                    p2cread, p2cwrite,
                                    c2pread, c2pwrite,
                                    errread, errwrite,
                                    restore_signals, start_new_session) = args_tuple
                to_close = set()
                to_close.add(p2cread)
                if p2cwrite is not None:
                    to_close.add(p2cwrite)
                to_close.add(c2pwrite)
                if c2pread is not None:
                    to_close.add(c2pread)
                to_close.add(errwrite)
                if errread is not None:
                    to_close.add(errread)
            else: # 2.7.6 and later
                (args, executable, preexec_fn, close_fds,
                 cwd, env, universal_newlines, input_startupinfo,
                 creationflags, shell, to_close,
                 p2cread, p2cwrite,
                 c2pread, c2pwrite,
                 errread, errwrite) = args_tuple

            if shell:
                return super(ProcThreadAttributeHandleListPopen, self)._execute_child(*args_tuple)

            close_fds = self.__really_close_fds

            if not isinstance(args, basestring):
                args = subprocess.list2cmdline(args)

            if _winprocess_ctypes.CAN_USE_EXTENDED_STARTUPINFO:
                attribute_list_data = ()
                startupinfoex           = _winprocess_ctypes.STARTUPINFOEX()
                startupinfo             = startupinfoex.StartupInfo
                startupinfo.cb          = _winprocess_ctypes.sizeof(_winprocess_ctypes.STARTUPINFOEX)
                startupinfo_argument = startupinfoex
            else:
                startupinfo = _winprocess_ctypes.STARTUPINFO()
                startupinfo_argument = startupinfo

            if input_startupinfo is not None:
                startupinfo.dwFlags = input_startupinfo.dwFlags
                startupinfo.hStdInput = input_startupinfo.hStdInput
                startupinfo.hStdOutput = input_startupinfo.hStdOutput
                startupinfo.hStdError = input_startupinfo.hStdError
                startupinfo.wShowWindow = input_startupinfo.wShowWindow

            inherit_handles = 0 if close_fds else 1

            if None not in (p2cread, c2pwrite, errwrite):
                if close_fds:
                    HandleArray = _winprocess_ctypes.HANDLE * 3
                    # PY2COMPAT new_int doesn't seem to know how to convert file handles to int.
                    # So we use the "native_int" instead.
                    handles_to_inherit = HandleArray(native_int(p2cread), native_int(c2pwrite), native_int(errwrite))

                    attribute_list_data = (
                        (
                            _winprocess_ctypes.PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
                            handles_to_inherit
                        ),
                    )
                    inherit_handles = 1

                startupinfo.dwFlags |= _winprocess_ctypes.STARTF_USESTDHANDLES
                # PY2COMPAT new_int doesn't seem to know how to convert file handles to int.
                # So we use the "native_int" instead.
                startupinfo.hStdInput = native_int(p2cread)
                startupinfo.hStdOutput = native_int(c2pwrite)
                startupinfo.hStdError = native_int(errwrite)

            if _winprocess_ctypes.CAN_USE_EXTENDED_STARTUPINFO:
                attribute_list = _winprocess_ctypes.ProcThreadAttributeList(attribute_list_data)
                startupinfoex.lpAttributeList = attribute_list.value
                creationflags |= _winprocess_ctypes.EXTENDED_STARTUPINFO_PRESENT

            def _close_in_parent(fd):
                fd.Close()
                if to_close:
                    to_close.remove(fd)

            # create the process
            try:
                hp, ht, pid, tid = _winprocess_ctypes.ExtendedCreateProcess(
                    executable, args,
                    None, None, # No special security
                    inherit_handles, #Inherit handles
                    creationflags,
                    _winprocess_ctypes.EnvironmentBlock(env) if env else None,
                    cwd,
                    startupinfo_argument)
            finally:
                # Child is launched. Close the parent's copy of those pipe
                # handles that only the child should have open.  You need
                # to make sure that no handles to the write end of the
                # output pipe are maintained in this process or else the
                # pipe will not close when the child process exits and the
                # ReadFile will hang.
                if p2cread is not None:
                    _close_in_parent(p2cread)
                if c2pwrite is not None:
                    _close_in_parent(c2pwrite)
                if errwrite is not None:
                    _close_in_parent(errwrite)

            self._child_created = True
            self._handle = subprocess.Handle(hp) if hasattr(subprocess, 'Handle') else hp
            self._thread = ht
            self.pid = pid
            self.tid = tid

            ht.Close()
else:
    # On Python 3.7 closefds with redirection works on windows, so we don't need to change anything.
    # I'm not sure if this is true for early versions of Python 3
    class ProcThreadAttributeHandleListPopen(subprocess.Popen):
        pass