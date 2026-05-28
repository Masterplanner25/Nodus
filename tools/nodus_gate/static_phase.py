"""Static phase: extract documented symbols and verify they exist in the runtime."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from tools.nodus_gate.markdown_parser import CodeBlock, collect_doc_files, extract_blocks


# -- Known symbol sets -------------------------------------------------------

def _builtin_names() -> set[str]:
    """Return the set of built-in function names."""
    sys.path.insert(0, str(Path(__file__).parents[2] / "src"))
    from nodus.builtins.nodus_builtins import BUILTIN_NAMES
    return set(BUILTIN_NAMES)


def _stdlib_modules() -> set[str]:
    """Return set of std: module short names (e.g. 'env', 'http', ...)."""
    stdlib_dir = Path(__file__).parents[2] / "src" / "nodus" / "stdlib"
    modules: set[str] = set()
    if stdlib_dir.is_dir():
        for f in stdlib_dir.glob("*.nd"):
            modules.add(f.stem)
    return modules


def _cli_commands() -> set[str]:
    """Return set of known CLI commands."""
    return {
        "run", "check", "fmt", "ast", "dis", "debug", "profile", "test",
        "repl", "graph", "serve", "lsp", "dap", "snapshot", "snapshots",
        "restore", "worker", "workflow", "goal-run", "goal-plan", "goal-resume",
        "tool-call", "agent-call", "memory-get", "memory-put", "memory-delete",
        "memory-keys", "package-init", "package-install", "package-update",
        "package-list", "cache", "add", "remove", "init", "install", "update",
        "deps", "login", "logout", "publish", "status",
    }


# -- Symbol patterns ---------------------------------------------------------

# func(...) calls — match word chars followed by (
_FUNC_CALL_RE = re.compile(r'\b([a-z_][a-z0-9_]*)\s*\(', re.IGNORECASE)

# import "std:name" or import "std:name" as alias
_IMPORT_RE = re.compile(r'\bimport\s+"std:([a-z][a-z0-9_-]*)(?:/[^"]*)?"\s*(?:as\s+\w+)?')

# module.function(...) calls
_QUALIFIED_RE = re.compile(r'\b([a-z][a-z0-9_]*)\.([a-z_][a-z0-9_]*)\s*\(', re.IGNORECASE)

# nodus <subcommand> mentions in code blocks (after line start, $, or whitespace)
_CLI_RE = re.compile(r'(?:^|[\s$`])nodus(?:_gate)?\s+([a-z][a-z0-9_-]+)', re.MULTILINE)


@dataclass
class StaticFinding:
    kind: str        # "missing_function", "missing_module", "missing_cli"
    symbol: str      # the extracted symbol
    file_path: str
    line: int
    message: str


@dataclass
class StaticResult:
    findings: list[StaticFinding] = field(default_factory=list)
    scanned_files: int = 0
    total_symbols: int = 0


def run_static_phase(
    root: str,
    *,
    include_design: bool = False,
    allowlist: set[str] | None = None,
) -> StaticResult:
    """Run the static phase against all doc files under root."""
    result = StaticResult()
    allowlist = allowlist or set()

    builtins = _builtin_names()
    stdlib = _stdlib_modules()
    cli_cmds = _cli_commands()

    # Build qualified function map from stdlib modules
    # e.g. "env.get", "http.post", etc.
    qualified = _build_qualified_set(stdlib)

    doc_files = collect_doc_files(root, include_design=include_design)
    result.scanned_files = len(doc_files)

    seen_symbols: set[tuple] = set()  # (kind, symbol) — deduplicate

    for file_path in doc_files:
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
                lines = content.splitlines()
        except OSError:
            continue

        blocks = extract_blocks(file_path)

        for block in blocks:
            if block.is_skip:
                continue
            _check_block(block, builtins, stdlib, cli_cmds, qualified,
                         allowlist, seen_symbols, result)

        # Also check prose (non-code sections) for import and CLI patterns
        _check_prose(file_path, lines, stdlib, cli_cmds, allowlist,
                     seen_symbols, result)

    return result


def _build_qualified_set(stdlib_modules: set[str]) -> set[str]:
    """Build set of qualified function names from stdlib .nd files."""
    qualified: set[str] = set()
    stdlib_dir = Path(__file__).parents[2] / "src" / "nodus" / "stdlib"
    for mod_name in stdlib_modules:
        nd_file = stdlib_dir / f"{mod_name}.nd"
        if not nd_file.exists():
            continue
        try:
            content = nd_file.read_text(encoding="utf-8")
        except OSError:
            continue
        for m in re.finditer(r'^fn\s+(\w+)\s*\(', content, re.MULTILINE):
            qualified.add(f"{mod_name}.{m.group(1)}")
    return qualified


def _check_block(
    block: CodeBlock, builtins: set[str], stdlib: set[str],
    cli_cmds: set[str], qualified: set[str],
    allowlist: set[str], seen: set, result: StaticResult,
) -> None:
    src = block.source

    # Imports
    for m in _IMPORT_RE.finditer(src):
        mod = m.group(1)
        key = ("missing_module", f"std:{mod}")
        if mod not in stdlib and key not in seen and f"symbol:std:{mod}" not in allowlist:
            seen.add(key)
            result.total_symbols += 1
            result.findings.append(StaticFinding(
                kind="missing_module",
                symbol=f"std:{mod}",
                file_path=block.file_path,
                line=block.start_line,
                message=f"Module 'std:{mod}' is documented but not found in stdlib/",
            ))
        result.total_symbols += 1

    # CLI commands
    for m in _CLI_RE.finditer(src):
        cmd = m.group(1)
        key = ("missing_cli", cmd)
        if cmd not in cli_cmds and key not in seen and f"symbol:nodus {cmd}" not in allowlist:
            seen.add(key)
            result.total_symbols += 1
            result.findings.append(StaticFinding(
                kind="missing_cli",
                symbol=f"nodus {cmd}",
                file_path=block.file_path,
                line=block.start_line,
                message=f"CLI subcommand 'nodus {cmd}' is documented but not found",
            ))

    # Qualified calls (module.function)
    for m in _QUALIFIED_RE.finditer(src):
        mod, fn = m.group(1), m.group(2)
        q = f"{mod}.{fn}"
        key = ("missing_qualified", q)
        if (mod in stdlib and q not in qualified
                and key not in seen
                and f"symbol:{q}" not in allowlist):
            seen.add(key)
            result.total_symbols += 1
            result.findings.append(StaticFinding(
                kind="missing_qualified",
                symbol=q,
                file_path=block.file_path,
                line=block.start_line,
                message=f"Function '{q}' is documented but not found in stdlib/{mod}.nd",
            ))


def _strip_code_fences(text: str) -> str:
    """Remove all fenced code blocks from text, leaving only prose."""
    return re.sub(r'```.*?```', '', text, flags=re.DOTALL)


def _check_prose(
    file_path: str, lines: list[str], stdlib: set[str],
    cli_cmds: set[str], allowlist: set[str],
    seen: set, result: StaticResult,
) -> None:
    """Check import statements and CLI references in prose text (not in code fences)."""
    full = _strip_code_fences("\n".join(lines))

    for m in _IMPORT_RE.finditer(full):
        mod = m.group(1)
        key = ("missing_module", f"std:{mod}")
        if mod not in stdlib and key not in seen and f"symbol:std:{mod}" not in allowlist:
            seen.add(key)
            result.total_symbols += 1
            line_no = full[:m.start()].count("\n") + 1
            result.findings.append(StaticFinding(
                kind="missing_module",
                symbol=f"std:{mod}",
                file_path=file_path,
                line=line_no,
                message=f"Module 'std:{mod}' is documented but not found in stdlib/",
            ))
