"""Reading this process's resident memory, cheaply enough to poll (#160).

`max_steps` bounds instructions and `timeout_ms` bounds wall clock, but neither
bounds the heap: a script that grows a list in a loop runs until the host gets a
`MemoryError` or the OS kills it. `max_memory_mb` is the missing third bound.

**Three of the four approaches the issue proposed were measured and rejected**,
which is why this module reads RSS from the OS rather than counting allocations:

- `tracemalloc` — **64x slowdown** on allocation-heavy code (0.026s → 1.681s on a
  300k-iteration loop), and 11.9 µs per `get_traced_memory()`. Unusable even as an
  opt-in, and #173 already names throughput as the bootstrapping blocker.
- `sys.getallocatedblocks()` — cheap (0.8 µs) but counts pymalloc **blocks, not
  bytes**, so it cannot back a limit expressed in megabytes without inventing a
  conversion. It is also absent on PyPy.
- Counting allocations in the VM's value constructors — deterministic, but it
  measures *elements*, and an embedder asked for megabytes. Left on the table
  rather than dismissed: it is the portable answer if a deterministic bound is
  ever wanted alongside this one.

Reading RSS costs **6.8 µs** on Windows, which at the polling interval the VM uses
is a few nanoseconds per instruction. That is the trade this module exists to make.

**What this cannot do**, stated because a memory limit implies more than it
delivers: polling bounds *growth over time*, not a single allocation. A program
that asks for one enormous list gets it, and the check fires afterwards — by which
point the process may already be dead. "Afterwards" is at the next sample or when
`VM.execute` returns, whichever comes first (#999). Only an OS-level limit (ulimit, cgroups, a
container memory cap) prevents that, and `SECURITY_POSTURE.md §5` says so.
"""

from __future__ import annotations

import math
import sys

_PAGE_SIZE = 4096


def _rss_windows():
    import ctypes
    import ctypes.wintypes as wintypes

    class _ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    # Declared explicitly: without argtypes the call silently returns a zeroed
    # struct on 64-bit, which reads as "0 MB resident" and would make the limit
    # unenforceable while looking like it worked.
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(_ProcessMemoryCounters), wintypes.DWORD
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    handle = kernel32.GetCurrentProcess()
    # One struct, reused. Allocating a fresh one per read doubled the cost
    # (15 us against 7), and this is on a polling path.
    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(_ProcessMemoryCounters)
    size = ctypes.sizeof(_ProcessMemoryCounters)
    reference = ctypes.byref(counters)

    def read() -> int | None:
        if not psapi.GetProcessMemoryInfo(handle, reference, size):
            return None
        return int(counters.WorkingSetSize)

    read()  # prove it works now, not at the first limit check
    return read


def _rss_proc_statm():
    """Linux: field 2 of /proc/self/statm is resident pages."""
    def read() -> int | None:
        try:
            with open("/proc/self/statm", "rb") as handle:
                return int(handle.read().split()[1]) * _PAGE_SIZE
        except (OSError, IndexError, ValueError):
            return None

    if read() is None:
        raise OSError("/proc/self/statm unreadable")
    return read


def _rss_getrusage():
    """macOS and other POSIX: `ru_maxrss`, in bytes on Darwin and KiB on Linux.

    A *peak*, not a current reading, so it never falls. For a limit that is the
    conservative direction -- it can fire late but not early on freed memory.
    """
    import resource

    # Reached through `getattr` rather than attribute access: `resource` is
    # POSIX-only, so mypy on Windows reports "Module has no attribute
    # getrusage" -- while a `type: ignore` would be flagged as unused on the
    # Linux runner that CI type-checks on. This is correct on both.
    getrusage = getattr(resource, "getrusage")
    rusage_self = getattr(resource, "RUSAGE_SELF")
    scale = 1 if sys.platform == "darwin" else 1024

    def read() -> int | None:
        return int(getrusage(rusage_self).ru_maxrss) * scale

    read()
    return read


def _select_reader():
    for candidate in (_rss_windows, _rss_proc_statm, _rss_getrusage):
        try:
            return candidate()
        except Exception:  # noqa: BLE001 - any failure means "try the next one"
            continue
    return None


_READER = _select_reader()


def rss_bytes() -> int | None:
    """This process's resident set size, or None where it cannot be read."""
    if _READER is None:
        return None
    return _READER()


_MB = 1048576


class MemoryCeiling(int):
    """An absolute RSS ceiling that remembers the limit it was set from (#1004).

    The VM compares RSS against one number, `baseline + limit`, so it carries
    one attribute rather than three (PyPy's 80-attribute limit, #702). But the
    host set the *limit*, and a message quoting only the sum told someone who
    passed `max_memory_mb=50` that the run was "past its 76 MB ceiling".

    As an `int` it compares, inherits into child VMs and prints as the
    ceiling did. The two parts ride along for the message.
    """

    baseline: int
    limit: int

    def __new__(cls, baseline: int, limit: int) -> MemoryCeiling:
        ceiling = super().__new__(cls, baseline + limit)
        ceiling.baseline = baseline
        ceiling.limit = limit
        return ceiling


def _limit_mb(n: int) -> str:
    """The limit as the host wrote it: `50`, or `0.5` (fractions are accepted)."""
    return f"{round(n / _MB, 3):g}"  # 0.55 MB is stored as a truncated byte count


def _growth_mb(n: int) -> str:
    """Growth, rounded **up** to 0.1 MB.

    The check fires only when growth is past the limit, so rounding to nearest
    printed "grew the process by 1 MB, past its 1 MB limit" for 1.03 MB. Rounded
    up, the figure shown is always above the limit shown.
    """
    return f"{math.ceil(n * 10 / _MB) / 10:.1f}".removesuffix(".0")


def limit_exceeded_message(current: int, ceiling: int) -> str:
    """The `RuntimeLimitExceeded` text, in the terms the host set (#1004).

    Starts with "Memory limit exceeded" whatever the form: embedders and tests
    match on it. A plain-int ceiling (set on a VM directly, with no limit
    recorded) keeps the absolute wording, since growth cannot be known.
    """
    if isinstance(ceiling, MemoryCeiling):
        return (
            f"Memory limit exceeded: this run grew the process by "
            f"{_growth_mb(current - ceiling.baseline)} MB, past its "
            f"{_limit_mb(ceiling.limit)} MB limit ({current // _MB} MB resident)"
        )
    return (
        f"Memory limit exceeded: the process reached {current // _MB} MB, "
        f"past its {ceiling // _MB} MB ceiling"
    )


def memory_metering_available() -> bool:
    """Can `max_memory_mb` be enforced here?

    Asked at construction so an unenforceable limit is **refused** rather than
    accepted and quietly ignored. A limit that is declared and not enforced is
    the pattern #473 and #478 were both filed for, and it is worse than no limit:
    it is a security control an operator believes they have.
    """
    return rss_bytes() is not None
