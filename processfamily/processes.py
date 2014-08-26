__author__ = 'matth'

import os
import sys
import logging
import affinity

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


def _affinity_mask_to_list(mask):
    """converts a mask to a list of cores"""
    cores = []
    i = 0
    while mask:
        if mask % 2:
            cores.append(i)
        mask >>= 1
        i += 1
    return cores

def _create_affinity_mask(mask_or_list):
    """converts a list of cores to a mask if necessary"""
    if isinstance(mask_or_list, int):
        return mask_or_list
    cores = mask_or_list
    mask = 0
    for core in cores:
        mask |= 1 << core
    return mask

def get_processor_affinity(pid=None):
    """Gets the process_affinity cores either for the current process or the given pid. Returns a list of cores"""
    mask = affinity.get_process_affinity_mask(pid or 0)
    return _affinity_mask_to_list(mask)

def set_processor_affinity(mask, pid=None):
    """Sets the process_affinity to the given cores, either for the current process or the given pid. mask can be an affinity mask or list of cores. Returns success"""
    mask = _create_affinity_mask(mask)
    pid = pid or 0
    previous_mask = affinity.set_process_affinity_mask(pid, mask)
    current_mask = affinity.get_process_affinity_mask(pid)
    current_mask_str = ", ".join(str(i) for i in _affinity_mask_to_list(current_mask))
    if current_mask != mask:
        request_mask_str = ", ".join(str(i) for i in _affinity_mask_to_list(mask))
        logger.warning("Set process affinity for pid %d to cores %s unsuccessful: actually set to %s", pid, request_mask_str, current_mask_str)
        return False
    else:
        logger.info("Set process affinity for pid %d to cores %s", pid, current_mask_str)
        return True