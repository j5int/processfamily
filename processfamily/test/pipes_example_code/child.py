__author__ = 'Administrator'

import os
import sys

import msvcrt
import _subprocess
import win32api
import win32con

# Get file descriptor from argument
ppid = int(sys.argv[1])
pipearg = int(sys.argv[2])

curproc = _subprocess.GetCurrentProcess()
parent_process = win32api.OpenProcess(win32con.PROCESS_DUP_HANDLE, 0, int(ppid))

pipeoutih = _subprocess.DuplicateHandle(parent_process, pipearg, curproc, 0, 1,
        _subprocess.DUPLICATE_SAME_ACCESS)
pipeoutfd = msvcrt.open_osfhandle(int(pipeoutih), os.O_RDONLY)

# Read from pipe
# Note:  Could be done with os.read/os.close directly, instead of os.fdopen
pipeout = os.fdopen(pipeoutfd, 'r')
print pipeout.read()
pipeout.close()