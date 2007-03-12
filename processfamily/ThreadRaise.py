"""raises exceptions in other Python threads asynchronously using ctypes and PyThreadState_SetAsyncExc"""

# from http://sebulba.wikispaces.com/recipe+thread2

import threading
import ctypes
 
def thread_async_raise(thread, exctype):
    """raises the exception, performs cleanup if needed"""
    # if not inspect.isclass(exctype):
    #     raise TypeError("Only types can be raised (not instances)")
    if isinstance(thread, threading.Thread):
        tid = get_thread_id(thread)
    else:
        tid = thread
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, ctypes.py_object(exctype))
    if res == 0:
        raise ValueError("invalid thread id")
    elif res != 1:
        # """if it returns a number greater than one, you're in trouble, 
        # and you should call it again with exc=NULL to revert the effect"""
        ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, 0)
        raise SystemError("PyThreadState_SetAsyncExc failed")
 
def get_thread_id(thread):
    if not thread.isAlive():
        raise threading.ThreadError("the thread is not active")
    # do we have it cached?
    if hasattr(thread, "_thread_id"):
        return thread._thread_id
    # no, look for it in the _active dict
    for tid, tobj in threading._active.items():
        if tobj is thread:
            thread._thread_id = tid
            return tid
    raise AssertionError("could not determine the thread's id")

class Thread(threading.Thread):
    def _get_my_tid(self):
        """determines this (self's) thread id"""
        return get_thread_id(self)

    def raise_exc(self, exctype):
        """raises the given exception type in the context of this thread"""
        thread_async_raise(self._get_my_tid(), exctype)

    def terminate(self):
        """raises SystemExit in the context of the given thread, which should 
        cause the thread to exit silently (unless caught)"""
        self.raise_exc(SystemExit)

