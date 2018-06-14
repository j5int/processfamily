"""A subset of the operations that can be performed on a process provided by the prctl system call"""

from ctypes import CDLL, c_int, byref, create_string_buffer
from ctypes.util import find_library

libc = CDLL(find_library('c'))

PR_SET_PDEATHSIG = 1
PR_GET_PDEATHSIG = 2

PR_SET_NAME = 15
PR_GET_NAME = 16

def _prctl(option, arg2=0, arg3=0, arg4=0, arg5=0):
    """Calls the libc prctl function, with the given command option and arguments
    return values should be passed by reference"""
    return libc.prctl(option, arg2, arg3, arg4, arg5)

def set_pdeathsig(pdeathsig):
    """Set the parent process death signal of the calling process to pdeathsig (either a signal value in the range 1..maxsig, or 0 to claer)
    This is the signal that the calling process will get when its parent dies.
    This value is cleared for the child of a fork and when executing a set-user-ID or set-group-ID binary"""
    return _prctl(PR_SET_PDEATHSIG, pdeathsig)

def get_pdeathsig():
    """Return the current value of the parent process death signal"""
    result = c_int()
    _prctl(PR_GET_PDEATHSIG, byref(result))
    return result.value

def set_name(name):
    """Set the name of the calling thread. name can be up to 16 bytes long"""
    return _prctl(PR_SET_NAME, create_string_buffer(name, 16))

def get_name():
    """Return the name of the calling thread"""
    result = create_string_buffer(16)
    _prctl(PR_GET_NAME, byref(result))
    return result.value