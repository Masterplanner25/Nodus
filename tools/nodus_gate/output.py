"""Output formatting for nodus_gate (pretty, plain, JSON)."""

from __future__ import annotations

import json
import os
import sys
from typing import Any


def _is_tty() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _c(text: str, code: str, *, use_color: bool) -> str:
    return f"{code}{text}{_RESET}" if use_color else text


def _rel(path: str, root: str) -> str:
    try:
        return os.path.relpath(path, root)
    except ValueError:
        return path


# -- Static phase output ------------------------------------------------------

def format_static(result, root: str, *, use_color: bool, verbose: bool, quiet: bool) -> str:
    lines = []
    if not quiet:
        lines.append(f"Scanned {result.scanned_files} document(s), found {result.total_symbols} symbol(s)")
        lines.append("")

    for f in result.findings:
        rel = _rel(f.file_path, root)
        lines.append(_c(f"FAIL {rel}:{f.line}", _RED, use_color=use_color))
        lines.append(f"  {f.message}")
        lines.append("")

    n_fail = len(result.findings)
    n_ok = result.total_symbols - n_fail
    if not quiet:
        status = _c("PASS", _GREEN, use_color=use_color) if n_fail == 0 else _c("FAIL", _RED, use_color=use_color)
        lines.append(f"Static: {status} — {n_fail} failure(s), {n_ok}/{result.total_symbols} symbols valid")
    return "\n".join(lines)


def format_runtime(result, root: str, *, use_color: bool, verbose: bool, quiet: bool) -> str:
    lines = []
    if not quiet:
        lines.append(f"Scanned {result.scanned_files} document(s), ran {result.total_blocks} block(s)")
        lines.append("")

    for f in result.findings:
        rel = _rel(f.file_path, root)
        lines.append(_c(f"FAIL {rel}:{f.start_line}", _RED, use_color=use_color))
        lines.append(f"  {f.message}")
        if f.actual_output or f.expected_output:
            if f.expected_output:
                lines.append("  Expected:")
                for ln in f.expected_output.splitlines():
                    lines.append(f"    {ln}")
            if f.actual_output:
                lines.append("  Actual:")
                for ln in f.actual_output.splitlines()[:20]:
                    lines.append(f"    {ln}")
        lines.append("")

    n_fail = len(result.findings)
    if not quiet:
        status = _c("PASS", _GREEN, use_color=use_color) if n_fail == 0 else _c("FAIL", _RED, use_color=use_color)
        lines.append(f"Runtime: {status} — {n_fail} failure(s), {result.passed}/{result.total_blocks} blocks passed")
    return "\n".join(lines)


def format_closed_issues(result, root: str, *, use_color: bool, verbose: bool, quiet: bool) -> str:
    lines = []
    if not quiet:
        lines.append(f"Scanning CHANGELOG [{result.scanned_section}] section")
        lines.append(f"Found {len(result.issues)} issue reference(s)")
        lines.append("")

    for iss in result.issues:
        if iss.test_path is None:
            sym = _c("?", _YELLOW, use_color=use_color)
            lines.append(f"  {sym} #{iss.issue_number}: no test found")
            lines.append(f"    {iss.error_msg}")
        elif iss.passed is True:
            sym = _c("PASS", _GREEN, use_color=use_color)
            rel = _rel(iss.test_path, root)
            lines.append(f"  {sym} #{iss.issue_number}: {rel}")
        elif iss.passed is False:
            sym = _c("FAIL", _RED, use_color=use_color)
            rel = _rel(iss.test_path, root)
            lines.append(f"  {sym} #{iss.issue_number}: {rel}")
            for err_line in iss.error_msg.splitlines()[:5]:
                lines.append(f"    {err_line}")
        lines.append("")

    if not quiet:
        n_miss = result.missing_tests
        n_fail = result.failed
        n_ok = result.passed
        total = len(result.issues)
        status_ok = (n_miss == 0 and n_fail == 0)
        status = _c("PASS", _GREEN, use_color=use_color) if status_ok else _c("FAIL", _RED, use_color=use_color)
        lines.append(
            f"Closed-issues: {status} — {n_ok} passed, {n_fail} failed, {n_miss} missing"
            f" (of {total} referenced issues)"
        )
    return "\n".join(lines)


def format_json_results(
    static=None, runtime=None, closed=None
) -> str:
    obj: dict[str, Any] = {"phases": {}}

    if static is not None:
        obj["phases"]["static"] = {
            "scanned_files": static.scanned_files,
            "total_symbols": static.total_symbols,
            "failures": len(static.findings),
            "findings": [
                {"kind": f.kind, "symbol": f.symbol,
                 "file": f.file_path, "line": f.line, "message": f.message}
                for f in static.findings
            ],
        }

    if runtime is not None:
        obj["phases"]["runtime"] = {
            "scanned_files": runtime.scanned_files,
            "total_blocks": runtime.total_blocks,
            "passed": runtime.passed,
            "failures": len(runtime.findings),
            "findings": [
                {"kind": f.kind, "file": f.file_path, "line": f.start_line,
                 "message": f.message, "actual": f.actual_output,
                 "expected": f.expected_output}
                for f in runtime.findings
            ],
        }

    if closed is not None:
        obj["phases"]["closed_issues"] = {
            "section": closed.scanned_section,
            "total": len(closed.issues),
            "passed": closed.passed,
            "failed": closed.failed,
            "missing": closed.missing_tests,
            "issues": [
                {"number": i.issue_number, "test": i.test_path,
                 "passed": i.passed, "error": i.error_msg}
                for i in closed.issues
            ],
        }

    total_failures = sum([
        len(static.findings) if static else 0,
        len(runtime.findings) if runtime else 0,
        (closed.failed + closed.missing_tests) if closed else 0,
    ])
    obj["total_failures"] = total_failures
    obj["passed"] = total_failures == 0
    return json.dumps(obj, indent=2) + "\n"
