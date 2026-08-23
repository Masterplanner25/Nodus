"""CLI entry point for nodus_gate.

Usage:
    python -m tools.nodus_gate.cli --static
    python -m tools.nodus_gate.cli --runtime
    python -m tools.nodus_gate.cli --closed-issues
    python -m tools.nodus_gate.cli --opcodes
    python -m tools.nodus_gate.cli --all
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _parse_args(argv: list[str]) -> dict:
    flags = {
        "--static": False,
        "--runtime": False,
        "--closed-issues": False,
        "--contracts": False,
        "--consumers": False,
        "--opcodes": False,
        "--versions": False,
        "--all": False,
        "--include-design": False,
        "--verbose": False,
        "--quiet": False,
        "--strict": False,
        "--no-cache": False,
        "--migrate-allowlist": False,
    }
    flags_with_values = {"--format", "--allowlist", "--section"}
    values = {"--format": "auto", "--allowlist": ".nodusgate-allow", "--section": "Unreleased"}

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in flags:
            flags[arg] = True
        elif arg in flags_with_values:
            if i + 1 < len(argv):
                values[arg] = argv[i + 1]
                i += 1
        elif arg.startswith("--") and "=" in arg:
            k, v = arg.split("=", 1)
            if k in flags_with_values:
                values[k] = v
        i += 1

    return {**flags, **values}


def _load_allowlist(path: str) -> set[str]:
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return set()
    result: set[str] = set()
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            result.add(line)
    return result


def _migrate_allowlist(path: str) -> int:
    """Rewrite ``block:<path>:<line>`` entries as stable ``blockhash:`` keys.

    Line-number keys silently rot: any edit that shifts a block leaves the
    entry pointing at the wrong line, where it matches nothing and suppresses
    nothing. This resolves each entry against the block currently at that line
    and rewrites it as a content hash. Entries that no longer resolve to a
    runnable block are dropped with a note — they were already inert.

    Comments and ordering are preserved so the file stays reviewable.
    """
    from tools.nodus_gate.markdown_parser import collect_doc_files, extract_blocks

    root = os.getcwd()
    by_line: dict[str, object] = {}
    for file_path in collect_doc_files(root, include_design=True):
        for block in extract_blocks(file_path):
            if block.should_run:
                by_line[block.line_key(root)] = block

    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        print(f"allowlist not found: {path}")
        return 1

    out: list[str] = []
    migrated = dropped = kept = 0
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("block:"):
            out.append(line)
            continue
        block = by_line.get(stripped)
        if block is None:
            print(f"  DROP (dead, matched no runnable block): {stripped}")
            dropped += 1
            continue
        out.append(block.content_key(root))
        migrated += 1

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")

    print(f"migrated {migrated} entr{'y' if migrated == 1 else 'ies'} to blockhash keys, "
          f"dropped {dropped} dead, left {kept} other line(s) untouched")
    return 0


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    args = _parse_args(argv)

    if args["--migrate-allowlist"]:
        return _migrate_allowlist(args["--allowlist"])

    run_static = args["--static"] or args["--all"]
    run_runtime = args["--runtime"] or args["--all"]
    run_closed = args["--closed-issues"] or args["--all"]
    run_contracts = args["--contracts"] or args["--all"]
    run_opcodes = args["--opcodes"] or args["--all"]
    run_consumers = args["--consumers"] or args["--all"]
    run_versions = args["--versions"] or args["--all"]

    if not (run_static or run_runtime or run_closed or run_contracts or run_opcodes
            or run_consumers or run_versions):
        print("Usage: nodus_gate [--static] [--runtime] [--closed-issues] [--contracts] "
              "[--opcodes] [--consumers] [--versions] [--all]")
        print("  --static         Verify documented symbols exist in shipped code")
        print("  --runtime        Execute code blocks from docs and verify output")
        print("  --closed-issues  Verify CHANGELOG-referenced issues have passing tests")
        print("  --contracts      Verify HandlerContract infrastructure is wired correctly")
        print("  --opcodes        Verify the frozen opcode set matches its documented record")
        print("  --consumers      Report non-PyPI consumers a release has left behind")
        print("  --versions       Verify prose still agrees with the version files")
        print("  --all            Run all seven phases")
        print("")
        print("Options:")
        print("  --include-design  Include docs/design/ in scans")
        print("  --verbose         Show each check, not just failures")
        print("  --quiet           Show only summary line")
        print("  --format <fmt>    Output format: pretty, plain, json (default: auto)")
        print("  --allowlist <f>   Path to allowlist file (default: .nodusgate-allow)")
        print("  --section <s>     CHANGELOG section for closed-issues (default: Unreleased)")
        print("")
        print("Maintenance:")
        print("  --migrate-allowlist  Rewrite line-number block: entries as stable")
        print("                       blockhash: entries, and drop dead ones")
        return 2

    output_fmt = args["--format"]
    use_color = output_fmt in ("pretty",) or (output_fmt == "auto" and _is_tty())
    verbose = args["--verbose"]
    quiet = args["--quiet"]
    include_design = args["--include-design"]
    strict = args["--strict"]
    section = args["--section"]

    root = _find_root()
    allowlist = _load_allowlist(args["--allowlist"])

    from tools.nodus_gate.output import (
        format_static, format_runtime, format_closed_issues, format_contracts,
        format_opcodes, format_consumers, format_versions, format_json_results,
    )

    static_result = runtime_result = closed_result = contracts_result = None
    opcode_result = None
    any_failure = False

    if run_static:
        from tools.nodus_gate.static_phase import run_static_phase
        static_result = run_static_phase(root, include_design=include_design, allowlist=allowlist)
        if output_fmt != "json":
            print(format_static(static_result, root, use_color=use_color,
                                verbose=verbose, quiet=quiet))
        if static_result.findings:
            any_failure = True

    if run_runtime:
        from tools.nodus_gate.runtime_phase import run_runtime_phase
        runtime_result = run_runtime_phase(root, include_design=include_design,
                                           allowlist=allowlist, verbose=verbose)
        if output_fmt != "json":
            print(format_runtime(runtime_result, root, use_color=use_color,
                                 verbose=verbose, quiet=quiet))
        if runtime_result.findings:
            any_failure = True

    if run_closed:
        from tools.nodus_gate.closed_issues_phase import run_closed_issues_phase
        closed_result = run_closed_issues_phase(root, section=section)
        if output_fmt != "json":
            print(format_closed_issues(closed_result, root, use_color=use_color,
                                       verbose=verbose, quiet=quiet))
        if closed_result.missing_tests or closed_result.failed:
            any_failure = True

    if run_contracts:
        from tools.nodus_gate.contracts_phase import run_contracts_phase
        contracts_result = run_contracts_phase(root)
        if output_fmt != "json":
            print(format_contracts(contracts_result, use_color=use_color,
                                   verbose=verbose, quiet=quiet))
        if contracts_result.findings:
            any_failure = True

    if run_opcodes:
        from tools.nodus_gate.opcode_phase import run_opcode_phase
        opcode_result = run_opcode_phase(root)
        if output_fmt != "json":
            print(format_opcodes(opcode_result, use_color=use_color,
                                 verbose=verbose, quiet=quiet))
        if opcode_result.findings:
            any_failure = True

    if run_consumers:
        from tools.nodus_gate.consumers_phase import run_consumers_phase
        consumers_result = run_consumers_phase(root)
        if output_fmt != "json":
            print(format_consumers(consumers_result, use_color=use_color,
                                   verbose=verbose, quiet=quiet))
        # Advisory: a stale consumer is a release obligation, not a broken tree.
        # Flagging it early is the point; blocking an unrelated merge is not.
        # A manifest that cannot be read *is* a failure -- the check is not
        # allowed to pass by being unable to run.
        if consumers_result.error:
            any_failure = True
        elif consumers_result.stale and strict:
            any_failure = True

    if run_versions:
        from tools.nodus_gate.versions_phase import run_versions_phase
        versions_result = run_versions_phase(root)
        if output_fmt != "json":
            print(format_versions(versions_result, use_color=use_color,
                                  verbose=verbose, quiet=quiet))
        # A stale version string is wrong *now* and the fix is one line, unlike a
        # stale consumer which needs an external republish. So this one fails by
        # default -- hand-checking a list is exactly what failed three times.
        # The unregistered-line sweep stays advisory: it suggests, it does not decide.
        if versions_result.has_failure:
            any_failure = True

    if output_fmt == "json":
        print(format_json_results(static_result, runtime_result, closed_result,
                                  contracts_result, opcode_result))

    if strict and not any_failure:
        # Warnings don't fail in non-strict mode, but may have been printed
        pass

    return 1 if any_failure else 0


def _is_tty() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _find_root() -> str:
    """Find the project root (parent of tools/)."""
    here = Path(__file__).parent
    # Walk up looking for pyproject.toml
    candidate = here
    for _ in range(5):
        if (candidate / "pyproject.toml").exists():
            return str(candidate)
        candidate = candidate.parent
    # Fall back to cwd
    return os.getcwd()


if __name__ == "__main__":
    sys.exit(main())
