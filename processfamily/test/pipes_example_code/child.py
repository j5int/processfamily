__author__ = 'Administrator'

import os
import sys

import msvcrt
import win32api
import win32con

# Get file descriptor from argument
ppid = int(sys.argv[1])
pipearg = int(sys.argv[2])

curproc = win32api.GetCurrentProcess()
parent_process = win32api.OpenProcess(win32con.PROCESS_DUP_HANDLE, 0, int(ppid))

in_file_handle = win32api.DuplicateHandle(
                       parent_process,
                       pipearg,
                       curproc,
                       0, #desiredAccess ignored because of DUPLICATE_SAME_ACCESS
                       0, #Inheritable
                       win32con.DUPLICATE_SAME_ACCESS | win32con.DUPLICATE_CLOSE_SOURCE)

pipeoutfd = msvcrt.open_osfhandle(int(in_file_handle), os.O_RDONLY)

# Read from pipe
# Note:  Could be done with os.read/os.close directly, instead of os.fdopen
pipeout = os.fdopen(pipeoutfd, 'r')
print pipeout.read()
pipeout.close()