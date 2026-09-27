"""Local hardware measurements for resource admission.

The ResourceManager never probes hardware or substitutes a guessed value, so the
platform must supply a real adapter. Every field returned here is an actual
measurement; anything this module cannot measure is reported as ``None`` so the
manager fails closed instead of admitting a model it cannot fit.
"""

from __future__ import annotations

import ctypes
import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass

from app.agent.resource_manager import ResourceSnapshot

_MB = 1024 * 1024
_VM_STAT_PAGE_RE = re.compile(r"^Pages\s+([a-z ]+):\s+(\d+)\.")


class HardwareMeasurementError(RuntimeError):
    pass


@dataclass(frozen=True)
class _RawMemory:
    total_mb: int | None
    available_mb: int | None


class _MemoryStatusEx(ctypes.Structure):
    """Win32 ``MEMORYSTATUSEX``, declared with fixed-width fields.

    The documented layout is two ``DWORD`` followed by seven ``DWORDLONG``, i.e. 64
    bytes. ``c_ulong`` is only 4 bytes on Windows and 8 on 64-bit Linux, so using it
    here would make this structure silently wrong on every host except the one that
    calls it, and would hide the mistake from a test run on any other platform.
    """

    _fields_ = [
        ("dwLength", ctypes.c_uint32),
        ("dwMemoryLoad", ctypes.c_uint32),
        ("ullTotalPhys", ctypes.c_uint64),
        ("ullAvailPhys", ctypes.c_uint64),
        ("ullTotalPageFile", ctypes.c_uint64),
        ("ullAvailPageFile", ctypes.c_uint64),
        ("ullTotalVirtual", ctypes.c_uint64),
        ("ullAvailVirtual", ctypes.c_uint64),
        ("ullAvailExtendedVirtual", ctypes.c_uint64),
    ]


def _global_memory_status_ex() -> tuple[int, int]:
    """Read physical memory from kernel32 as (total_bytes, available_bytes).

    Isolated as the single Win32 seam so the Windows branch stays reachable from a
    test on any host, and so a failing API call is reported as an unknown measurement
    rather than being mistaken for an empty machine.
    """
    load_library = getattr(ctypes, "WinDLL", None)
    if load_library is None:
        raise HardwareMeasurementError("ctypes.WinDLL is unavailable on this platform")
    status = _MemoryStatusEx()
    status.dwLength = ctypes.sizeof(_MemoryStatusEx)
    if not load_library("kernel32", use_last_error=True).GlobalMemoryStatusEx(
        ctypes.byref(status)
    ):
        raise HardwareMeasurementError(
            f"GlobalMemoryStatusEx failed (winerror {ctypes.get_last_error()})"
        )
    return int(status.ullTotalPhys), int(status.ullAvailPhys)


def _windows_memory() -> _RawMemory:
    total_bytes, available_bytes = _global_memory_status_ex()
    return _RawMemory(total_bytes // _MB, available_bytes // _MB)


def _macos_memory() -> _RawMemory:
    page_size = os.sysconf("SC_PAGE_SIZE")
    total_pages = os.sysconf("SC_PHYS_PAGES")
    total_mb = (page_size * total_pages) // _MB
    try:
        output = subprocess.run(
            ["vm_stat"], capture_output=True, text=True, timeout=5, check=True
        ).stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise HardwareMeasurementError("vm_stat is unavailable") from error
    counters: dict[str, int] = {}
    for line in output.splitlines():
        match = _VM_STAT_PAGE_RE.match(line.strip())
        if match:
            counters[match.group(1).strip()] = int(match.group(2))
    if not counters:
        raise HardwareMeasurementError("vm_stat returned no page counters")
    # Inactive and speculative pages are reclaimable without swapping; wired pages are not.
    reclaimable = sum(
        counters.get(name, 0) for name in ("free", "inactive", "speculative", "purgeable")
    )
    return _RawMemory(total_mb, (page_size * reclaimable) // _MB)


def _linux_memory() -> _RawMemory:
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            fields = {}
            for line in handle:
                key, _, rest = line.partition(":")
                fields[key.strip()] = int(rest.split()[0]) // 1024
    except (OSError, ValueError, IndexError) as error:
        raise HardwareMeasurementError("/proc/meminfo is unreadable") from error
    total = fields.get("MemTotal")
    available = fields.get("MemAvailable")
    if total is None:
        raise HardwareMeasurementError("/proc/meminfo has no MemTotal")
    return _RawMemory(total, available)


def _nvidia_vram_mb() -> int | None:
    binary = shutil.which("nvidia-smi")
    if binary is None:
        return None
    try:
        output = subprocess.run(
            [binary, "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for line in output.splitlines():
        value = line.strip()
        if value.isdigit():
            return int(value)
    return None


def measure_memory() -> _RawMemory:
    system = platform.system()
    if system == "Darwin":
        return _macos_memory()
    if system == "Linux":
        return _linux_memory()
    if system == "Windows":
        return _windows_memory()
    raise HardwareMeasurementError(f"unsupported platform for memory measurement: {system}")


class LocalHardwareResources:
    """Measure this machine's real memory and GPU memory budget."""

    def __init__(self, *, max_unified_memory_mb: int | None = None) -> None:
        self.max_unified_memory_mb = max_unified_memory_mb

    def snapshot(self) -> ResourceSnapshot:
        try:
            memory = measure_memory()
        except HardwareMeasurementError:
            return ResourceSnapshot(ram_mb_available=None, vram_mb_available=None)
        vram = self._vram_mb(memory)
        return ResourceSnapshot(ram_mb_available=memory.available_mb, vram_mb_available=vram)

    def _vram_mb(self, memory: _RawMemory) -> int | None:
        system = platform.system()
        if system == "Darwin":
            # Apple Silicon and integrated AMD GPUs draw on the same unified pool.
            pool = memory.available_mb if memory.available_mb is not None else memory.total_mb
            if pool is None:
                return None
            if self.max_unified_memory_mb is None:
                return pool
            return min(pool, self.max_unified_memory_mb)
        if system == "Linux":
            discrete = _nvidia_vram_mb()
            return discrete if discrete is not None else memory.available_mb
        if system == "Windows":
            # Deliberately no fallback to system RAM, unlike the Linux branch above.
            # A discrete NVIDIA card has a VRAM budget separate from host memory, so
            # substituting available host RAM here would admit a model the GPU cannot
            # hold. No nvidia-smi means an unknown measurement, and unknown stays
            # unknown so admission fails closed.
            return _nvidia_vram_mb()
        return None


class StaticHardwareResources:
    """Explicitly configured budgets for operators and tests.

    Only for environments that state their budget (for example a headless runner
    with a known allocation). It is never a fallback for a failed measurement.
    """

    def __init__(self, *, ram_mb: int | None, vram_mb: int | None) -> None:
        if ram_mb is not None and ram_mb <= 0:
            raise ValueError("ram_mb must be positive")
        if vram_mb is not None and vram_mb <= 0:
            raise ValueError("vram_mb must be positive")
        self.ram_mb = ram_mb
        self.vram_mb = vram_mb

    def snapshot(self) -> ResourceSnapshot:
        return ResourceSnapshot(ram_mb_available=self.ram_mb, vram_mb_available=self.vram_mb)
