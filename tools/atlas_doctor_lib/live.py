from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any

from .core import git_state, milliseconds, utc_now, write_json


class ProcessSampleError(RuntimeError):
    pass


def _filetime_to_seconds(value) -> float:
    high = int(value.dwHighDateTime)
    low = int(value.dwLowDateTime)
    return ((high << 32) | low) / 10_000_000.0


def _windows_process_tree(root_pid: int) -> set[int]:
    TH32CS_SNAPPROCESS = 0x00000002
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ('dwSize', wintypes.DWORD),
            ('cntUsage', wintypes.DWORD),
            ('th32ProcessID', wintypes.DWORD),
            ('th32DefaultHeapID', ctypes.c_size_t),
            ('th32ModuleID', wintypes.DWORD),
            ('cntThreads', wintypes.DWORD),
            ('th32ParentProcessID', wintypes.DWORD),
            ('pcPriClassBase', ctypes.c_long),
            ('dwFlags', wintypes.DWORD),
            ('szExeFile', wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    create_snapshot = kernel32.CreateToolhelp32Snapshot
    create_snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    create_snapshot.restype = wintypes.HANDLE
    process_first = kernel32.Process32FirstW
    process_first.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    process_first.restype = wintypes.BOOL
    process_next = kernel32.Process32NextW
    process_next.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    process_next.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle

    snapshot = create_snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        return {root_pid}
    parents: dict[int, int] = {}
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        ok = process_first(snapshot, ctypes.byref(entry))
        while ok:
            parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            ok = process_next(snapshot, ctypes.byref(entry))
    finally:
        close_handle(snapshot)

    result = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, parent in parents.items():
            if parent in result and pid not in result:
                result.add(pid)
                changed = True
    return result


def _windows_sample_pid(pid: int) -> tuple[int, float] | None:
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    PROCESS_VM_READ = 0x0010

    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ('cb', wintypes.DWORD),
            ('PageFaultCount', wintypes.DWORD),
            ('PeakWorkingSetSize', ctypes.c_size_t),
            ('WorkingSetSize', ctypes.c_size_t),
            ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
            ('QuotaPagedPoolUsage', ctypes.c_size_t),
            ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
            ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
            ('PagefileUsage', ctypes.c_size_t),
            ('PeakPagefileUsage', ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    psapi = ctypes.WinDLL('psapi', use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    open_process.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    get_times = kernel32.GetProcessTimes
    get_memory = psapi.GetProcessMemoryInfo

    handle = open_process(PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ, False, pid)
    if not handle:
        return None
    try:
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        if not get_memory(handle, ctypes.byref(counters), counters.cb):
            rss = 0
        else:
            rss = int(counters.WorkingSetSize)
        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        if not get_times(handle, ctypes.byref(creation), ctypes.byref(exit_time), ctypes.byref(kernel), ctypes.byref(user)):
            cpu_seconds = 0.0
        else:
            cpu_seconds = _filetime_to_seconds(kernel) + _filetime_to_seconds(user)
        return rss, cpu_seconds
    finally:
        close_handle(handle)


def _sample_tree(pid: int) -> dict[str, Any]:
    if os.name != 'nt':
        statm = Path(f'/proc/{pid}/statm')
        stat = Path(f'/proc/{pid}/stat')
        if not statm.is_file() or not stat.is_file():
            raise ProcessSampleError(f'Processus {pid} introuvable')
        page_size = os.sysconf('SC_PAGE_SIZE')
        rss = int(statm.read_text(encoding='ascii').split()[1]) * page_size
        fields = stat.read_text(encoding='ascii').split()
        ticks = os.sysconf(os.sysconf_names['SC_CLK_TCK'])
        cpu = (int(fields[13]) + int(fields[14])) / ticks
        return {'process_count': 1, 'rss_bytes': rss, 'cpu_seconds': cpu}

    pids = _windows_process_tree(pid)
    rss_total = 0
    cpu_total = 0.0
    sampled = 0
    for child_pid in pids:
        sample = _windows_sample_pid(child_pid)
        if sample is None:
            continue
        rss, cpu = sample
        rss_total += rss
        cpu_total += cpu
        sampled += 1
    if sampled == 0:
        raise ProcessSampleError(f'Processus {pid} introuvable')
    return {'process_count': sampled, 'rss_bytes': rss_total, 'cpu_seconds': cpu_total}


def inspect_live(
    root: Path,
    *,
    sample_seconds: float = 0.5,
    trace_io: bool = True,
    quiet: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    main_script = root / 'main.py'
    runner = root / 'tools/atlas_doctor_io_runner.py'
    if not main_script.is_file():
        raise RuntimeError('main.py introuvable.')

    trace_path = root / '.ai/runtime/atlas_doctor/live_io_trace.json'
    trace_path.unlink(missing_ok=True)
    env = os.environ.copy()
    current_pythonpath = env.get('PYTHONPATH', '')
    env['PYTHONPATH'] = str(root) + (os.pathsep + current_pythonpath if current_pythonpath else '')
    if trace_io and runner.is_file():
        env['ATLAS_DOCTOR_IO_TRACE'] = str(trace_path)
        command = [sys.executable, '-m', 'tools.atlas_doctor_io_runner', str(main_script)]
    else:
        command = [sys.executable, str(main_script)]

    process = subprocess.Popen(
        command,
        cwd=root,
        env=env,
        stdout=subprocess.DEVNULL if quiet else None,
        stderr=subprocess.DEVNULL if quiet else None,
    )
    samples: list[dict[str, Any]] = []
    previous_cpu: float | None = None
    previous_wall: float | None = None
    logical_cpus = max(1, os.cpu_count() or 1)
    if not quiet:
        print(f'Atlas lance (PID {process.pid}). Utilise l app normalement puis ferme-la pour terminer la mesure.')
    try:
        while process.poll() is None:
            wall = time.perf_counter()
            try:
                raw = _sample_tree(process.pid)
            except ProcessSampleError:
                time.sleep(sample_seconds)
                continue
            cpu = float(raw['cpu_seconds'])
            cpu_one_core = 0.0
            cpu_total = 0.0
            if previous_cpu is not None and previous_wall is not None:
                delta_wall = max(wall - previous_wall, 1e-9)
                delta_cpu = max(cpu - previous_cpu, 0.0)
                cpu_one_core = (delta_cpu / delta_wall) * 100.0
                cpu_total = cpu_one_core / logical_cpus
            row = {
                't_ms': round((wall - started) * 1000.0, 1),
                'rss_mb': round(int(raw['rss_bytes']) / 1024 / 1024, 2),
                'cpu_one_core_percent': round(cpu_one_core, 2),
                'cpu_total_percent': round(cpu_total, 2),
                'process_count': int(raw['process_count']),
            }
            samples.append(row)
            previous_cpu = cpu
            previous_wall = wall
            if not quiet and len(samples) % max(1, round(1.0 / sample_seconds)) == 0:
                print(f"RAM {row['rss_mb']:.1f} MiB | CPU {row['cpu_total_percent']:.1f}% | processus {row['process_count']}")
            time.sleep(sample_seconds)
    except KeyboardInterrupt:
        if process.poll() is None:
            process.terminate()
    finally:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    trace_payload = None
    if trace_path.is_file():
        try:
            trace_payload = json.loads(trace_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            pass

    rss_values = [float(item['rss_mb']) for item in samples]
    cpu_values = [float(item['cpu_total_percent']) for item in samples]
    rss_growth_mb = None
    if len(rss_values) >= 6:
        window = max(1, len(rss_values) // 5)
        first_avg = sum(rss_values[:window]) / window
        last_avg = sum(rss_values[-window:]) / window
        rss_growth_mb = round(last_avg - first_avg, 2)
    payload = {
        'schema_version': 1,
        'kind': 'live_performance',
        'generated_at': utc_now(),
        'git': git_state(root),
        'command': command,
        'returncode': process.returncode,
        'duration_ms': milliseconds(started),
        'sample_seconds': sample_seconds,
        'summary': {
            'samples': len(samples),
            'rss_peak_mb': round(max(rss_values), 2) if rss_values else None,
            'rss_last_mb': round(rss_values[-1], 2) if rss_values else None,
            'rss_growth_mb': rss_growth_mb,
            'possible_memory_growth': bool(rss_growth_mb is not None and rss_growth_mb >= 20.0),
            'cpu_peak_total_percent': round(max(cpu_values), 2) if cpu_values else None,
            'max_process_count': max((int(item['process_count']) for item in samples), default=0),
        },
        'samples': samples,
        'io_trace': trace_payload,
    }
    write_json(root, 'latest_live_perf', payload, rotate=True)
    return payload
