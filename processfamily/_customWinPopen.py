# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# It is a snippet taken from : https://hg.mozilla.org/mozilla-central/raw-file/0753f7b93ab7/testing/mozbase/mozprocess/mozprocess/processhandler.py

__author__ = 'matth'

from processfamily import _winprocess_ctypes
import subprocess
import os
import sys


#Relevant python docs:
# http://bugs.python.org/issue19764
# http://legacy.python.org/dev/peps/pep-0446/

class WinPopen(subprocess.Popen):

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
        if not isinstance(args, basestring):
            args = subprocess.list2cmdline(args)

        # Always or in the create new process group
        creationflags |= _winprocess_ctypes.CREATE_NEW_PROCESS_GROUP

        AttributeListData = ()
        StartupInfoEx           = _winprocess_ctypes.STARTUPINFOEX()
        startupinfo             = StartupInfoEx.StartupInfo
        startupinfo.cb          = _winprocess_ctypes.sizeof(_winprocess_ctypes.STARTUPINFOEX)

        if None not in (p2cread, c2pwrite, errwrite):
            HandleArray = _winprocess_ctypes.HANDLE * 3
            handles_to_inherit = HandleArray(int(p2cread), int(c2pwrite), int(errwrite))

            AttributeListData = (
                (
                    _winprocess_ctypes.PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
                    handles_to_inherit
                ),
            )

            startupinfo.dwFlags |= _winprocess_ctypes.STARTF_USESTDHANDLES
            startupinfo.hStdInput = int(p2cread)
            startupinfo.hStdOutput = int(c2pwrite)
            startupinfo.hStdError = int(errwrite)

        AttributeList = _winprocess_ctypes.ProcThreadAttributeList(AttributeListData)
        StartupInfoEx.lpAttributeList = AttributeList.value
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

        # create the process
        try:
            hp, ht, pid, tid = _winprocess_ctypes.CreateProcess(
                executable, args,
                None, None, # No special security
                0 if close_fds else 1,
                creationflags,
                _winprocess_ctypes.EnvironmentBlock(env) if env else None,
                cwd,
                StartupInfoEx)
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