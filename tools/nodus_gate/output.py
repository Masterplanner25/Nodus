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


def format_contracts(result, *, use_color: bool, verbose: bool, quiet: bool) -> str:
    lines = []
    if not quiet:
        lines.append(f"Ran {result.checks_run} contract infrastructure check(s)")
        lines.append("")

    for f in result.findings:
        lines.append(_c(f"FAIL {f.message}", _RED, use_color=use_color))
        if f.detail:
            lines.append(f"  {f.detail}")
        lines.append("")

    if not quiet:
        n_fail = len(result.findings)
        status = _c("PASS", _GREEN, use_color=use_color) if n_fail == 0 else _c("FAIL", _RED, use_color=use_color)
        lines.append(f"Contracts: {status} — {result.passed}/{result.checks_run} checks passed")
    return "\n".join(lines)


def format_consumers(result, *, use_color: bool, verbose: bool, quiet: bool) -> str:
    """A tick per consumer, and what to do about the ones that do not have one."""
    lines = []
    if result.error:
        lines.append(_c(f"FAIL {result.error}", _RED, use_color=use_color))
        return "\n".join(lines)

    if not quiet:
        lines.append(f"Checked {result.checks_run} non-PyPI consumer(s) against this tree")
        lines.append("")

    for s_ in result.statuses:
        if s_.in_step:
            mark = _c("[ok]", _GREEN, use_color=use_color)
            lines.append(f"  {mark} {s_.name} ({s_.published}) — {s_.tracks} unchanged")
            if verbose:
                lines.append(f"       {s_.kind}")
        else:
            mark = _c("[--]", _YELLOW, use_color=use_color)
            lines.append(f"  {mark} {s_.name} ({s_.published}) — NEEDS REPUBLISH")
            lines.append(f"       {s_.tracks} moved: {s_.expected} -> {s_.actual}")
            if s_.why:
                lines.append(f"       {s_.why}")
            if s_.republish:
                lines.append(f"       how: {s_.republish}")
        lines.append("")

    if not quiet:
        n_stale = len(result.stale)
        if n_stale == 0:
            status = _c("PASS", _GREEN, use_color=use_color)
            lines.append(f"Consumers: {status} — {result.passed}/{result.checks_run} in step")
        else:
            status = _c("STALE", _YELLOW, use_color=use_color)
            lines.append(
                f"Consumers: {status} — {result.passed}/{result.checks_run} in step, "
                f"{n_stale} need republishing (advisory; --strict to fail)"
            )
    return "\n".join(lines)


def format_opcodes(result, *, use_color: bool, verbose: bool, quiet: bool) -> str:
    lines = []
    if not quiet:
        lines.append(
            f"Ran {result.checks_run} opcode inventory check(s) against "
            f"{result.dispatch_count} dispatched opcode(s), "
            f"BYTECODE_VERSION {result.bytecode_version}"
        )
        lines.append("")

    for f in result.findings:
        lines.append(_c(f"FAIL {f.message}", _RED, use_color=use_color))
        if f.detail:
            lines.append(f"  {f.detail}")
        lines.append("")

    if not quiet:
        n_fail = len(result.findings)
        status = _c("PASS", _GREEN, use_color=use_color) if n_fail == 0 else _c("FAIL", _RED, use_color=use_color)
        lines.append(f"Opcodes: {status} — {result.passed}/{result.checks_run} checks passed")
    return "\n".join(lines)


def format_json_results(
    static=None, runtime=None, closed=None, contracts=None, opcodes=None
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

    if contracts is not None:
        obj["phases"]["contracts"] = {
            "checks_run": contracts.checks_run,
            "passed": contracts.passed,
            "failures": len(contracts.findings),
            "findings": [
                {"message": f.message, "detail": f.detail}
                for f in contracts.findings
            ],
        }

    if opcodes is not None:
        obj["phases"]["opcodes"] = {
            "checks_run": opcodes.checks_run,
            "passed": opcodes.passed,
            "dispatch_count": opcodes.dispatch_count,
            "bytecode_version": opcodes.bytecode_version,
            "failures": len(opcodes.findings),
            "findings": [
                {"message": f.message, "detail": f.detail}
                for f in opcodes.findings
            ],
        }

    total_failures = sum([
        len(static.findings) if static else 0,
        len(runtime.findings) if runtime else 0,
        (closed.failed + closed.missing_tests) if closed else 0,
        len(contracts.findings) if contracts else 0,
        len(opcodes.findings) if opcodes else 0,
    ])
    obj["total_failures"] = total_failures
    obj["passed"] = total_failures == 0
    return json.dumps(obj, indent=2) + "\n"
