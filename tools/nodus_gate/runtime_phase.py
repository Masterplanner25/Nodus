"""Runtime phase: execute code blocks and verify output."""

from __future__ import annotations

import os
import re
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

from tools.nodus_gate.markdown_parser import CodeBlock, collect_doc_files, extract_blocks


@dataclass
class RuntimeFinding:
    kind: str          # "error", "output_mismatch", "timeout", "no_expected_output"
    file_path: str
    start_line: int
    message: str
    actual_output: str = ""
    expected_output: str = ""


@dataclass
class RuntimeResult:
    findings: list[RuntimeFinding] = field(default_factory=list)
    scanned_files: int = 0
    total_blocks: int = 0
    passed: int = 0


def _normalize_output(text: str) -> str:
    """Normalize output for comparison: strip trailing whitespace per line."""
    lines = text.splitlines()
    stripped = [line.rstrip() for line in lines]
    # Remove leading/trailing blank lines
    while stripped and not stripped[0]:
        stripped.pop(0)
    while stripped and not stripped[-1]:
        stripped.pop()
    # Strip ANSI codes
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    return "\n".join(ansi_escape.sub("", line) for line in stripped)


def _run_block_with_timeout(
    source: str, timeout_ms: int
) -> tuple[str, str, Exception | None]:
    """Run Nodus source in a fresh VM. Returns (stdout, stderr, error_or_None)."""
    # Import lazily to avoid circular issues
    sys.path.insert(0, str(Path(__file__).parents[2] / "src"))
    from nodus.runtime.embedding import NodusRuntime

    result_holder: list = [None]
    error_holder: list = [None]

    def run_it() -> None:
        try:
            runtime = NodusRuntime(
                timeout_ms=timeout_ms,
                max_steps=1_000_000,
                allow_input=False,
            )
            res = runtime.run_source(source, filename="<gate>")
            result_holder[0] = res
        except Exception as exc:
            error_holder[0] = exc

    t = threading.Thread(target=run_it, daemon=True)
    t.start()
    t.join(timeout=timeout_ms / 1000 + 2.0)

    if t.is_alive():
        return "", "", TimeoutError(f"Block exceeded {timeout_ms}ms timeout")

    if error_holder[0]:
        return "", "", error_holder[0]

    res = result_holder[0]
    if res is None:
        return "", "", RuntimeError("Runner returned no result")

    stdout = res.get("stdout", "")
    stderr = res.get("stderr", "")
    if not res.get("ok"):
        errors = res.get("errors") or []
        msg = (errors[0].get("message") if errors else "") or res.get("error", {}).get("message", "unknown error")
        return stdout, stderr, RuntimeError(msg)

    return stdout, stderr, None


def run_runtime_phase(
    root: str,
    *,
    include_design: bool = False,
    allowlist: set[str] | None = None,
    verbose: bool = False,
) -> RuntimeResult:
    """Run all executable code blocks in the scanned documents."""
    result = RuntimeResult()
    allowlist = allowlist or set()

    doc_files = collect_doc_files(root, include_design=include_design)
    result.scanned_files = len(doc_files)

    for file_path in doc_files:
        blocks = extract_blocks(file_path)
        for block in blocks:
            if not block.should_run:
                continue
            result.total_blocks += 1
            allow_key = "block:" + os.path.relpath(block.file_path, root).replace("\\", "/") + f":{block.start_line}"
            if allow_key in allowlist:
                result.passed += 1
                continue
            _run_one_block(block, result, root, verbose=verbose)

    return result


def _run_one_block(
    block: CodeBlock, result: RuntimeResult, root: str, *, verbose: bool
) -> None:
    stdout, stderr, error = _run_block_with_timeout(block.source, block.timeout_ms)

    if isinstance(error, TimeoutError):
        result.findings.append(RuntimeFinding(
            kind="timeout",
            file_path=block.file_path,
            start_line=block.start_line,
            message=str(error),
        ))
        return

    if error is not None:
        result.findings.append(RuntimeFinding(
            kind="error",
            file_path=block.file_path,
            start_line=block.start_line,
            message=f"Block raised error: {error}",
            actual_output=stdout,
        ))
        return

    if block.expect_output:
        if block.expected_output is None:
            result.findings.append(RuntimeFinding(
                kind="no_expected_output",
                file_path=block.file_path,
                start_line=block.start_line,
                message="nodus-expect=output block has no Output: block following it",
            ))
            return

        actual = _normalize_output(stdout)
        expected = _normalize_output(block.expected_output)
        if actual != expected:
            result.findings.append(RuntimeFinding(
                kind="output_mismatch",
                file_path=block.file_path,
                start_line=block.start_line,
                message="Output does not match expected",
                actual_output=actual,
                expected_output=expected,
            ))
            return

    result.passed += 1
