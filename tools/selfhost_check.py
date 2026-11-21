"""Check the self-hosted Nodus frontend against the Python one, and measure it (#173).

`examples/selfhost/` holds a lexer and a parser written in Nodus. This runs
them over every tracked `.nd` file in the repository, compares their output to
`nodus.frontend.lexer.tokenize` and `nodus.frontend.parser.Parser`, and reports
how many VM instructions each phase cost.

The comparison is exact. Tokens must agree on kind, value, line and column.
The AST is compared as nested lists, `[NodeName, field, ...]`, with fields in
dataclass order and private fields (`_tok`, `_comments`) left out. The Nodus
parser builds that shape directly.

    python -m tools.selfhost_check            # every tracked .nd file
    python -m tools.selfhost_check FILE ...   # just these
    python -m tools.selfhost_check --json     # machine-readable summary

Exit status is 1 if any file disagrees.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import subprocess
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SELFHOST = _REPO_ROOT / "examples" / "selfhost"

if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from nodus.frontend.lexer import tokenize  # noqa: E402
from nodus.frontend.parser import Parser  # noqa: E402
from nodus.runtime.diagnostics import LangSyntaxError  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402

# Each phase is a separate run, so a phase's cost is the difference between
# two instruction counts rather than a reading taken mid-run.
#
# Every program imports both modules, so the import cost is the same in each and
# cancels out of the differences. The imports are relative: `run_source` resolves
# them against `filename`, which points into `examples/selfhost/`.
_IMPORTS = 'import "./lexer.nd" as lexer\nimport "./parser.nd" as parser\n'
_PROGRAMS = {
    "base": _IMPORTS + "let src = host_source()\n",
    "lex": _IMPORTS + "let toks = lexer.tokenize(host_source())\n",
    "parse": _IMPORTS + "let ast = parser.parse_source(host_source())\n",
    "tokens": (
        _IMPORTS
        + "let rows = []\n"
        + "for t in lexer.tokenize(host_source()) {\n"
        + "    push(rows, [t.kind, t.val, t.line, t.col])\n"
        + "}\n"
        + "host_emit(json_stringify(rows))\n"
    ),
    "ast": _IMPORTS + "host_emit(json_stringify(parser.parse_source(host_source())))\n",
}


def tracked_nd_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "*.nd"], cwd=_REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout
    return [_REPO_ROOT / line for line in out.splitlines() if line.strip()]


def python_tokens(src: str) -> list:
    return [[t.kind, t.val, t.line, t.col] for t in tokenize(src)]


def to_lists(value):
    """A Python AST as `[NodeName, field, ...]`, the shape the Nodus parser builds."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return [type(value).__name__] + [
            to_lists(getattr(value, f.name))
            for f in dataclasses.fields(value)
            if not f.name.startswith("_")
        ]
    if isinstance(value, (list, tuple)):
        return [to_lists(v) for v in value]
    return value


def python_ast(src: str) -> list:
    return to_lists(Parser(tokenize(src)).parse())


class SelfHosted:
    """Runs one of `_PROGRAMS` against a source text."""

    def __init__(self) -> None:
        self.source = ""
        self.emitted: str | None = None
        self.rt = NodusRuntime(max_steps=None, timeout_ms=None)
        self.rt.register_function("host_source", lambda: self.source, arity=0)
        self.rt.register_function("host_emit", self._emit, arity=1)

    def _emit(self, text):
        self.emitted = text
        return None

    def run(self, program: str, source: str) -> tuple[int, float, str | None, str | None]:
        """(instructions, seconds, emitted, error)."""
        self.source = source
        self.emitted = None
        started = time.perf_counter()
        result = self.rt.run_source(_PROGRAMS[program], filename=str(_SELFHOST / "README.md"))
        elapsed = time.perf_counter() - started
        instructions = self.rt.get_execution_stats()["instructions_executed"]
        error = None
        if not result.get("ok"):
            error = str((result.get("error") or {}).get("message") or result)
        return instructions, elapsed, self.emitted, error


def first_difference(expected, actual, path="") -> str:
    if type(expected) is not type(actual) and not (
        isinstance(expected, (int, float)) and isinstance(actual, (int, float))
        and not isinstance(expected, bool) and not isinstance(actual, bool)
    ):
        return f"{path or '<root>'}: expected {expected!r}, got {actual!r}"
    if isinstance(expected, list):
        # Recurse into every element rather than skipping those that compare
        # equal: Python's `1 == True` would let a bool stand in for an int.
        for i, (e, a) in enumerate(zip(expected, actual)):
            found = first_difference(e, a, f"{path}[{i}]")
            if found:
                return found
        if len(expected) != len(actual):
            return f"{path or '<root>'}: expected {len(expected)} items, got {len(actual)}"
        return ""
    if expected != actual:
        return f"{path or '<root>'}: expected {expected!r}, got {actual!r}"
    return ""


def check_file(
    sh: SelfHosted, path: Path, phases: tuple[str, ...], *, measure: bool = True
) -> dict:
    """Compare one file's tokens and AST, and with `measure`, count what each phase cost."""
    src = path.read_bytes().decode("utf-8")
    rel = path.relative_to(_REPO_ROOT).as_posix()
    row: dict = {"file": rel, "chars": len(src), "lines": src.count("\n") + 1}

    try:
        expected_tokens = python_tokens(src)
    except LangSyntaxError as exc:
        row["skipped"] = f"Python lexer rejects it: {exc}"
        return row
    row["tokens"] = len(expected_tokens)

    _, _, emitted, error = sh.run("tokens", src)
    if error is not None:
        row["lex_error"] = error
    else:
        diff = first_difference(expected_tokens, json.loads(emitted))
        if diff:
            row["lex_diff"] = diff

    if "parse" in phases:
        try:
            expected_ast = python_ast(src)
        except LangSyntaxError as exc:
            row["parse_skipped"] = f"Python parser rejects it: {exc}"
        else:
            _, _, emitted, error = sh.run("ast", src)
            if error is not None:
                row["parse_error"] = error
            else:
                diff = first_difference(expected_ast, json.loads(emitted))
                if diff:
                    row["parse_diff"] = diff

    if not measure:
        return row
    base, base_s, _, _ = sh.run("base", src)
    lex, lex_s, _, _ = sh.run("lex", src)
    row["lex_instructions"] = lex - base
    row["lex_seconds"] = max(lex_s - base_s, 0.0)
    if "parse" in phases and "parse_skipped" not in row and "parse_error" not in row:
        parse, parse_s, _, _ = sh.run("parse", src)
        row["parse_instructions"] = parse - lex
        row["parse_seconds"] = max(parse_s - lex_s, 0.0)
    return row


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--lex-only", action="store_true", help="skip the parser")
    ap.add_argument("--json", action="store_true", help="print the per-file rows as JSON")
    args = ap.parse_args(argv)

    files = [p.resolve() for p in args.files] if args.files else tracked_nd_files()
    phases = ("lex",) if args.lex_only else ("lex", "parse")
    sh = SelfHosted()
    rows = [check_file(sh, p, phases) for p in files]

    failures = [
        r for r in rows
        if any(k in r for k in ("lex_error", "lex_diff", "parse_error", "parse_diff"))
    ]
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for r in rows:
            for key in ("skipped", "parse_skipped", "lex_error", "lex_diff", "parse_error", "parse_diff"):
                if key in r:
                    print(f"{r['file']}: {key}: {r[key]}")
        checked = [r for r in rows if "skipped" not in r]
        chars = sum(r["chars"] for r in checked)
        toks = sum(r["tokens"] for r in checked)
        lex_i = sum(r["lex_instructions"] for r in checked)
        lex_s = sum(r["lex_seconds"] for r in checked)
        print(f"{len(checked)} files, {chars:,} chars, {toks:,} tokens")
        print(f"lex:   {lex_i:,} instructions ({lex_i / max(chars, 1):.1f}/char), {lex_s:.2f}s")
        parsed = [r for r in checked if "parse_instructions" in r]
        if parsed:
            par_i = sum(r["parse_instructions"] for r in parsed)
            par_s = sum(r["parse_seconds"] for r in parsed)
            par_t = sum(r["tokens"] for r in parsed)
            print(f"parse: {par_i:,} instructions ({par_i / max(par_t, 1):.1f}/token) over "
                  f"{len(parsed)} files, {par_s:.2f}s")
        print(f"{len(failures)} file(s) disagree")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
