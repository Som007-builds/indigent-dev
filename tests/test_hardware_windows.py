"""Windows must be a measured platform, not an unknown one.

``measure_memory`` and ``LocalHardwareResources._vram_mb`` historically dispatched
only on Darwin and Linux, so on Windows they raised or reported nothing. The
ResourceManager fails closed on an unknown measurement, which meant that real mode
could not select *any* model on Windows -- including the ``rtx_3050a_4gb`` profile
that PRD section 24 names as a supported target.

These tests pin the Windows behavior without running on Windows: the platform is
selected by patching ``platform.system`` and every OS touchpoint is replaced, so
the suite stays hermetic and platform-independent. The ctypes struct is asserted
to be fixed-width so the declared layout is correct on any host, and the Darwin
and Linux paths are asserted to be untouched.
"""

from __future__ import annotations

import ctypes
import io
import subprocess

import pytest

from app.agent.resource_manager import ResourceManager
from app.config import Settings
from app.deps import build_hardware_resources
from app.providers.types import ModelInfo
from app.runtime.hardware import (
    HardwareMeasurementError,
    LocalHardwareResources,
    StaticHardwareResources,
    _MemoryStatusEx,
    _nvidia_vram_mb,
    _RawMemory,
    measure_memory,
)

_MB = 1024 * 1024


@pytest.fixture
def on_windows(monkeypatch):
    monkeypatch.setattr("app.runtime.hardware.platform.system", lambda: "Windows")


@pytest.fixture
def status_ex(monkeypatch):
    """Replace the kernel32 call; returns the list of (total, available) it received."""
    calls: list[tuple[int, int]] = []

    def fake() -> tuple[int, int]:
        value = (16 * 1024 * _MB, 9 * 1024 * _MB)
        calls.append(value)
        return value

    monkeypatch.setattr("app.runtime.hardware._global_memory_status_ex", fake)
    return calls


# ---------------------------------------------------------------------------
# System memory
# ---------------------------------------------------------------------------


def test_windows_memory_reports_total_and_available_in_mb(on_windows, status_ex):
    memory = measure_memory()
    assert memory.total_mb == 16 * 1024
    assert memory.available_mb == 9 * 1024
    assert status_ex, "the kernel32 measurement must actually be used"


def test_windows_memory_uses_the_measured_bytes_not_a_guess(on_windows, monkeypatch):
    """Values come from the API, byte-for-byte truncated to MB -- never estimated."""
    seen: dict[str, int] = {}

    def fake() -> tuple[int, int]:
        # 15.5 GB total, 7.25 GB available: fractional MB must truncate, not round.
        seen["total"] = int(15.5 * 1024 * 1024 * 1024)
        seen["available"] = int(7.25 * 1024 * 1024 * 1024)
        return seen["total"], seen["available"]

    monkeypatch.setattr("app.runtime.hardware._global_memory_status_ex", fake)
    memory = measure_memory()
    assert memory.total_mb == int(15.5 * 1024)
    assert memory.available_mb == int(7.25 * 1024)
    assert memory.total_mb > memory.available_mb > 0


def test_windows_memory_zero_available_is_not_treated_as_unknown(on_windows, monkeypatch):
    """A genuinely exhausted machine reports 0 MB free, which is a real measurement."""
    monkeypatch.setattr(
        "app.runtime.hardware._global_memory_status_ex", lambda: (8 * 1024 * _MB, 0)
    )
    memory = measure_memory()
    assert memory.available_mb == 0
    assert memory.total_mb == 8 * 1024


def test_failed_global_memory_status_ex_raises_measurement_error(on_windows, monkeypatch):
    """A failed API call is an unknown measurement, not a zero-memory machine."""

    def boom():
        raise HardwareMeasurementError("GlobalMemoryStatusEx failed")

    monkeypatch.setattr("app.runtime.hardware._global_memory_status_ex", boom)
    with pytest.raises(HardwareMeasurementError):
        measure_memory()


def test_snapshot_returns_none_when_the_api_is_unavailable(monkeypatch):
    """snapshot() must degrade to unknown rather than propagate or invent a value."""

    def boom():
        raise HardwareMeasurementError("kernel32 unavailable")

    monkeypatch.setattr("app.runtime.hardware.measure_memory", boom)
    snapshot = LocalHardwareResources().snapshot()
    assert snapshot.ram_mb_available is None
    assert snapshot.vram_mb_available is None


def test_memory_status_ex_layout_is_fixed_width():
    """The struct must be the documented 64-byte MEMORYSTATUSEX on every host.

    ctypes normalizes c_uint32 to c_ulong and c_uint64 to c_ulonglong, so the field
    *types* are not comparable by identity. Field size and offset are the real
    invariant: had this used plain c_ulong, the two DWORDs would be 8 bytes each on
    a 64-bit non-Windows host and the struct would total 72 bytes, silently wrong
    everywhere except the platform that actually calls it.
    """
    layout = {name: getattr(_MemoryStatusEx, name) for name, *_ in _MemoryStatusEx._fields_}
    assert ctypes.sizeof(_MemoryStatusEx) == 64
    assert layout["dwLength"].size == 4 and layout["dwLength"].offset == 0
    assert layout["dwMemoryLoad"].size == 4 and layout["dwMemoryLoad"].offset == 4
    assert layout["ullTotalPhys"].size == 8 and layout["ullTotalPhys"].offset == 8
    assert layout["ullAvailPhys"].size == 8 and layout["ullAvailPhys"].offset == 16
    assert layout["ullAvailExtendedVirtual"].offset == 56


# ---------------------------------------------------------------------------
# Discrete GPU memory
# ---------------------------------------------------------------------------


def _fake_nvidia_smi(monkeypatch, stdout: str, returncode: int = 0):
    seen: dict[str, object] = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        return subprocess.CompletedProcess(args, returncode, stdout, "")

    monkeypatch.setattr("app.runtime.hardware.shutil.which", lambda name: "C:/nvidia-smi.exe")
    monkeypatch.setattr("app.runtime.hardware.subprocess.run", fake_run)
    return seen


def test_windows_vram_reads_nvidia_smi(on_windows, monkeypatch):
    seen = _fake_nvidia_smi(monkeypatch, "3769\n")
    vram = LocalHardwareResources()._vram_mb(_RawMemory(8 * 1024, 4 * 1024))
    assert vram == 3769
    assert seen["args"] == [
        "C:/nvidia-smi.exe",
        "--query-gpu=memory.free",
        "--format=csv,noheader,nounits",
    ]


def test_windows_vram_takes_the_first_gpu_when_several_report(on_windows, monkeypatch):
    _fake_nvidia_smi(monkeypatch, "3769\n1024\n")
    memory = _RawMemory(8 * 1024, 4 * 1024)
    assert LocalHardwareResources()._vram_mb(memory) == 3769


def test_windows_vram_never_falls_back_to_system_ram(on_windows, monkeypatch):
    """No nvidia-smi on an unknown-Windows box must yield None, never system RAM.

    Falling back to available system memory would let the manager admit a model
    that cannot fit in the GPU, which is the opposite of failing closed.
    """
    monkeypatch.setattr("app.runtime.hardware.shutil.which", lambda name: None)
    memory = _RawMemory(32 * 1024, 24 * 1024)
    assert LocalHardwareResources()._vram_mb(memory) is None


def _local_model(model_id: str, memory_mb: int) -> ModelInfo:
    return ModelInfo(
        model_id,
        model_id,
        "ollama",
        "local",
        frozenset({"inspection"}),
        frozenset({"rtx_3050a_4gb"}),
        memory_estimate_mb=memory_mb,
    )


def test_windows_without_a_discrete_gpu_refuses_local_models_until_a_budget_is_stated(
    on_windows, monkeypatch
):
    """The unknown-VRAM box must fail closed, and it must fail closed loudly.

    ``ResourceManager.can_select`` gates a local model on vram_mb_available alone and
    treats None as unadmittable, so a Windows machine with no detectable discrete GPU
    selects nothing. That is the intended fail-closed outcome, not a crash and not a
    fabricated number, and it is the state the next test shows how to remedy.
    """
    monkeypatch.setattr("app.runtime.hardware.shutil.which", lambda name: None)
    manager = ResourceManager(LocalHardwareResources())
    assert manager.can_select(_local_model("fits-in-24gb-of-ram", 3_000)) is False


def test_windows_without_a_discrete_gpu_is_usable_once_a_budget_is_stated(
    on_windows, monkeypatch
):
    """A machine whose VRAM cannot be measured stays usable via the explicit budget.

    This is the path that makes an integrated-graphics Windows host work at all, and
    it goes through the real composition helper rather than a hand-built stub, so the
    test covers the wiring an operator actually depends on.
    """
    monkeypatch.setattr("app.runtime.hardware.shutil.which", lambda name: None)
    resources = build_hardware_resources(Settings(hardware_vram_budget_mb=4096))
    assert isinstance(resources, StaticHardwareResources)
    manager = ResourceManager(resources)
    assert manager.can_select(_local_model("fits", 3_000)) is True
    assert manager.can_select(_local_model("too-big", 8_000)) is False


def test_measured_windows_vram_wins_over_an_absent_budget(on_windows, monkeypatch):
    """A real nvidia-smi reading is used as-is; no budget is needed or consulted."""
    _fake_nvidia_smi(monkeypatch, "3769\n")
    resources = build_hardware_resources(Settings())
    manager = ResourceManager(resources)
    assert manager.can_select(_local_model("fits", 3_700)) is True
    assert manager.can_select(_local_model("too-big", 3_900)) is False


def test_absent_nvidia_smi_returns_none_without_raising(monkeypatch):
    monkeypatch.setattr("app.runtime.hardware.shutil.which", lambda name: None)
    assert _nvidia_vram_mb() is None


def test_missing_binary_raises_oserror_returns_none(monkeypatch):
    """A race where the binary vanishes between which() and run() must not crash."""
    monkeypatch.setattr("app.runtime.hardware.shutil.which", lambda name: "C:/nvidia-smi.exe")

    def boom(*args, **kwargs):
        raise FileNotFoundError("nvidia-smi")

    monkeypatch.setattr("app.runtime.hardware.subprocess.run", boom)
    assert _nvidia_vram_mb() is None


def test_nonzero_nvidia_smi_exit_returns_none(monkeypatch):
    """A driver-level failure is an unknown measurement, not a crash."""
    monkeypatch.setattr("app.runtime.hardware.shutil.which", lambda name: "C:/nvidia-smi.exe")

    def boom(*args, **kwargs):
        raise subprocess.CalledProcessError(returncode=9, cmd="nvidia-smi")

    monkeypatch.setattr("app.runtime.hardware.subprocess.run", boom)
    assert _nvidia_vram_mb() is None


def test_unparsable_nvidia_smi_output_returns_none(monkeypatch):
    _fake_nvidia_smi(monkeypatch, "No devices were found\n")
    assert _nvidia_vram_mb() is None


# ---------------------------------------------------------------------------
# Existing platforms must be untouched
# ---------------------------------------------------------------------------


def test_darwin_branch_is_unchanged(monkeypatch):
    monkeypatch.setattr("app.runtime.hardware.platform.system", lambda: "Darwin")
    # os.sysconf does not exist on a Windows host, so the attribute is created here.
    monkeypatch.setattr("app.runtime.hardware.os.sysconf", lambda name: 4096, raising=False)
    monkeypatch.setattr(
        "app.runtime.hardware.subprocess.run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, "Pages free: 100.\n", ""),
    )
    memory = measure_memory()
    assert memory.total_mb > 0
    assert memory.available_mb >= 0


def test_linux_branch_is_unchanged(monkeypatch):
    monkeypatch.setattr("app.runtime.hardware.platform.system", lambda: "Linux")
    monkeypatch.setattr(
        "builtins.open",
        lambda *a, **k: io.StringIO(
            "MemTotal:       16384000 kB\nMemAvailable:    8192000 kB\n"
        ),
    )
    memory = measure_memory()
    assert memory.total_mb == 16384000 // 1024
    assert memory.available_mb == 8192000 // 1024


def test_linux_vram_still_falls_back_to_system_ram(monkeypatch):
    """The existing Linux no-nvidia-smi fallback must be preserved as-is."""
    monkeypatch.setattr("app.runtime.hardware.platform.system", lambda: "Linux")
    monkeypatch.setattr("app.runtime.hardware.shutil.which", lambda name: None)
    memory = _RawMemory(32 * 1024, 24 * 1024)
    assert LocalHardwareResources()._vram_mb(memory) == 24 * 1024


def test_unknown_platform_still_raises(monkeypatch):
    monkeypatch.setattr("app.runtime.hardware.platform.system", lambda: "Plan9")
    with pytest.raises(HardwareMeasurementError, match="unsupported platform"):
        measure_memory()
