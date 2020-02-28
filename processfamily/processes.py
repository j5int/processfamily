from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from future import standard_library
standard_library.install_aliases()
from builtins import str
from builtins import *
__author__ = 'matth'

import os
import sys
import logging
from processfamily import affinity

if sys.platform.startswith("win"):
    import win32api
    import win32con
    import win32process
    import pywintypes
    import winerror
else:
    import multiprocessing
    import signal

logger = logging.getLogger("processfamily.processes")

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



def get_process_affinity(pid=None):
    """Gets the process_affinity cores either for the current process or the given pid. Returns a list of cores"""
    try:
        return affinity.sched_getaffinity(pid or 0)
    except NotImplementedError:
        return {}

def set_process_affinity(mask, pid=None):
    """Sets the process_affinity to the given cores, either for the current process or the given pid. mask can be an affinity mask or list of cores. Returns success"""
    pid = pid or 0
    request_mask_str = ", ".join(str(i) for i in mask)
    try:
        affinity.sched_setaffinity(pid, mask)
        current_mask = affinity.sched_getaffinity(pid)
    except NotImplementedError:
        logger.warning("Set process affinity for pid %d to cores %s unsuccessful: Not implemented", pid, request_mask_str)
        return False
    current_mask_str = ", ".join(str(i) for i in current_mask)
    if current_mask != set(mask):
        logger.warning("Set process affinity for pid %d to cores %s unsuccessful: actually set to %s", pid, request_mask_str, current_mask_str)
        return False
    else:
        logger.info("Set process affinity for pid %d to cores %s", pid, current_mask_str)
        return True