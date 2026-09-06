"""Measure what #173 is about, rather than quoting a number that goes stale.

Two figures, and they are different questions:

- **Throughput** -- how fast the VM executes instructions once running. This is
  the ceiling #173 names, and it is bounded by CPython's own dispatch loop.
- **Startup** -- how long before a program executes at all. This is what blocks
  #173's PyPy path: PyPy's interpreter starts *faster* than CPython's, and the
  adoption cost is importing Nodus's own module tree, which is run-once code the
  JIT never warms.

The instruction count comes from the VM's own counter rather than an estimate
per loop iteration. An earlier reading of this benchmark assumed "about 6
instructions per iteration" and was wrong by nearly 3x -- it is 17.

Run it::

    PYTHONPATH="src" python -m tools.benchmark_runtime
    PYTHONPATH="src" python -m tools.benchmark_runtime --quick

Numbers are machine-specific and are not asserted anywhere. Nothing here is a
gate: it exists so the figure in an issue or a document can be re-derived
instead of transcribed.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"

LOOP = """
fn compute(n) {
    let i = 0i
    let sum = 0i
    while (i < n) { sum = sum + i; i = i + 1i }
    return sum
}
print(compute(%d))
"""


def _runtime():
    sys.path.insert(0, str(_SRC))
    from nodus.runtime.embedding import NodusRuntime

    return NodusRuntime


def throughput(sizes, reps: int) -> None:
    NodusRuntime = _runtime()

    def once(n):
        rt = NodusRuntime(timeout_ms=None, max_steps=None)
        start = time.perf_counter()
        result = rt.run_source(LOOP % n)
        elapsed = time.perf_counter() - start
        if not result.get("ok"):
            raise SystemExit(f"benchmark program failed: {result.get('error')}")
        return elapsed, rt.get_execution_stats()["instructions_executed"]

    once(1000)  # warm the compiler and its lazy imports
    print(f"throughput -- {sys.implementation.name} {sys.version.split()[0]}")
    for n in sizes:
        best, instructions = None, 0
        for _ in range(reps):
            elapsed, instructions = once(n)
            best = elapsed if best is None else min(best, elapsed)
        print(
            f"  n={n:>9,}  {best:6.3f}s  {n / best / 1000:7.1f}K iter/s  "
            f"{instructions / best / 1000:9.1f}K instr/s  "
            f"({instructions / n:.1f} instr/iter)"
        )


def startup(reps: int) -> None:
    """Cost before a program runs. Subprocesses, because that is the real cost."""
    env = dict(os.environ, PYTHONPATH=str(_SRC))
    hello = _REPO_ROOT / ".benchmark_hello.nd"
    hello.write_text('print("hi")\n', encoding="utf-8")
    cases = [
        ([sys.executable, "-c", "pass"], "bare interpreter"),
        ([sys.executable, "-c", "import nodus"], "import nodus"),
        ([sys.executable, "-c", "import nodus.cli.cli"], "import nodus.cli.cli"),
        ([sys.executable, str(_REPO_ROOT / "nodus.py"), "--version"], "nodus --version"),
        ([sys.executable, str(_REPO_ROOT / "nodus.py"), "run", str(hello)], "nodus run hello.nd"),
    ]
    print("\nstartup -- best of "
          f"{reps}, subprocess wall clock")
    try:
        for cmd, label in cases:
            best = None
            for _ in range(reps):
                start = time.perf_counter()
                subprocess.run(cmd, cwd=_REPO_ROOT, env=env, capture_output=True)
                elapsed = time.perf_counter() - start
                best = elapsed if best is None else min(best, elapsed)
            print(f"  {label:24} {best * 1000:7.0f} ms")
    finally:
        hello.unlink(missing_ok=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quick", action="store_true",
                        help="one small size, fewer repetitions")
    parser.add_argument("--skip-startup", action="store_true")
    args = parser.parse_args(argv)

    sizes = (50_000,) if args.quick else (50_000, 200_000, 1_000_000)
    throughput(sizes, reps=1 if args.quick else 3)
    if not args.skip_startup:
        startup(reps=2 if args.quick else 3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
