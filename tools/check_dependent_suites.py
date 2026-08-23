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
    python -m tools.check_dependent_suites --retry-failed

Exit status
-----------

    0   every dependent suite passed
    1   at least one *new* failure — do not publish
    2   a checkout was missing, or a suite timed out — an unrun suite is not a
        passing one, so this is not a pass
    3   every failure matched a recorded flake — still not a pass; re-run those
        suites serially before deciding

**Why a red run has to name the test** (#528). This gate's one instruction is
"do not publish", and until it named the failing test that instruction could
neither be acted on nor dismissed without leaving the tool and re-running the
companion by hand — the manual step the gate was written to replace. Worse, the
underlying reality is not binary: a suite can go red because the release broke it,
because a documented port-conflict flake fired, or because the host was loaded.
Those demand opposite responses.

So a red run now prints the failing node ids, says which of them match a recorded
flake, and points at a log holding the full output including tracebacks.

**A recorded flake never turns a red run green.** It changes the exit code from 1
to 3 and changes the advice, and that is all. Passing on a listed test would
rebuild "re-run until green" one level up, which is the failure this whole process
exists to prevent.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO_ROOT, "src")
LOG_DIR = os.path.join(REPO_ROOT, ".dependent-suites")
FLAKES_MANIFEST = os.path.join(REPO_ROOT, "tools", "dependent_flakes.json")

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

# pytest's short summary. `-rfE` is passed explicitly rather than relying on the
# default, because a companion's own pytest config can set `-r` and this parser
# must not depend on what each one happens to choose.
_SUMMARY_LINE = re.compile(r"^(FAILED|ERROR)\s+(\S+)")
_COUNT_LINE = re.compile(r"\b\d+ (?:passed|failed|error|errors|skipped)\b")


@dataclass
class SuiteResult:
    name: str
    verdict: str
    summary: str = ""
    failures: list[str] = field(default_factory=list)
    log_path: str | None = None
    known: list[str] = field(default_factory=list)
    new: list[str] = field(default_factory=list)
    retry_passed: list[str] = field(default_factory=list)
    retry_failed: list[str] = field(default_factory=list)
    retried: bool = False


def load_known_flaky() -> dict[str, list[dict]]:
    """Recorded flakes, or an empty map if the manifest is absent.

    Absence is not an error: the gate's job is running the suites, and it must
    not refuse to run because a triage aid is missing. It says so instead.
    """
    if not os.path.isfile(FLAKES_MANIFEST):
        return {}
    try:
        with open(FLAKES_MANIFEST, encoding="utf-8") as handle:
            return json.load(handle).get("known_flaky", {})
    except (OSError, json.JSONDecodeError) as exc:
        print(f"  ! could not read {FLAKES_MANIFEST}: {exc}", file=sys.stderr)
        return {}


def parse_failures(stdout: str) -> list[str]:
    """Node ids from pytest's short summary, `FAILED` and `ERROR` alike.

    A collection error reports as `ERROR path` with no `::test`, which is still
    the most useful thing to print — it names the file that would not import.
    """
    found: list[str] = []
    for line in stdout.splitlines():
        match = _SUMMARY_LINE.match(line.strip())
        if match:
            node = match.group(2)
            if node not in found:
                found.append(node)
    return found


def classify(failures: list[str], patterns: list[dict]) -> tuple[list[str], list[str]]:
    """Split failures into (known-flaky, new) by substring match on the node id."""
    known, new = [], []
    for node in failures:
        if any(entry.get("match", "") and entry["match"] in node for entry in patterns):
            known.append(node)
        else:
            new.append(node)
    return known, new


def _summary_of(stdout: str, stderr: str) -> str:
    tail = [ln.strip() for ln in stdout.splitlines() if _COUNT_LINE.search(ln)]
    if tail:
        return tail[-1]
    return (stdout or stderr).strip()[-120:]


def _write_log(name: str, proc: subprocess.CompletedProcess) -> str | None:
    """Persist full output so triage never requires re-running.

    Written even on success: a passing run's timings are what a later flake gets
    compared against.
    """
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        path = os.path.join(LOG_DIR, f"{name}.log")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(proc.stdout or "")
            if proc.stderr:
                handle.write("\n--- stderr ---\n")
                handle.write(proc.stderr)
        return path
    except OSError:
        return None


def _pytest(path: str, extra: list[str]) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=SRC)
    return subprocess.run(
        # `--tb=short` rather than `--tb=no`: the console output is parsed and
        # summarised either way, and the log is worthless for triage without a
        # traceback in it.
        [sys.executable, "-m", "pytest", "-q", "--tb=short", "-rfE", *extra],
        cwd=path, env=env, capture_output=True, text=True, timeout=1800,
    )


def run_suite(name: str, path: str, known_patterns: list[dict], *,
              retry: bool = False) -> SuiteResult:
    if not os.path.isdir(path):
        return SuiteResult(name, "MISSING", summary=f"no checkout at {path}")
    try:
        proc = _pytest(path, [])
    except subprocess.TimeoutExpired:
        return SuiteResult(name, "TIMEOUT", summary="suite exceeded 30 minutes")

    result = SuiteResult(
        name=name,
        verdict="PASS" if proc.returncode == 0 else "FAIL",
        summary=_summary_of(proc.stdout, proc.stderr),
        failures=parse_failures(proc.stdout),
        log_path=_write_log(name, proc),
    )
    result.known, result.new = classify(result.failures, known_patterns)

    if retry and result.verdict == "FAIL" and result.failures:
        # Opt-in, never automatic. An automatic retry in a publish gate erodes
        # into re-run-until-green; asked for explicitly it is evidence. Either
        # way it cannot change the verdict below.
        try:
            again = _pytest(path, ["--lf"])
        except subprocess.TimeoutExpired:
            return result
        result.retried = True
        still_failing = parse_failures(again.stdout)
        result.retry_failed = still_failing
        result.retry_passed = [n for n in result.failures if n not in still_failing]
    return result


def _print_report(results: list[SuiteResult], have_manifest: bool) -> None:
    print()
    print(f"{'companion':<30} {'verdict':<9} detail")
    print("-" * 78)
    for r in results:
        print(f"{r.name:<30} {r.verdict:<9} {r.summary}")
    print()

    for r in results:
        if r.verdict != "FAIL":
            continue
        print(f"{r.name}:")
        if not r.failures:
            print("    exited non-zero but printed no FAILED/ERROR line —")
            print("    look at the log; this is usually a collection or config error.")
        for node in r.new:
            print(f"    NEW    {node}")
        for node in r.known:
            print(f"    known  {node}  (recorded flake)")
        if r.retried:
            for node in r.retry_passed:
                print(f"    retry  {node} PASSED on re-run (first result stands)")
            for node in r.retry_failed:
                print(f"    retry  {node} failed again")
        if r.log_path:
            print(f"    log    {r.log_path}")
        print()

    if not have_manifest and any(r.verdict == "FAIL" for r in results):
        print(f"(no {os.path.relpath(FLAKES_MANIFEST, REPO_ROOT)} — every failure is")
        print(" reported as new, which is the safe direction.)")
        print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", nargs="*", help="limit to these companions")
    parser.add_argument(
        "--retry-failed", action="store_true",
        help="after a red suite, re-run only its failed tests (--lf) and report both "
             "results. Never changes the verdict.",
    )
    args = parser.parse_args(argv)

    known_flaky = load_known_flaky()
    have_manifest = os.path.isfile(FLAKES_MANIFEST)
    targets = {k: v for k, v in DEPENDENTS.items() if not args.only or k in args.only}
    print(f"Running {len(targets)} dependent suite(s) against {SRC}\n")

    results: list[SuiteResult] = []
    for name, path in targets.items():
        print(f"  {name} ...", flush=True)
        results.append(
            run_suite(name, path, known_flaky.get(name, []), retry=args.retry_failed)
        )

    _print_report(results, have_manifest)

    failed = [r for r in results if r.verdict == "FAIL"]
    unrun = [r for r in results if r.verdict in {"MISSING", "TIMEOUT"}]
    with_new = [r for r in failed if r.new or not r.failures]

    if with_new:
        names = ", ".join(r.name for r in with_new)
        print(f"{len(with_new)} dependent suite(s) fail against this checkout: {names}")
        print("Do not publish. A break found here is one release cheaper than one found")
        print("by the post-publish sweep, which is how v5.0.3 shipped a broken nodus-sdk.")
        return 1
    if failed:
        names = ", ".join(r.name for r in failed)
        print(f"{len(failed)} suite(s) red, and every failure matches a recorded flake: {names}")
        print("Not a pass. Re-run those suites serially, with nothing else running, and")
        print("publish only if they go green — a recorded flake is a reason to look")
        print("again, never a reason to skip looking.")
        return 3
    if unrun:
        names = ", ".join(r.name for r in unrun)
        print(f"Could not run: {names}. An unrun suite is not a passing one.")
        return 2
    print(f"All {len(results)} dependent suites pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
