"""Run every companion's test suite against this checkout, before publishing.

Gate 10 validates nodus-lang against itself: eval scripts, adversarial probes,
the doc gate. None of that executes a *dependent*. Stage 6 does, but Stage 6 runs
**after** the PyPI upload, and PyPI is immutable.

v5.0.3 shipped through that gap. A change to `NodusRuntime.__init__` assigned
`self.memory_store`, and `nodus_sdk.NodusSDKRuntime` subclasses it with
`memory_store` as a *read-only property* holding its own vector store:

    AttributeError: property 'memory_store' of 'NodusSDKRuntime' object has no setter

Every construction of that subclass raised. nodus-sdk went from 99 passed to
29 failed / 10 errors, and it was found by the post-publish sweep — one release too
late. Running the same suites before the upload would have caught it, which is what
this does.

Usage::

    python -m tools.check_dependent_suites
    python -m tools.check_dependent_suites --only nodus-sdk nodus-mcp

Exit status is 0 only when every dependent suite passes. A companion whose checkout
is missing is reported and skipped, not silently ignored: an absent checkout means
the gate did not cover it.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO_ROOT, "src")

# Companions that import nodus-lang. Packages with no dependency on it cannot be
# broken by a nodus-lang change and are deliberately absent.
DEPENDENTS = {
    "nodus-mcp": r"C:\dev\nodus-mcp",
    "nodus-mcp-server": r"C:\dev\nodus-mcp-server",
    "nodus-extension": r"C:\dev\nodus-extension",
    "nodus-sdk": r"C:\dev\nodus-sdk",
    "nodus-native-memory-engine": r"C:\dev\nodus-native-memory-engine",
    "nodus-jupyter": r"C:\dev\nodus-jupyter",
}


def run_suite(name: str, path: str) -> tuple[str, str]:
    """Return (verdict, detail) for one companion."""
    if not os.path.isdir(path):
        return "MISSING", f"no checkout at {path}"
    env = dict(os.environ, PYTHONPATH=SRC)
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--tb=no"],
            cwd=path, env=env, capture_output=True, text=True, timeout=1800,
        )
    except subprocess.TimeoutExpired:
        return "TIMEOUT", "suite exceeded 30 minutes"
    tail = [ln for ln in proc.stdout.splitlines() if "passed" in ln or "failed" in ln]
    detail = tail[-1].strip() if tail else (proc.stdout or proc.stderr).strip()[-120:]
    return ("PASS" if proc.returncode == 0 else "FAIL"), detail


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", nargs="*", help="limit to these companions")
    args = parser.parse_args(argv)

    targets = {k: v for k, v in DEPENDENTS.items() if not args.only or k in args.only}
    print(f"Running {len(targets)} dependent suite(s) against {SRC}\n")

    results: dict[str, tuple[str, str]] = {}
    for name, path in targets.items():
        print(f"  {name} ...", flush=True)
        results[name] = run_suite(name, path)

    print()
    print(f"{'companion':<30} {'verdict':<9} detail")
    print("-" * 78)
    for name, (verdict, detail) in results.items():
        print(f"{name:<30} {verdict:<9} {detail}")

    failed = [n for n, (v, _) in results.items() if v == "FAIL"]
    missing = [n for n, (v, _) in results.items() if v in {"MISSING", "TIMEOUT"}]
    print()
    if failed:
        print(f"{len(failed)} dependent suite(s) fail against this checkout: {', '.join(failed)}")
        print("Do not publish. A break found here is one release cheaper than one found")
        print("by the post-publish sweep, which is how v5.0.3 shipped a broken nodus-sdk.")
        return 1
    if missing:
        print(f"Could not run: {', '.join(missing)}. An unrun suite is not a passing one.")
        return 2
    print(f"All {len(results)} dependent suites pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
