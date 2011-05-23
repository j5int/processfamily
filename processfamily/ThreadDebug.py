#!/usr/bin/env python

"""Module to help with debugging errors by looking up things on the gc stack"""

import gc
import logging
import threading
from j5.OS import ThreadControl
# TODO: investigate what would happen when not using cherrypy
from cherrypy import wsgiserver

def find_thread(thread):
    """Looks up a thread by thread number and returns the thread object"""
    if isinstance(thread, int):
        for t in threading.enumerate():
            if t.ident == thread:
                return t
        else:
            raise ValueError("Could not find thread %s" % thread)
    return thread

GRACEFUL, FORCEFUL, INCREASING = range(3)

STOP_THREAD_METHODS = {GRACEFUL: ThreadControl.graceful_stop_thread, FORCEFUL: ThreadControl.forceful_stop_thread, INCREASING: ThreadControl.stop_thread}

def shutdown_thread(thread, force=INCREASING, loglevel=logging.DEBUG):
    """Shuts the given thread (given by Thread object or ident) down, with logging set to the given loglevel, and returns success"""
    thread = find_thread(thread)
    lines = []
    logger = logging.getLogger()
    previous_loglevel = logger.level
    logger.setLevel(loglevel)
    try:
        result = STOP_THREAD_METHODS[force](thread)
    finally:
        logger.setLevel(previous_loglevel)
    return result

