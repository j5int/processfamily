#!/usr/bin/env python

"""Module to help with debugging errors by looking up things on the gc stack"""

import gc
import logging
import threading
from j5.OS import ThreadControl
# TODO: investigate what would happen when not using cherrypy
from cherrypy import wsgiserver

logger = logging.getLogger("j5.OS.ThreadDebug")

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

def find_wsgi_environs(objects=None, loglevel=logging.DEBUG):
    """Filters the given objects (or all objects in the system if not given) and returns those that are wsgi environs"""
    objects = gc.get_objects() if objects is None else objects
    logger.log(loglevel, "find_wsgi_environs searching %d objects", len(objects))
    dicts = filter(lambda i: isinstance(i, dict), objects)
    del objects
    logger.log(loglevel, "find_wsgi_environs searching %d dicts", len(dicts))
    environs = filter(lambda d: "wsgi.input" in d, dicts)
    del dicts
    logger.log(loglevel, "find_wsgi_environs found %d wsgi environs", len(environs))
    return environs

def find_wsgi_environs_by_rfile(rfile, objects=None, loglevel=logging.DEBUG):
    """Finds any wsgi environs that have the given rfile as wsgi.input"""
    objects = gc.get_objects() if objects is None else objects
    logger.log(loglevel, "find_wsgi_environs searching %d objects", len(objects))
    dicts = filter(lambda i: isinstance(i, dict), objects)
    del objects
    logger.log(loglevel, "find_wsgi_environs searching %d dicts", len(dicts))
    environs = filter(lambda d: d.get("wsgi.input", None) is rfile, dicts)
    del dicts
    logger.log(loglevel, "find_wsgi_environs found %d wsgi environs", len(environs))
    return environs

def find_thread_frame(thread, objects=None, error_on_failure=True, loglevel=logging.INFO):
    """Finds the leaf frame for the given thread"""
    thread = find_thread(thread)
    for found_thread, leaf_frame in find_thread_frames():
        if found_thread is thread:
            return leaf_frame
    if error_on_failure:
        raise ValueError("Could not find leaf frame for given thread %s" % thread)
    else:
        return None

def find_thread_frames(objects=None, loglevel=logging.INFO):
    """Generates (thread, leaf_frame) for current threads; thread will be None for the main thread and some other special threads"""
    objects = gc.get_objects() if objects is None else objects
    # frames = filter(lambda i: isinstance(i, types.FrameType), objects)
    frames = filter(lambda i: 'frame' in repr(type(i)) and hasattr(i, "f_back"), objects)
    logger.log(loglevel, "find_thread_frames found %d frames", len(frames))
    parent_frames = filter(lambda f: f.f_back is None, frames)
    logger.log(loglevel, "find_thread_frames found %d parent frames (threads)", len(parent_frames))
    back_frames = set(map(lambda f: f.f_back, frames))
    leaf_frames = filter(lambda f: f not in back_frames, frames)
    logger.log(loglevel, "find_thread_frames found %d leaf frames (threads)", len(leaf_frames))
    for n, frame in enumerate(leaf_frames):
        head_frame = frame
        while head_frame.f_back is not None:
            head_frame = head_frame.f_back
        head_locals = head_frame.f_locals
        if isinstance(head_locals.get('self', None), threading.Thread):
            found_thread = head_locals['self']
        else:
            found_thread = None
        yield found_thread, frame


