from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from future import standard_library
standard_library.install_aliases()
from builtins import *

import os
import sys

if hasattr(os, 'sched_setaffinity'):
    sched_setaffinity = os.sched_setaffinity
    sched_getaffinity = os.sched_getaffinity
elif sys.platform.startswith("win"):
    # Use win32process from pywin32
    import win32api
    import win32con
    import win32process

    def _cores_to_mask(cores):
        mask = 0
        for core in cores:
            mask |= 1 << core
        return mask


    def _mask_to_cores(mask):
        """converts a mask to a list of cores"""
        cores = set()
        i = 0
        while mask:
            if mask % 2:
                cores.add(i)
            mask >>= 1
            i += 1
        return cores

    def sched_getaffinity(pid):
        pid = pid or os.getpid()
        handle = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION, False, pid)
        return _mask_to_cores(win32process.GetProcessAffinityMask(handle)[0])

    def sched_setaffinity(pid, mask):
        pid = pid or os.getpid()
        handle = win32api.OpenProcess(win32con.PROCESS_SET_INFORMATION, False, pid)
        win32process.SetProcessAffinityMask(handle, _cores_to_mask(mask))
else:
    def sched_setaffinity(*args, **kwargs):
        raise NotImplementedError()
    def sched_getaffinity(*args, **kwargs):
        raise NotImplementedError()