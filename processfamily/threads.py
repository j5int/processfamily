# -*- coding: utf-8 -*-

"""Utilities for controlling other threads (usually stopping them!)

NB this is dangerous and should only be used during shutdown; it's possible to get locks etc in unsavoury states through using this code"""

from j5.OS import ThreadMonitor

from j5.Logging import Errors
import threading
import time
import traceback
import logging
try:
    from j5.OS import ThreadRaise
except ImportError:
    # this requires ctypes so might not be available
    ThreadRaise = None
try:
    from j5.OS import ThreadDebug
except ImportError as thread_debug_error:
    ThreadDebug = None

logger = logging.getLogger("j5.OS.ThreadControl")

def get_thread_callstr(thread):
    """returns a string indicating how the given thread was called"""
    try:
        thread_args = thread._Thread__args
        thread_kwargs = thread._Thread__kwargs
        thread_target = thread._Thread__target
        if thread_target:
            thread_name = thread_target.__name__
        else:
            thread_name = "%s.%s" % (thread.__class__.__module__, thread.__class__.__name__)
        callargs = ", ".join([repr(arg) for arg in thread_args] + ["%s=%r" % (name, value) for name, value in thread_kwargs.items()])
        return "%s was called with %s(%s)" % (thread.getName(), thread_name, callargs)
    except Exception as e:
        return "Could not calculate thread arguments for thread (error %s)" % e

def graceful_stop_thread(thread, thread_wait=0.5):
    """try to stop the given thread gracefully if it is still alive. Returns success"""
    if thread.isAlive():
        if ThreadRaise is not None:
            # this attempts to raise an exception in the thread; the sleep allows the switch or natural end of the thread
            try:
                ThreadRaise.thread_async_raise(thread, SystemExit)
            except Exception as e:
                logger.info("Error trying to raise exit message in thread %s:\n%s", thread.getName(), Errors.traceback_str())
        time.sleep(thread_wait)
    if thread.isAlive():
        return False
    else:
        logger.info("Thread %s stopped gracefully", thread.getName())
        return True

def forceful_stop_thread(thread):
    """stops the given thread forcefully if it is alive"""
    if thread.isAlive():
        logger.warning("Stopping thread %s forcefully", thread.getName())
        try:
            thread._Thread__stop()
        except Exception as e:
            logger.warning("Error stopping thread %s: %s", thread.getName(), e)
    return not thread.isAlive()

def stop_thread(thread, thread_wait=1.0):
    """stops the given thread if it is still alive - first gently, then forcefully if it does not respond to an exception raise within thread_wait seconds"""
    if graceful_stop_thread(thread, thread_wait):
        return True
    else:
        return forceful_stop_thread(thread)

def filter_threads(threads, current_thread=None, exclude_threads=None):
    """filters the threads to exclude the current thread (which can be given as a speedup) and other threads if given"""
    if exclude_threads is None:
        exclude_threads = []
    remaining_threads = threads[:]
    if current_thread is None:
        current_thread = threading.currentThread()
    if current_thread in remaining_threads:
        remaining_threads.remove(current_thread)
    for exclude_thread in exclude_threads:
        if exclude_thread in remaining_threads:
            remaining_threads.remove(exclude_thread)
    return remaining_threads

def log_thread_tracebacks(threads, stop_event=None, finished_event=None, loglevel=logging.INFO):
    """Logs tracebacks for the given threads"""
    logger.log(loglevel, "Preparing to shut down %d threads; generating tracebacks", len(threads))
    for (thread, frame) in ThreadDebug.find_thread_frames():
        if thread in threads:
            logger.log(loglevel, "Preparing to shut down thread %r", thread)
            logger.log(loglevel, "".join(traceback.format_stack(frame)))
            if stop_event and stop_event.is_set():
                logger.log(loglevel, "Told to stop tracebacks; aborting")
                break
    else:
        logger.log(loglevel, "Completed generating tracebacks")
    if finished_event:
        finished_event.set()

def stop_threads(global_wait=2.0, thread_wait=1.0, exclude_threads=None, log_tracebacks=True):
    """enumerates remaining threads and stops them"""
    current_thread = threading.currentThread()
    def find_stop_threads():
        return [t for t in filter_threads(threading._active.values(), current_thread, exclude_threads) if t.isAlive()]
    remaining_threads = find_stop_threads()
    threads_to_stop = []
    for thread in remaining_threads:
        thread_name = thread.getName()
        callstr = get_thread_callstr(thread)
        logger.warning("Shutting down but thread still remains alive: %s", callstr)
        threads_to_stop.append(thread)
    if not threads_to_stop:
        return
    traceback_stop_event = threading.Event()
    traceback_finished_event = threading.Event()
    if log_tracebacks and not ThreadDebug:
        logger.warning("Cannot log tracebacks as ThreadDebug could not be imported: %s", thread_debug_error)
        log_tracebacks = False
    if log_tracebacks:
        traceback_thread = ThreadMonitor.MonitoredThread(target=log_thread_tracebacks, name="stop_thread_tracebacks", args=(threads_to_stop, traceback_stop_event, traceback_finished_event))
        traceback_thread.start()
        # wait for the tracebacks to stop, and give them a chance to abort if they take too long
        logger.info("Started traceback thread")
        traceback_finished_event.wait(global_wait)
        traceback_stop_event.set()
        traceback_finished_event.wait(global_wait)
        logger.info("Finished waiting for traceback thread")
    threads_to_stop2 = []
    try:
        time.sleep(global_wait)
        for thread in threads_to_stop:
            if not graceful_stop_thread(thread, thread_wait):
                threads_to_stop2.append(thread)
    except KeyboardInterrupt as e:
        logger.warning("Keyboard Interrupt received while waiting for thread; abandoning civility and forcing them all to stop")
        threads_to_stop2 = find_stop_threads()
    for thread in threads_to_stop2:
        forceful_stop_thread(thread)
    last_sleep = time.time() + global_wait
    while find_stop_threads() and time.time() < last_sleep:
        # give them half a chance to stop
        time.sleep(thread_wait/5)
    unstoppable_thread_names = [thread.getName() for thread in find_stop_threads()]
    if unstoppable_thread_names:
        logger.error("The following threads could not be stopped: %s", ", ".join(unstoppable_thread_names))

