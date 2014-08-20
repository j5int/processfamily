__author__ = 'matth'

import os
import sys

if sys.platform.startswith("win"):
    import win32api
    import win32con
    import win32process
    import pywintypes

    def process_exists(pid):
        try:
            h = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION, 0, pid)
        except pywintypes.error:
            return False
        try:
            exitcode = win32process.GetExitCodeProcess(h)
            return exitcode == win32con.STILL_ACTIVE
        finally:
            win32api.CloseHandle(h)

    def kill_process(pid):
        if hasattr(os, "kill"):
            #Python 2.7 and later has this
            os.kill(pid, -1)
        else:
            try:
                h = win32api.OpenProcess(win32con.PROCESS_TERMINATE, 0, pid)
            except pywintypes.error:
                return
            try:
                win32api.TerminateProcess(h, -1)
            finally:
                win32api.CloseHandle(h)
else:
    import signal

    def process_exists(pid):
        try:
            os.kill(pid, 0)
            return True
        except OSError as e:
            return False

    def kill_process(pid):
        os.kill(pid, signal.SIGHUP)
