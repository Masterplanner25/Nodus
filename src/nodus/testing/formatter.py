"""Output formatters for the Nodus test runner."""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Sequence

from nodus.testing.runner import TestResult


def _is_tty() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


# -- ANSI colour helpers ---------------------------------------------------

_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_GREY = "\033[90m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _c(text: str, code: str, *, use_color: bool) -> str:
    return f"{code}{text}{_RESET}" if use_color else text


# -- Aggregation -----------------------------------------------------------

@dataclass
class RunSummary:
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    duration_ms: float = 0.0


def _summarize(results: Sequence[TestResult]) -> RunSummary:
    s = RunSummary()
    for r in results:
        s.total += 1
        s.duration_ms += r.duration_ms
        if r.status == "pass":
            s.passed += 1
        elif r.status == "fail":
            s.failed += 1
        elif r.status == "skip":
            s.skipped += 1
        else:
            s.errors += 1
    return s


# -- Pretty / plain --------------------------------------------------------

def format_text(results: Sequence[TestResult], *, use_color: bool | None = None,
                verbose: bool = False, quiet: bool = False) -> str:
    if use_color is None:
        use_color = _is_tty()

    lines = []
    prev_file: str | None = None
    failures: list[TestResult] = []

    if not quiet:
        for r in results:
            if r.source_path != prev_file:
                lines.append(f"\n {_c('RUN', _BOLD, use_color=use_color)}  {r.source_path or '<source>'}")
                prev_file = r.source_path

            if r.status == "pass":
                if verbose:
                    symbol = _c("✓", _GREEN, use_color=use_color)
                    lines.append(f"  {symbol} {r.case_name} ({r.duration_ms:.0f}ms)")
            elif r.status == "skip":
                symbol = _c("-", _YELLOW, use_color=use_color)
                lines.append(f"  {symbol} {r.case_name} (skipped)")
            else:
                symbol = _c("✗", _RED, use_color=use_color)
                lines.append(f"  {symbol} {r.case_name} ({r.duration_ms:.0f}ms)")
                failures.append(r)

    # Failure details
    if failures:
        lines.append("")
        for r in failures:
            lines.append(_c(f"FAIL: {' > '.join(r.suite_path)} > {r.case_name}", _RED, use_color=use_color))
            if r.source_path:
                lines.append(f"  ({r.source_path})")
            if r.failure_message:
                for line in r.failure_message.splitlines():
                    lines.append(f"  {line}")
            lines.append("")

    summary = _summarize(results)
    duration_s = summary.duration_ms / 1000
    lines.append("")
    total_line = f"Tests: {summary.total} total"
    parts = []
    if summary.passed:
        parts.append(_c(f"{summary.passed} passed", _GREEN, use_color=use_color))
    if summary.failed:
        parts.append(_c(f"{summary.failed} failed", _RED, use_color=use_color))
    if summary.errors:
        parts.append(_c(f"{summary.errors} errors", _RED, use_color=use_color))
    if summary.skipped:
        parts.append(_c(f"{summary.skipped} skipped", _YELLOW, use_color=use_color))
    if parts:
        total_line += ", " + ", ".join(parts)
    lines.append(total_line)
    lines.append(f"Time:  {duration_s:.2f}s")
    lines.append("")
    return "\n".join(lines)


# -- JSON Lines -----------------------------------------------------------

def format_json(results: Sequence[TestResult]) -> str:
    lines = []
    for r in results:
        obj: dict = {
            "type": "test",
            "suite": " > ".join(r.suite_path),
            "case": r.case_name,
            "status": r.status,
            "duration_ms": round(r.duration_ms, 2),
        }
        if r.status in ("fail", "error"):
            obj["failure"] = {
                "kind": r.failure_kind,
                "message": r.failure_message,
            }
        if r.status == "skip" and r.skip_reason:
            obj["skip_reason"] = r.skip_reason
        if r.source_path:
            obj["source"] = r.source_path
        lines.append(json.dumps(obj))
    summary = _summarize(results)
    lines.append(json.dumps({
        "type": "summary",
        "tests_total": summary.total,
        "tests_passed": summary.passed,
        "tests_failed": summary.failed,
        "tests_skipped": summary.skipped,
        "tests_errors": summary.errors,
        "duration_ms": round(summary.duration_ms, 2),
    }))
    return "\n".join(lines) + "\n"


# -- JUnit XML ------------------------------------------------------------

def format_junit(results: Sequence[TestResult], suite_name: str = "nodus") -> str:
    by_suite: dict[str, list[TestResult]] = {}
    for r in results:
        key = " > ".join(r.suite_path) or "(no suite)"
        by_suite.setdefault(key, []).append(r)

    testsuites = ET.Element("testsuites")
    for suite_path, suite_results in by_suite.items():
        summary = _summarize(suite_results)
        ts = ET.SubElement(testsuites, "testsuite",
                           name=suite_path,
                           tests=str(summary.total),
                           failures=str(summary.failed),
                           errors=str(summary.errors),
                           skipped=str(summary.skipped),
                           time=f"{summary.duration_ms / 1000:.3f}")
        for r in suite_results:
            tc = ET.SubElement(ts, "testcase",
                               name=r.case_name,
                               classname=suite_path.replace(" > ", "."),
                               time=f"{r.duration_ms / 1000:.3f}")
            if r.status == "skip":
                sk = ET.SubElement(tc, "skipped")
                if r.skip_reason:
                    sk.set("message", r.skip_reason)
            elif r.status in ("fail", "error"):
                el = ET.SubElement(tc, "failure" if r.status == "fail" else "error")
                el.set("type", r.failure_kind or r.status)
                el.set("message", r.failure_message[:200] if r.failure_message else "")
                el.text = r.failure_message

    ET.indent(testsuites, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(testsuites, encoding="unicode") + "\n"
