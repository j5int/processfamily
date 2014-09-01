__author__ = 'matth'

from processfamily import _winprocess_ctypes
import subprocess
import os
import sys
import msvcrt

DEVNULL = -3

class HandlesOverCommandLinePopen(subprocess.Popen):
    """
    This class can be used to more closely match the behaviour
    on linux when the input and output streams are redirected, but you
    want close_fds to be True. (This is 'not supported' in the standard
    implementation.)

    This is achieved by passing the stream handles over the commandline
    and duplicating them manually in the child application.

    Relevant python docs:
    http://bugs.python.org/issue19764
    http://legacy.python.org/dev/peps/pep-0446/
    """

    def __init__(self, args,  bufsize=0, stdin=None, stdout=None, stderr=None,
                 universal_newlines=False, close_fds=False, **kwargs):
        if not isinstance(bufsize, (int, long)):
            raise TypeError("bufsize must be an integer")

        #must be all or nothing for now
        for p in [stdin, stdout, stderr]:
            if p not in [DEVNULL, subprocess.PIPE]:
                raise ValueError("Only PIPE or DEVNULL is supported if pass_handles_over_commandline is True")

        self.commandline_passed = {}
        for s, p, m in [('stdin', stdin, 'w'), ('stdout', stdout, 'r'), ('stderr', stderr, 'r')]:
            if p == subprocess.PIPE:

                if m == 'r':
                    mode = 'rU' if universal_newlines else 'rb'
                else:
                    mode = 'wb'

                piperead, pipewrite = os.pipe()
                myfile = os.fdopen(pipewrite if m == 'w' else piperead, mode, bufsize)
                childhandle = str(int(msvcrt.get_osfhandle(pipewrite if m == 'r' else piperead)))
                self.commandline_passed[s] = (myfile, childhandle, piperead, pipewrite)
            else:
                childhandle = str(int(msvcrt.get_osfhandle(open(os.devnull, m))))
                self.commandline_passed[s] = (None, childhandle)

        args += [str(os.getpid()),
                 self.commandline_passed['stdin'][1],
                 self.commandline_passed['stdout'][1],
                 self.commandline_passed['stderr'][1],
                 ]

        super(HandlesOverCommandLinePopen, self).__init__(args, bufsize=bufsize,
                 stdin=None, stdout=None, stderr=None,
                 close_fds=close_fds, universal_newlines=universal_newlines, **kwargs)

        self.stdin = self.commandline_passed['stdin'][0]
        self.stdout = self.commandline_passed['stdout'][0]
        self.stderr = self.commandline_passed['stderr'][0]


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

    def __init__(self, args, stdin=None, stdout=None, stderr=None, close_fds=False, **kwargs):
        self.__really_close_fds = close_fds
        if close_fds and (stdin is not None or stdout is not None or stderr is not None):
            if not _winprocess_ctypes.CAN_USE_EXTENDED_STARTUPINFO:
                raise ValueError("close_fds is not supported on Windows "
                                 "platforms XP/2003 and below, if you redirect stdin/stdout/stderr")
            self.__really_close_fds = True
            close_fds = False

        super(ProcThreadAttributeHandleListPopen, self).__init__(
            args, stdin=stdin, stdout=stdout, stderr=stderr, close_fds=close_fds, **kwargs)


    # This Source Code Form is subject to the terms of the Mozilla Public
    # License, v. 2.0. If a copy of the MPL was not distributed with this file,
    # You can obtain one at http://mozilla.org/MPL/2.0/.
    #
    # This snippet is a modified method taken from : https://hg.mozilla.org/mozilla-central/raw-file/0753f7b93ab7/testing/mozbase/mozprocess/mozprocess/processhandler.py
    def _execute_child(self, *args_tuple):
        if sys.hexversion < 0x02070600: # prior to 2.7.6
            (args, executable, preexec_fn, close_fds,
             cwd, env, universal_newlines, startupinfo,
             creationflags, shell,
             p2cread, p2cwrite,
             c2pread, c2pwrite,
             errread, errwrite) = args_tuple
            to_close = None
        else: # 2.7.6 and later
            (args, executable, preexec_fn, close_fds,
             cwd, env, universal_newlines, startupinfo,
             creationflags, shell, to_close,
             p2cread, p2cwrite,
             c2pread, c2pwrite,
             errread, errwrite) = args_tuple

        close_fds = self.__really_close_fds

        # Always or in the create new process group
        creationflags |= _winprocess_ctypes.CREATE_NEW_PROCESS_GROUP

        if _winprocess_ctypes.CAN_USE_EXTENDED_STARTUPINFO:
            attribute_list_data = ()
            startupinfoex           = _winprocess_ctypes.STARTUPINFOEX()
            startupinfo             = startupinfoex.StartupInfo
            startupinfo.cb          = _winprocess_ctypes.sizeof(_winprocess_ctypes.STARTUPINFOEX)
            startupinfo_argument = startupinfoex
        else:
            startupinfo = _winprocess_ctypes.STARTUPINFO()
            startupinfo_argument = startupinfo
        inherit_handles = 0 if close_fds else 1

        if None not in (p2cread, c2pwrite, errwrite):
            if close_fds:
                HandleArray = _winprocess_ctypes.HANDLE * 3
                handles_to_inherit = HandleArray(int(p2cread), int(c2pwrite), int(errwrite))

                attribute_list_data = (
                    (
                        _winprocess_ctypes.PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
                        handles_to_inherit
                    ),
                )
                inherit_handles = 1

            startupinfo.dwFlags |= _winprocess_ctypes.STARTF_USESTDHANDLES
            startupinfo.hStdInput = int(p2cread)
            startupinfo.hStdOutput = int(c2pwrite)
            startupinfo.hStdError = int(errwrite)

        if _winprocess_ctypes.CAN_USE_EXTENDED_STARTUPINFO:
            attribute_list = _winprocess_ctypes.ProcThreadAttributeList(attribute_list_data)
            startupinfoex.lpAttributeList = attribute_list.value
            creationflags |= _winprocess_ctypes.EXTENDED_STARTUPINFO_PRESENT

        if shell:
            raise NotImplementedError()

        def _close_in_parent(fd):
            fd.Close()
            if to_close:
                to_close.remove(fd)

        # set process creation flags
        if env:
            creationflags |= _winprocess_ctypes.CREATE_UNICODE_ENVIRONMENT

        if not isinstance(args, basestring):
            args = subprocess.list2cmdline(args)

        # create the process
        try:
            hp, ht, pid, tid = _winprocess_ctypes.CreateProcess(
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
        self._handle = hp
        self._thread = ht
        self.pid = pid
        self.tid = tid

        ht.Close()
