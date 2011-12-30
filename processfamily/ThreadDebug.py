#!/usr/bin/env python

"""Module to help with debugging errors by looking up things on the gc stack"""

import gc
import logging
import sys
import threading
# TODO: investigate what would happen when not using cherrypy
from cherrypy import wsgiserver
from j5.Web.Server import RequestStack

if not hasattr(sys, "_current_frames"):
    raise ImportError("Cannot use ThreadDebug without sys._current_frames")

logger = logging.getLogger("j5.OS.ThreadDebug")

def find_thread(thread, error_on_failure=True):
    """Looks up a thread by thread number and returns the thread object. If given a thread, return the thread. If not error_on_failure, return None if not found"""
    if isinstance(thread, (int, long)):
        for t in threading.enumerate():
            if t.ident == thread:
                return t
        else:
            if error_on_failure:
                raise ValueError("Could not find thread %s" % thread)
            else:
                return None
    return thread

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

def environ_has_rfile(environ, rfile):
    """Returns whether the given environ matches the given rfile (including a wrapped version of it)"""
    wsgi_input = environ.get("wsgi.input", None)
    if not wsgi_input:
        return False
    return wsgi_input is rfile or getattr(wsgi_input, "rfile", None) is rfile

def find_wsgi_environs(rfile=None, objects=None, loglevel=logging.INFO):
    """Filters the given objects (or all objects in the system if not given) and returns those that are wsgi environs, matching rfile if provided"""
    objects = gc.get_objects() if objects is None else objects
    logger.log(loglevel, "find_wsgi_environs searching %d objects", len(objects))
    dicts = filter(lambda i: isinstance(i, dict), objects)
    del objects
    logger.log(loglevel, "find_wsgi_environs searching %d dicts", len(dicts))
    environs = filter(lambda d: "wsgi.input" in d, dicts)
    if rfile is not None:
        logger.log(loglevel, "find_wsgi_environs searching %d environs for rfile", len(environs))
        environs = filter(lambda d: environ_has_rfile(d, rfile), environs)
    del dicts
    logger.log(loglevel, "find_wsgi_environs found %d wsgi environs", len(environs))
    return environs

def find_thread_environs(threads=None, objects=None):
    """Generates a set of thread, (server, conn, environs) results for active cherrypy threads"""
    threads = threading.enumerate() if threads is None else threads
    for thread in threads:
        server = getattr(thread, "server", None)
        conn = getattr(thread, "conn", None)
        environ = RequestStack.request_stack.get_environ_by_thread_id(thread.ident)
        environs = [environ] if environ else []
        if server or conn or environs:
            yield thread, (server, conn, environs)

def find_thread_frame(thread_id, error_on_failure=True, loglevel=logging.INFO):
    """Finds the leaf frame for the given thread"""
    leaf_frames = sys._current_frames()
    for t_id, frame in leaf_frames.items():
        if thread_id == t_id:
            return frame
    if error_on_failure:
        raise ValueError("Could not find leaf frame for given thread %s" % thread)
    else:
        return None

def find_thread_frames(loglevel=logging.INFO):
    """Generates (thread, leaf_frame) for current threads; thread will be None for the main thread and some other special threads"""
    leaf_frames = sys._current_frames()
    threads = dict((t.ident, t) for t in threading.enumerate())
    for thread_id, frame in leaf_frames.items():
        if thread_id in threads:
            yield threads[thread_id], frame
        else:
            yield None, frame


