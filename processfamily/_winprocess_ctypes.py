# Extends mozprocess with some code from winappdgb:
# These parts are mostly from: http://winappdbg.sourceforge.net/
#
# We've decided not actually add a dependency on that library, though, as it is
# not too straightforward to install, and is quite a a beast.
#
# Copyright (c) 2009-2014, Mario Vilas
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#    * Redistributions of source code must retain the above copyright notice,
#      this list of conditions and the following disclaimer.
#    * Redistributions in binary form must reproduce the above copyright
#      notice,this list of conditions and the following disclaimer in the
#      documentation and/or other materials provided with the distribution.
#    * Neither the name of the copyright holder nor the names of its
#      contributors may be used to endorse or promote products derived from
#      this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

from mozprocess.winprocess import *
from ctypes import cast, pointer, c_size_t, c_ssize_t, byref
import sys

PVOID = LPVOID
DWORD_PTR = LPDWORD
# Map size_t to SIZE_T
SIZE_T  = c_size_t
SSIZE_T = c_ssize_t
PSIZE_T = POINTER(SIZE_T)

CAN_USE_EXTENDED_STARTUPINFO = sys.getwindowsversion().major > 5
# --- Extended process and thread attribute support ---------------------------
if CAN_USE_EXTENDED_STARTUPINFO:
    EXTENDED_STARTUPINFO_PRESENT      = 0x00080000

    PPROC_THREAD_ATTRIBUTE_LIST  = LPVOID
    LPPROC_THREAD_ATTRIBUTE_LIST = PPROC_THREAD_ATTRIBUTE_LIST

    PROC_THREAD_ATTRIBUTE_NUMBER   = 0x0000FFFF
    PROC_THREAD_ATTRIBUTE_THREAD   = 0x00010000  # Attribute may be used with thread creation
    PROC_THREAD_ATTRIBUTE_INPUT    = 0x00020000  # Attribute is input only
    PROC_THREAD_ATTRIBUTE_ADDITIVE = 0x00040000  # Attribute may be "accumulated," e.g. bitmasks, counters, etc.

    # PROC_THREAD_ATTRIBUTE_NUM
    ProcThreadAttributeParentProcess    = 0
    ProcThreadAttributeExtendedFlags    = 1
    ProcThreadAttributeHandleList       = 2
    ProcThreadAttributeGroupAffinity    = 3
    ProcThreadAttributePreferredNode    = 4
    ProcThreadAttributeIdealProcessor   = 5
    ProcThreadAttributeUmsThread        = 6
    ProcThreadAttributeMitigationPolicy = 7
    ProcThreadAttributeMax              = 8

    PROC_THREAD_ATTRIBUTE_PARENT_PROCESS    = ProcThreadAttributeParentProcess      |                                PROC_THREAD_ATTRIBUTE_INPUT
    PROC_THREAD_ATTRIBUTE_EXTENDED_FLAGS    = ProcThreadAttributeExtendedFlags      |                                PROC_THREAD_ATTRIBUTE_INPUT | PROC_THREAD_ATTRIBUTE_ADDITIVE
    PROC_THREAD_ATTRIBUTE_HANDLE_LIST       = ProcThreadAttributeHandleList         |                                PROC_THREAD_ATTRIBUTE_INPUT
    PROC_THREAD_ATTRIBUTE_GROUP_AFFINITY    = ProcThreadAttributeGroupAffinity      | PROC_THREAD_ATTRIBUTE_THREAD | PROC_THREAD_ATTRIBUTE_INPUT
    PROC_THREAD_ATTRIBUTE_PREFERRED_NODE    = ProcThreadAttributePreferredNode      |                                PROC_THREAD_ATTRIBUTE_INPUT
    PROC_THREAD_ATTRIBUTE_IDEAL_PROCESSOR   = ProcThreadAttributeIdealProcessor     | PROC_THREAD_ATTRIBUTE_THREAD | PROC_THREAD_ATTRIBUTE_INPUT
    PROC_THREAD_ATTRIBUTE_UMS_THREAD        = ProcThreadAttributeUmsThread          | PROC_THREAD_ATTRIBUTE_THREAD | PROC_THREAD_ATTRIBUTE_INPUT
    PROC_THREAD_ATTRIBUTE_MITIGATION_POLICY = ProcThreadAttributeMitigationPolicy   |                                PROC_THREAD_ATTRIBUTE_INPUT

    PROCESS_CREATION_MITIGATION_POLICY_DEP_ENABLE           = 0x01
    PROCESS_CREATION_MITIGATION_POLICY_DEP_ATL_THUNK_ENABLE = 0x02
    PROCESS_CREATION_MITIGATION_POLICY_SEHOP_ENABLE         = 0x04

    def RaiseIfZero(result, func = None, arguments = ()):
        """
        Error checking for most Win32 API calls.

        The function is assumed to return an integer, which is C{0} on error.
        In that case the C{WindowsError} exception is raised.
        """
        if not result:
            raise WinError()
        return result

    # BOOL WINAPI InitializeProcThreadAttributeList(
    #   __out_opt   LPPROC_THREAD_ATTRIBUTE_LIST lpAttributeList,
    #   __in        DWORD dwAttributeCount,
    #   __reserved  DWORD dwFlags,
    #   __inout     PSIZE_T lpSize
    # );
    def InitializeProcThreadAttributeList(dwAttributeCount):
        _InitializeProcThreadAttributeList = windll.kernel32.InitializeProcThreadAttributeList
        _InitializeProcThreadAttributeList.argtypes = [LPPROC_THREAD_ATTRIBUTE_LIST, DWORD, DWORD, PSIZE_T]
        _InitializeProcThreadAttributeList.restype  = bool

        Size = SIZE_T(0)
        _InitializeProcThreadAttributeList(None, dwAttributeCount, 0, byref(Size))
        RaiseIfZero(Size.value)
        AttributeList = (BYTE * Size.value)()
        success = _InitializeProcThreadAttributeList(byref(AttributeList), dwAttributeCount, 0, byref(Size))
        RaiseIfZero(success)
        return AttributeList

    # BOOL WINAPI UpdateProcThreadAttribute(
    #   __inout    LPPROC_THREAD_ATTRIBUTE_LIST lpAttributeList,
    #   __in       DWORD dwFlags,
    #   __in       DWORD_PTR Attribute,
    #   __in       PVOID lpValue,
    #   __in       SIZE_T cbSize,
    #   __out_opt  PVOID lpPreviousValue,
    #   __in_opt   PSIZE_T lpReturnSize
    # );
    def UpdateProcThreadAttribute(lpAttributeList, Attribute, Value, cbSize = None):
        _UpdateProcThreadAttribute = windll.kernel32.UpdateProcThreadAttribute
        _UpdateProcThreadAttribute.argtypes = [LPPROC_THREAD_ATTRIBUTE_LIST, DWORD, DWORD, PVOID, SIZE_T, PVOID, PSIZE_T]
        _UpdateProcThreadAttribute.restype  = bool
        _UpdateProcThreadAttribute.errcheck = RaiseIfZero

        if cbSize is None:
            cbSize = sizeof(Value)
        _UpdateProcThreadAttribute(byref(lpAttributeList), 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST, byref(Value), cbSize, None, None)

    # VOID WINAPI DeleteProcThreadAttributeList(
    #   __inout  LPPROC_THREAD_ATTRIBUTE_LIST lpAttributeList
    # );
    def DeleteProcThreadAttributeList(lpAttributeList):
        _DeleteProcThreadAttributeList = windll.kernel32.DeleteProcThreadAttributeList
        _DeleteProcThreadAttributeList.restype = None
        _DeleteProcThreadAttributeList(byref(lpAttributeList))

    class ProcThreadAttributeList (object):
        """
        Extended process and thread attribute support.

        To be used with L{STARTUPINFOEX}.
        Only available for Windows Vista and above.

        @type AttributeList: list of tuple( int, ctypes-compatible object )
        @ivar AttributeList: List of (Attribute, Value) pairs.

        @type AttributeListBuffer: L{LPPROC_THREAD_ATTRIBUTE_LIST}
        @ivar AttributeListBuffer: Memory buffer used to store the attribute list.
            L{InitializeProcThreadAttributeList},
            L{UpdateProcThreadAttribute},
            L{DeleteProcThreadAttributeList} and
            L{STARTUPINFOEX}.
        """

        def __init__(self, AttributeList):
            """
            @type  AttributeList: list of tuple( int, ctypes-compatible object )
            @param AttributeList: List of (Attribute, Value) pairs.
            """
            self.AttributeList = AttributeList
            self.AttributeListBuffer = InitializeProcThreadAttributeList(
                                                                len(AttributeList))
            try:
                for Attribute, Value in AttributeList:
                    UpdateProcThreadAttribute(self.AttributeListBuffer,
                                              Attribute, Value)
            except:
                ProcThreadAttributeList.__del__(self)
                raise

        def __del__(self):
            try:
                DeleteProcThreadAttributeList(self.AttributeListBuffer)
                del self.AttributeListBuffer
            except Exception:
                pass

        def __copy__(self):
            return self.__deepcopy__()

        def __deepcopy__(self):
            return self.__class__(self.AttributeList)

        @property
        def value(self):
            return cast(pointer(self.AttributeListBuffer), LPVOID)

        @property
        def _as_parameter_(self):
            return self.value

        # XXX TODO
        @staticmethod
        def from_param(value):
            raise NotImplementedError()


    # STARTUPINFOEX structure:
    class STARTUPINFOEX(Structure):
        _fields_ = [
            ('StartupInfo',     STARTUPINFO),
            ('lpAttributeList', PPROC_THREAD_ATTRIBUTE_LIST),
        ]
    LPSTARTUPINFOEX = POINTER(STARTUPINFOEX)
    _create_process_startup_info_type = LPSTARTUPINFOEX

else:
    _create_process_startup_info_type = LPSTARTUPINFO

ExtendedCreateProcessProto = WINFUNCTYPE(BOOL,                  # Return type
                                 LPCWSTR,               # lpApplicationName
                                 LPWSTR,                # lpCommandLine
                                 LPVOID,                # lpProcessAttributes
                                 LPVOID,                # lpThreadAttributes
                                 BOOL,                  # bInheritHandles
                                 DWORD,                 # dwCreationFlags
                                 LPVOID,                # lpEnvironment
                                 LPCWSTR,               # lpCurrentDirectory
                                 _create_process_startup_info_type,   # lpStartupInfo / lpStartupInfoEx
                                 LPPROCESS_INFORMATION  # lpProcessInformation
                                 )

ExtendedCreateProcess = ExtendedCreateProcessProto(("CreateProcessW", windll.kernel32),
                                   CreateProcessFlags)
ExtendedCreateProcess.errcheck = ErrCheckCreateProcess
