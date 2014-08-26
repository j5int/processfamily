__author__ = 'matth'

import os
import sys

if sys.platform.startswith("win"):
    import win32api
    import win32con
    import win32process
    import pywintypes
    import winerror
else:
    import multiprocessing
    import signal

class AccessDeniedError(Exception):
    pass

if sys.platform.startswith("win"):

    #PROCESS_QUERY_LIMITED_INFORMATION is not available on WinXP / 2003:
    USE_PROCESS_QUERY_LIMITED_INFORMATION = sys.getwindowsversion().major > 5
    PROCESS_QUERY_LIMITED_INFORMATION = 4096

    def process_exists(pid):
        try:
            if USE_PROCESS_QUERY_LIMITED_INFORMATION:
                #this one potentially works even for other user's processes
                h = win32api.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
            else:
                h = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION, 0, pid)
        except pywintypes.error as e:
            if e.winerror == winerror.ERROR_INVALID_PARAMETER:
                #This error is returned if the pid doesn't match any known process
                return False
            elif e.winerror == winerror.ERROR_ACCESS_DENIED:
                raise AccessDeniedError(e)
            #Other errors are not expected
            raise
        try:
            exitcode = win32process.GetExitCodeProcess(h)
            return exitcode == win32con.STILL_ACTIVE
        finally:
            win32api.CloseHandle(h)

else:

    def process_exists(pid):
        try:
            os.kill(pid, 0)
            return True
        except OSError as e:
            return False


if sys.platform.startswith("win"):

    def kill_process(pid):
        try:
            h = win32api.OpenProcess(win32con.PROCESS_TERMINATE, 0, pid)
        except pywintypes.error as e:
            if e.winerror == winerror.ERROR_INVALID_PARAMETER:
                #This error is returned if the pid doesn't match any known process
                return
            elif e.winerror == winerror.ERROR_ACCESS_DENIED:
                raise AccessDeniedError(e)
            #Other errors are not expected
            raise
        try:
            win32api.TerminateProcess(h, -1)
        finally:
            win32api.CloseHandle(h)
else:

    def kill_process(pid):
        os.kill(pid, signal.SIGKILL)

if sys.platform.startswith("win"):

    def cpu_count():
        #The multiprocessing cpu_count implementation is flaky on windows - so we do it the official windows way
        # (it looks for an environment variable that may not be there)
        (wProcessorArchitecture,
            dwPageSize,
            lpMinimumApplicationAddress,
            lpMaximumApplicationAddress,
            dwActiveProcessorMask,
            dwNumberOfProcessors,
            dwProcessorType,
            dwAllocationGranularity,
            (wProcessorLevel,wProcessorRevision)) = win32api.GetSystemInfo()
        return dwNumberOfProcessors

else:

    def cpu_count():
        return multiprocessing.cpu_count()