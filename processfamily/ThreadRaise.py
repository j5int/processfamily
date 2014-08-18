"""raises exceptions in other Python threads asynchronously using ctypes and PyThreadState_SetAsyncExc

NB this is dangerous and should only be used during shutdown; it's possible to get locks etc in unsavoury states through using this code"""

# from http://sebulba.wikispaces.com/recipe+thread2

from processfamily.threads import get_thread_id, thread_async_raise
from j5.OS import ThreadMonitor


class Thread(ThreadMonitor.MonitoredThread):
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

