"""Run a native test and release its private child processes before temp cleanup."""
import ctypes
from contextlib import ExitStack
from ctypes import wintypes
from pathlib import Path
import os
import subprocess
import sys
import time
import uuid


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
        ("flags", wintypes.DWORD), ("minimum_working_set", ctypes.c_size_t),
        ("maximum_working_set", ctypes.c_size_t), ("process_limit", wintypes.DWORD),
        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
        ("scheduling", wintypes.DWORD),
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("basic", _BasicLimits), ("io_counters", ctypes.c_uint64 * 6),
        ("memory_limits_and_peaks", ctypes.c_size_t * 4),
    ]


def _kernel():
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    handle, dword, pointer = wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p
    for name, result, args in (
        ("CreateJobObjectW", handle, [pointer, wintypes.LPCWSTR]),
        ("OpenJobObjectW", handle, [dword, wintypes.BOOL, wintypes.LPCWSTR]),
        ("GetCurrentProcess", handle, []),
        ("OpenProcess", handle, [dword, wintypes.BOOL, dword]),
        ("IsProcessInJob", wintypes.BOOL, [handle, handle, pointer]),
        ("WaitForSingleObject", dword, [handle, dword]),
        ("SetInformationJobObject", wintypes.BOOL, [handle, dword, pointer, dword]),
        ("QueryInformationJobObject", wintypes.BOOL, [handle, dword, pointer, dword, pointer]),
        ("AssignProcessToJobObject", wintypes.BOOL, [handle, handle]),
        ("TerminateJobObject", wintypes.BOOL, [handle, wintypes.UINT]),
        ("CloseHandle", wintypes.BOOL, [handle]),
    ):
        function = getattr(api, name)
        function.argtypes, function.restype = args, result
    return api


def _checked(result):
    if not result:
        raise ctypes.WinError(ctypes.get_last_error())
    return result


def _run_child(job_name, command):
    # Join before starting Maya, so even a very short-lived parent cannot
    # create an untracked licensing helper. The test owns the only lasting handle.
    api = _kernel()
    job = _checked(api.OpenJobObjectW(0x0001, False, job_name))  # ASSIGN_PROCESS
    try:
        _checked(api.AssignProcessToJobObject(job, api.GetCurrentProcess()))
    finally:
        api.CloseHandle(job)
    return subprocess.call(command, stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)


def _job_members(api, job):
    capacity = 16
    while True:
        # JOBOBJECT_BASIC_PROCESS_ID_LIST contains two DWORDs then ULONG_PTR IDs.
        buffer = ctypes.create_string_buffer(8 + capacity * ctypes.sizeof(ctypes.c_size_t))
        if api.QueryInformationJobObject(job, 3, buffer, ctypes.sizeof(buffer), None):
            count = wintypes.DWORD.from_buffer(buffer, 4).value
            return list((ctypes.c_size_t * count).from_buffer(buffer, 8))
        if ctypes.get_last_error() != 234:  # ERROR_MORE_DATA
            raise ctypes.WinError(ctypes.get_last_error())
        capacity *= 2


def _finish_job(api, job):
    # Windows removes terminating children from the job count before their
    # handles are signaled. Wait on the owned processes to release their files.
    with ExitStack() as scope:
        processes = []
        try:
            for pid in _job_members(api, job):
                process = api.OpenProcess(0x101000, False, pid)  # SYNCHRONIZE | QUERY_LIMITED_INFORMATION
                if not process and ctypes.get_last_error() == 87:  # exited before OpenProcess
                    continue
                scope.callback(api.CloseHandle, _checked(process))
                is_member = wintypes.BOOL()
                _checked(api.IsProcessInJob(process, job, ctypes.byref(is_member)))
                if is_member.value:
                    processes.append(process)
        finally:
            _checked(api.TerminateJobObject(job, 1))
        deadline = time.monotonic() + 10
        for process in processes:
            wait = api.WaitForSingleObject(process, max(0, int((deadline - time.monotonic()) * 1000)))
            if wait == 258:  # WAIT_TIMEOUT
                raise TimeoutError("A private native test child has not exited")
            if wait != 0:
                raise ctypes.WinError(ctypes.get_last_error())


def run_native_test(command, **kwargs):
    if os.name != "nt":
        return subprocess.run(command, **kwargs)
    api = _kernel()
    job_name = "Local\\hmb-native-test-" + uuid.uuid4().hex
    job = _checked(api.CreateJobObjectW(None, job_name))
    try:
        limits = _ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        _checked(api.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
        try:
            return subprocess.run(
                [sys.executable, "-I", "-S", "-B", str(Path(__file__).resolve()), job_name, *command],
                **kwargs,
            )
        finally:
            _finish_job(api, job)
    finally:
        api.CloseHandle(job)


if __name__ == "__main__":
    raise SystemExit(_run_child(sys.argv[1], sys.argv[2:]))
