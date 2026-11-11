"""OS process caps and measured counters, restricted to our own subprocesses.

Memory/CPU/output-file caps are kernel-enforced on Linux; Windows uses a nested
JobObject for commit memory/user CPU. Cumulative IO is sampled, not a claimed
kernel bandwidth guarantee. Fixed worker code also bounds every output write.
"""
import ctypes
import math
import os
import sys
import threading
import time

_job=None

def lower_priority():
    if os.name=='nt':
        if not K.SetPriorityClass(K.GetCurrentProcess(),0x4000):raise ValueError('CAPACITY_PARENT_PRIORITY')
    elif sys.platform.startswith('linux'):
        os.nice(max(0,10-os.getpriority(os.PRIO_PROCESS,0)))
    else:raise ValueError('CAPACITY_OS_RESOURCE_GUARD_UNSUPPORTED')

if os.name=='nt':
    from ctypes import wintypes as w
    K=ctypes.WinDLL('kernel32',use_last_error=True);P=ctypes.WinDLL('psapi',use_last_error=True)
    class IO(ctypes.Structure):
        _fields_=[(n,ctypes.c_ulonglong) for n in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]
    class BASIC(ctypes.Structure):
        _fields_=[('process_time',ctypes.c_longlong),('job_time',ctypes.c_longlong),('flags',w.DWORD),
                  ('min_ws',ctypes.c_size_t),('max_ws',ctypes.c_size_t),('active',w.DWORD),
                  ('affinity',ctypes.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
    class EXT(ctypes.Structure):
        _fields_=[('basic',BASIC),('io',IO),('process_memory',ctypes.c_size_t),('job_memory',ctypes.c_size_t),
                  ('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
    class MEMORY(ctypes.Structure):
        _fields_=[('size',w.DWORD),('faults',w.DWORD)]+[(n,ctypes.c_size_t) for n in
            ('peak_ws','ws','quota_peak_paged','quota_paged','quota_peak_nonpaged','quota_nonpaged','pagefile','peak_pagefile','private')]
    K.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];K.OpenProcess.restype=w.HANDLE
    K.GetCurrentProcess.restype=w.HANDLE
    K.CloseHandle.argtypes=[w.HANDLE]
    K.GetProcessTimes.argtypes=[w.HANDLE,*([ctypes.POINTER(w.FILETIME)]*4)]
    K.GetProcessIoCounters.argtypes=[w.HANDLE,ctypes.POINTER(IO)]
    P.GetProcessMemoryInfo.argtypes=[w.HANDLE,ctypes.POINTER(MEMORY),w.DWORD]
    K.CreateJobObjectW.argtypes=[ctypes.c_void_p,w.LPCWSTR];K.CreateJobObjectW.restype=w.HANDLE
    K.SetInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD]
    K.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE]
    K.SetPriorityClass.argtypes=[w.HANDLE,w.DWORD]
    K.GetPriorityClass.argtypes=[w.HANDLE];K.GetPriorityClass.restype=w.DWORD
    K.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD]
    K.TerminateProcess.argtypes=[w.HANDLE,w.UINT]
    class PBI(ctypes.Structure):
        _fields_=[('reserved1',ctypes.c_void_p),('peb',ctypes.c_void_p),
                  ('reserved2',ctypes.c_void_p*2),('pid',ctypes.c_size_t),('parent',ctypes.c_size_t)]
    N=ctypes.WinDLL('ntdll')
    N.NtQueryInformationProcess.argtypes=[w.HANDLE,w.ULONG,ctypes.c_void_p,w.ULONG,ctypes.c_void_p]

def parent_pid(pid,handle=None):
    if os.name=='nt':
        own=handle is None;h=K.OpenProcess(0x1000,False,pid) if own else handle
        if not h:return None
        try:
            info=PBI()
            return info.parent if N.NtQueryInformationProcess(h,0,ctypes.byref(info),ctypes.sizeof(info),None)==0 else None
        finally:
            if own:K.CloseHandle(h)
    try:
        with open(f'/proc/{pid}/stat') as f:return int(f.read().split(') ',1)[1].split()[1])
    except (OSError,ValueError):return None

def terminate_verified(pid,created,allowed_parents):
    """Kill only the generation-checked fixed worker, never an arbitrary PID."""
    if os.name=='nt':
        handle=K.OpenProcess(0x100000|0x1000|0x10|0x1,False,pid)
        if not handle:return
        try:
            stat=counters(pid,handle)
            if stat is None:return
            if stat['created']!=created or parent_pid(pid,handle) not in allowed_parents:
                raise ValueError('CAPACITY_WORKER_PROCESS_IDENTITY')
            if not K.TerminateProcess(handle,125) and K.WaitForSingleObject(handle,50)!=0:
                raise ValueError('CAPACITY_WORKER_TERMINATE')
        finally:K.CloseHandle(handle)
    else:
        stat=counters(pid)
        if stat is not None:
            if stat['created']!=created or parent_pid(pid) not in allowed_parents:
                raise ValueError('CAPACITY_WORKER_PROCESS_IDENTITY')
            import signal
            try:os.kill(pid,signal.SIGKILL)
            except ProcessLookupError:pass  # Already exited after verified read.

def counters(pid,process_handle=None):
    if os.name=='nt':
        handle=process_handle if process_handle is not None else K.OpenProcess(0x100000|0x1000|0x10,False,pid)
        if not handle:return None
        try:
            if K.WaitForSingleObject(handle,0)==0:return None
            a,b,c,d=(w.FILETIME() for _ in range(4));memory=MEMORY();memory.size=ctypes.sizeof(memory);io=IO()
            if not K.GetProcessTimes(handle,ctypes.byref(a),ctypes.byref(b),ctypes.byref(c),ctypes.byref(d)):return None
            if not P.GetProcessMemoryInfo(handle,ctypes.byref(memory),ctypes.sizeof(memory)):return None
            K.GetProcessIoCounters(handle,ctypes.byref(io))
            number=lambda f:(f.dwHighDateTime<<32)+f.dwLowDateTime
            return dict(cpu_s=(number(c)+number(d))/10000000,rss=memory.ws,peak_rss=memory.peak_ws,
                        io_bytes=io.read_bytes+io.write_bytes,created=number(a),priority=K.GetPriorityClass(handle))
        finally:
            if process_handle is None:K.CloseHandle(handle)
    if sys.platform.startswith('linux'):
        try:
            with open(f'/proc/{pid}/stat') as f:fields=f.read().split(') ',1)[1].split()
            if fields[0]=='Z':return None
            with open(f'/proc/{pid}/status') as f:rows=dict(line.split(':',1) for line in f if ':' in line)
            with open(f'/proc/{pid}/io') as f:io=dict(line.strip().split(': ') for line in f)
            hz=os.sysconf('SC_CLK_TCK')
            return dict(cpu_s=(int(fields[11])+int(fields[12]))/hz,
                        rss=int(rows.get('VmRSS','0 kB').split()[0])*1024,
                        peak_rss=int(rows.get('VmHWM','0 kB').split()[0])*1024,
                        io_bytes=int(io['rchar'])+int(io['wchar']),created=int(fields[19]),priority=int(fields[16]))
        except (OSError,ValueError,KeyError):return None
    raise ValueError('CAPACITY_OS_RESOURCE_GUARD_UNSUPPORTED')

def enforce(budget,parent_pid,cancel_path=None):
    global _job
    start=time.monotonic()
    if os.name=='nt':
        process=K.GetCurrentProcess();_job=K.CreateJobObjectW(None,None)
        limits=EXT();limits.basic.flags=0x2|0x100|0x2000
        limits.basic.process_time=budget['worker_cpu_s']*10000000
        limits.process_memory=budget['worker_memory_mb']*1024*1024
        if not(_job and K.SetInformationJobObject(_job,9,ctypes.byref(limits),ctypes.sizeof(limits))
               and K.AssignProcessToJobObject(_job,process) and K.SetPriorityClass(process,0x4000)):
            raise ValueError('CAPACITY_JOB_CAP_FAILED')
        parent=K.OpenProcess(0x100000,False,parent_pid)
        if not parent:raise ValueError('CAPACITY_PARENT_HANDLE')
        alive=lambda:K.WaitForSingleObject(parent,0)==258
        mode='WINDOWS_JOB_COMMIT_MEMORY_USER_CPU_BELOW_NORMAL'
    elif sys.platform.startswith('linux'):
        import resource
        resource.setrlimit(resource.RLIMIT_AS,(budget['worker_memory_mb']*1024*1024,)*2)
        resource.setrlimit(resource.RLIMIT_CPU,(budget['worker_cpu_s'],budget['worker_cpu_s']+1))
        resource.setrlimit(resource.RLIMIT_FSIZE,(budget['result_bytes'],)*2)
        lower_priority()
        alive=lambda:os.getppid()==parent_pid
        mode='LINUX_RLIMIT_AS_CPU_FSIZE_NICE_10'
    else:raise ValueError('CAPACITY_OS_RESOURCE_GUARD_UNSUPPORTED')
    def watchdog():
        while True:
            if not alive():os._exit(79)
            if cancel_path is not None and cancel_path.exists():os._exit(125)
            if time.monotonic()-start>budget['worker_wall_s']:os._exit(124)
            time.sleep(0.02)
    threading.Thread(target=watchdog,daemon=True).start()
    return dict(mode=mode,wall_watchdog=True,parent_death_watchdog=True,
                memory_kernel_cap=True,cpu_kernel_cap=True,io='POLLED_CUMULATIVE_BOUNDED_OUTPUT')
