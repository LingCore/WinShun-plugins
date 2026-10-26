"""Match the manifest's Windows job limits; keep the job alive until the child exits."""
import ctypes
from ctypes import wintypes as w


class BasicLimits(ctypes.Structure):
    _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                ('flags', w.DWORD), ('min_ws', ctypes.c_size_t), ('max_ws', ctypes.c_size_t),
                ('active_processes', w.DWORD), ('affinity', ctypes.c_size_t),
                ('priority', w.DWORD), ('scheduling', w.DWORD)]


class IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in
                ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [('basic', BasicLimits), ('io', IoCounters), ('process_memory', ctypes.c_size_t),
                ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]


kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.CreateJobObjectW.argtypes = (ctypes.c_void_p, w.LPCWSTR)
kernel.CreateJobObjectW.restype = w.HANDLE
kernel.SetInformationJobObject.argtypes = (w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD)
kernel.SetInformationJobObject.restype = w.BOOL
kernel.AssignProcessToJobObject.argtypes = (w.HANDLE, w.HANDLE)
kernel.AssignProcessToJobObject.restype = w.BOOL
kernel.CloseHandle.argtypes = (w.HANDLE,)
kernel.CloseHandle.restype = w.BOOL


class PluginJob:
    def __init__(self, process, memory_mb=512, allow_processes=False):
        self.handle = kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000 | 0x100 | (0 if allow_processes else 0x8)  # match the declared processes permission
        limits.basic.active_processes = 1
        limits.process_memory = memory_mb * 1024 * 1024
        try:
            if not kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise ctypes.WinError(ctypes.get_last_error())
            if not kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
                raise ctypes.WinError(ctypes.get_last_error())
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.handle:
            kernel.CloseHandle(self.handle)
            self.handle = None


if __name__ == '__main__':
    import subprocess
    import sys
    arguments = sys.argv[1:]
    allow_processes = bool(arguments and arguments[0] == '--allow-processes')
    if allow_processes:
        arguments = arguments[1:]
    process = subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
    job = PluginJob(process, allow_processes=allow_processes)
    try:
        out, err = process.communicate(timeout=45)
        print(out, end='')
        if err:
            print(err, file=sys.stderr, end='')
        if process.returncode == 0:
            print('PASS Windows job: 512MB memory limit; compiler processes ' + ('allowed' if allow_processes else 'blocked'))
        sys.exit(process.returncode)
    finally:
        job.close()
