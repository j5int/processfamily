# -*- coding: utf-8 -*-

"""Utilities for controlling other threads (usually stopping them!)"""

import threading
import time
import logging
try:
    from j5.OS import ThreadRaise
except ImportError:
    # this requires ctypes so might not be available
    ThreadRaise = None

def get_thread_callstr(thread):
    """returns a string indicating how the given thread was called"""
    try:
        thread_args = thread._Thread__args
        thread_kwargs = thread._Thread__kwargs
        thread_target = thread._Thread__target
        callargs = ", ".join([repr(arg) for arg in thread_args] + ["%s=%r" % (name, value) for name, value in thread_kwargs.items()])
        return "%s was called with %s(%s)" % (thread.getName(), thread_target.__name__, callargs)
    except Exception, e:
        return "Could not calculate thread arguments for thread (error %s)" % e

def graceful_stop_thread(thread, thread_wait=0.5):
    """try to stop the given thread gracefully if it is still alive. Returns success"""
    if thread.isAlive():
        if ThreadRaise is not None:
            # this attempts to raise an exception in the thread; the sleep allows the switch or natural end of the thread
            ThreadRaise.thread_async_raise(thread, SystemExit)
        time.sleep(thread_wait)
    if thread.isAlive():
        return False
    else:
        logging.info("Thread %s stopped gracefully" % thread.getName())
        return True

def forceful_stop_thread(thread):
    """stops the given thread forcefully if it is alive"""
    if thread.isAlive():
        logging.warning("Stopping thread %s forcefully" % thread.getName())
        try:
            thread._Thread__stop()
        except Exception, e:
            logging.warning("Error stopping thread %s: %s" % (thread.getName(), e))
    return not thread.isAlive()

def stop_thread(thread, thread_wait=1.0):
    """stops the given thread if it is still alive - first gently, then forcefully if it does not respond to an exception raise within thread_wait seconds"""
    if graceful_stop_thread(thread, thread_wait):
        return True
    else:
        return forceful_stop_thread(thread)

def stop_threads(global_wait=2.0, thread_wait=1.0):
    """enumerates remaining threads and stops them"""
    current_thread = threading.currentThread()
    remaining_threads = [thread for thread in threading.enumerate() if thread != current_thread and thread.isAlive()]
    threads_to_stop = []
    for thread in remaining_threads:
        thread_name = thread.getName()
        callstr = get_thread_callstr(thread)
        logging.warning("Shutting down but thread %s still remains alive; %s" % (thread_name, callstr))
        threads_to_stop.append(thread)
    if not threads_to_stop:
        return
    time.sleep(global_wait)
    threads_to_stop2 = []
    for thread in threads_to_stop:
        if not graceful_stop_thread(thread, thread_wait):
            threads_to_stop2.append(thread)
    for thread in threads_to_stop2:
        forceful_stop_thread(thread)
    unstoppable_thread_names = [thread.getName() for thread in threading.enumerate() if thread != current_thread and thread.isAlive()]
    if unstoppable_thread_names:
        logging.error("The following threads could not be stopped: %s" % ", ".join(unstoppable_thread_names))

