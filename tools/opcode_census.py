"""Phase 1 of #412: how often is each frozen opcode actually executed?

`nodus_gate --opcodes` verifies the **inventory** — that the docs and the VM
dispatch table name the same 49 opcodes. Nothing verifies that any of them does
what it is documented to do, and the three most severe VM bugs of the v5 cycle
(#361, #370, #371) were all opcode-semantics defects on paths nothing exercised.

This produces the number that tells you where to look: an opcode with **zero**
invocations across the whole suite is untested by construction, whatever the
coverage percentage says. `tests/test_bytecode_golden.py` does not close that gap
— it checks what the compiler *emits*, not what the VM then does.

Run:

    PYTHONPATH="C:/dev/Coding Language/src" python -m tools.opcode_census

Counts are collected by wrapping every handler in the dispatch table, so the
census measures **executions**, not appearances in compiled code. An opcode that
is emitted but never reached is exactly the case worth finding, and a static scan
of bytecode would miss it.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

_COUNTS: Counter[str] = Counter()


def _install(vm_module) -> None:
    """Wrap each dispatch entry so every execution is counted."""
    original = vm_module.VM._build_dispatch_table

    def counting_table(self):
        table = original(self)
        wrapped = {}
        for opcode, handler in table.items():
            def make(op, fn):
                def counted(*args, **kwargs):
                    _COUNTS[op] += 1
                    return fn(*args, **kwargs)
                return counted
            wrapped[opcode] = make(opcode, handler)
        return wrapped

    vm_module.VM._build_dispatch_table = counting_table


def main() -> int:
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(repo, "src"))

    from nodus.vm import vm as vm_module

    # The frozen set is read in a subprocess (`_declared_opcodes`) rather than
    # from the table here, so "never executed" can be told apart from "not an
    # opcode" without the counting wrapper in the way.
    declared = _declared_opcodes(repo)

    _install(vm_module)

    import pytest

    argv = sys.argv[1:] or ["tests/", "-q", "-p", "no:cacheprovider"]
    os.chdir(repo)
    exit_code = pytest.main(argv)

    never = [op for op in declared if _COUNTS[op] == 0]
    rare = [(op, _COUNTS[op]) for op in declared if 0 < _COUNTS[op] < 100]

    print()
    print("=" * 68)
    print(f"opcode execution census — {len(declared)} declared, suite exit {exit_code}")
    print("=" * 68)
    for op, count in sorted(_COUNTS.items(), key=lambda kv: -kv[1]):
        print(f"  {count:>12,}  {op}")
    print()
    print(f"NEVER EXECUTED ({len(never)}): {', '.join(never) if never else 'none'}")
    print(f"UNDER 100 EXECUTIONS ({len(rare)}):")
    for op, count in sorted(rare, key=lambda kv: kv[1]):
        print(f"  {count:>6}  {op}")

    out = os.path.join(repo, ".opcode-census.json")
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "declared": declared,
                "counts": dict(_COUNTS),
                "never_executed": never,
                "suite_exit_code": int(exit_code),
            },
            handle,
            indent=2,
            sort_keys=True,
        )
    print(f"\nwritten: {out}")
    return 0


def _declared_opcodes(repo: str) -> list[str]:
    """The frozen set, read the way `nodus_gate --opcodes` reads it."""
    import subprocess

    code = (
        "import sys; sys.path.insert(0, r'%s');"
        "from nodus.vm.vm import VM;"
        "print('\\n'.join(sorted(VM([], {}, code_locs=[])._dispatch)))" % os.path.join(repo, "src")
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
