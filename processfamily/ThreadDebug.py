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

def find_wsgi_requests(thread=None):
    """Finds wsgi requests on the given thread (generator)"""
    thread = find_thread(thread) if thread else None
    lines = []
    conn = thread.conn if thread else None
    refs = gc.get_referrers(wsgiserver.HTTPRequest)
    reqs = []
    for obj in refs:
        if isinstance(obj, wsgiserver.HTTPRequest):
            if conn is None or obj.conn is conn:
                yield obj
        elif isinstance(obj, (tuple, list)):
            for item in obj:
                if isinstance(item, wsgiserver.HTTPRequest):
                    if conn is None or item.conn is conn:
                        yield item

