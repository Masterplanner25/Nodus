"""Opcode phase: verify the frozen instruction set matches its own record.

The opcode set has been declared frozen since v1.0, and `FREEZE_PROPOSAL.md`
defines a seven-step extension process for adding one. Until this phase existed,
that freeze was enforced by prose and checked by nobody: `MOD` (2026-05-24) and
`RESET_LOCAL_IDX` (2026-06-10) were both added to the VM dispatch table without
a single one of the three mandatory steps, and went unnoticed until the
2026-08-07 doc sweep — about two and a half months and two months later (#366).

This phase makes the inventory machine-checked. It reads the live dispatch table
out of a constructed `VM` — not a regex over `vm.py`, so it cannot be fooled by
formatting — and requires every other record of the instruction set to agree:

1. `BYTECODE_REFERENCE.md` §3 opcode inventory (`### NAME` entries)
2. `BYTECODE_REFERENCE.md` Appendix quick opcode table
3. `FREEZE_PROPOSAL.md` opcode stability tables
4. Opcodes the compiler can emit (a compiler-only opcode is `Unknown opcode` at
   runtime)
5. Removed opcodes (`LOAD_LOCAL`) must stay out of the dispatch table
6. Declared counts and `BYTECODE_VERSION` values in the two authoritative docs

Check 6 works from a fixed table of anchors rather than a general regex over
prose, because both documents are full of correct *historical* counts ("47
opcodes at the v1.0 freeze") that a general scan would flag forever. An anchor
that stops matching is itself reported: rewording a policed claim fails loudly
instead of silently dropping out of coverage.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class OpcodeFinding:
    message: str
    detail: str = ""


@dataclass
class OpcodeResult:
    findings: list[OpcodeFinding] = field(default_factory=list)
    checks_run: int = 0
    dispatch_count: int = 0
    bytecode_version: int | None = None

    @property
    def passed(self) -> int:
        return self.checks_run - len(self.findings)


# -- Source of truth ----------------------------------------------------------

def load_dispatch_opcodes(root: str) -> tuple[set[str], int]:
    """Return the live VM dispatch opcode set and `BYTECODE_VERSION`.

    Constructs a real `VM` so the table is the one `execute()` dispatches
    through, rather than a parse of the source that built it.
    """
    src = str(Path(root) / "src")
    if src not in sys.path:
        sys.path.insert(0, src)

    from nodus.compiler.compiler import BYTECODE_VERSION
    from nodus.vm.vm import VM

    vm = VM([("HALT",)], {})
    return set(vm._dispatch), BYTECODE_VERSION


# -- Document parsing ---------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{2,3})\s+(.*?)\s*$", re.M)
_OPCODE_NAME = r"[A-Z][A-Z_0-9]*"
_REMOVED_MARK = "⛔"


def _section(text: str, title: str, level: int = 2) -> str:
    """Return the body of the heading whose text starts with `title`.

    Ends at the next heading of the same or shallower level.
    """
    hashes = "#" * level
    start = None
    for m in _HEADING_RE.finditer(text):
        if start is None:
            if m.group(1) == hashes and m.group(2).startswith(title):
                start = m.end()
        elif len(m.group(1)) <= level:
            return text[start:m.start()]
    return text[start:] if start is not None else ""


def parse_reference_inventory(text: str) -> tuple[set[str], set[str]]:
    """Parse §3 of BYTECODE_REFERENCE.md into (active, removed) opcode sets.

    An entry is "removed" when its body carries the ⛔ tombstone marker.
    """
    body = _section(text, "3. Opcode Inventory")
    entries = list(re.finditer(rf"^### ({_OPCODE_NAME})\s*$", body, re.M))
    active: set[str] = set()
    removed: set[str] = set()
    for i, m in enumerate(entries):
        end = entries[i + 1].start() if i + 1 < len(entries) else len(body)
        (removed if _REMOVED_MARK in body[m.end():end] else active).add(m.group(1))
    return active, removed


def parse_reference_categories(text: str) -> dict[str, str]:
    """Map each §3 opcode to its declared `Category:` line.

    Used by the spec-conformance check below. The category is read from the
    document rather than hardcoded here, so re-categorising an opcode moves it
    into or out of coverage in the same edit — a second list here would be one
    more thing to keep in step.
    """
    body = _section(text, "3. Opcode Inventory")
    entries = list(re.finditer(rf"^### ({_OPCODE_NAME})\s*$", body, re.M))
    categories: dict[str, str] = {}
    for i, m in enumerate(entries):
        end = entries[i + 1].start() if i + 1 < len(entries) else len(body)
        found = re.search(r"^- Category:\s*(.+?)\s*$", body[m.end():end], re.M)
        if found:
            categories[m.group(1)] = found.group(1).lower()
    return categories


def parse_specified_opcodes(root: str) -> set[str] | None:
    """The opcodes `tests/test_opcode_semantics.py` writes a semantic spec for.

    Read out of the module's own `SPECIFIED` tuple by literal evaluation, not by
    importing it — the gate must not run a test module as a side effect of
    checking one.
    """
    path = Path(root) / _SPEC_TESTS
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"^SPECIFIED\s*=\s*\((.*?)\)\s*$", source, re.M | re.S)
    if not m:
        return None
    return set(re.findall(r'"([A-Z][A-Z_0-9]*)"', m.group(1)))


def parse_reference_removed_section(text: str) -> set[str]:
    body = _section(text, "Removed Opcodes")
    return set(re.findall(rf"^### ({_OPCODE_NAME})\s*$", body, re.M))


def parse_reference_appendix(text: str) -> tuple[set[str], set[str]]:
    """Parse the Appendix quick opcode table into (active, removed) sets."""
    body = _section(text, "Appendix: Quick Opcode Table")
    active: set[str] = set()
    removed: set[str] = set()
    for line in body.splitlines():
        m = re.match(rf"^\|\s*({_OPCODE_NAME})\s*\|", line)
        if m:
            (removed if _REMOVED_MARK in line else active).add(m.group(1))
    return active, removed


def parse_freeze_stability_tables(text: str) -> tuple[set[str], set[str], set[str]]:
    """Parse FREEZE_PROPOSAL.md's stability tables.

    Returns (stable, provisional, removed). Rows look like
    ``| `PUSH_CONST` | `→ val` | **stable** | ... |``.
    """
    body = _section(text, "Opcode Stability Table")
    stable: set[str] = set()
    provisional: set[str] = set()
    removed: set[str] = set()
    for line in body.splitlines():
        m = re.match(rf"^\|\s*`({_OPCODE_NAME})`\s*\|", line)
        if not m:
            continue
        # Split on unescaped pipes only: stack-effect cells contain `\|`.
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
        classification = cells[2].lower() if len(cells) > 2 else ""
        if "removed" in classification:
            removed.add(m.group(1))
        elif "provisional" in classification:
            provisional.add(m.group(1))
        elif "stable" in classification:
            stable.add(m.group(1))
    return stable, provisional, removed


# -- Emitted-opcode scan ------------------------------------------------------

# First string literal in an `emit(...)` / `patch(index, ...)` call.
_EMIT_RE = re.compile(
    rf'self\.(?:emit|patch)\(\s*(?:[^,()"\']+,\s*)?"({_OPCODE_NAME})"'
)
# Values of opcode lookup dicts such as the binary-operator `op_map`.
_DICT_VALUE_RE = re.compile(rf':\s*"({_OPCODE_NAME})"')
# Instruction tuples the optimizer rewrites bytecode into, e.g. ("PUSH_CONST", v).
_TUPLE_RE = re.compile(rf'\(\s*"({_OPCODE_NAME})"\s*,')

_EMIT_SOURCES = [
    ("src/nodus/compiler/compiler.py", (_EMIT_RE, _DICT_VALUE_RE)),
    ("src/nodus/compiler/optimizer.py", (_TUPLE_RE,)),
]


def scan_emitted_opcodes(root: str) -> dict[str, list[str]]:
    """Map each opcode name the front-end can emit to where it was found.

    Deliberately narrow: only the syntactic positions that actually produce an
    instruction, so a new all-caps constant elsewhere in these files cannot make
    the gate cry wolf.
    """
    found: dict[str, list[str]] = {}
    for rel, patterns in _EMIT_SOURCES:
        path = Path(root) / rel
        if not path.exists():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for pattern in patterns:
                for m in pattern.finditer(line):
                    found.setdefault(m.group(1), []).append(f"{rel}:{lineno}")
    return found


# -- Policed numeric claims ---------------------------------------------------

_REFERENCE = "docs/runtime/BYTECODE_REFERENCE.md"
_FREEZE = "docs/governance/FREEZE_PROPOSAL.md"
_SPEC_TESTS = "tests/test_opcode_semantics.py"

# #412 phase 2: the category whose opcodes must carry a semantic spec.
#
# Every VM bug of the v5 cycle (#361, #370, #371) was in the exception-unwind
# path, and phase 1's census found `POP_TRY` executing 18 times and
# `FINALLY_END` 60 across the whole suite -- which is not an exercised path.
# Naming a *category* rather than four opcodes means a fifth exception opcode is
# covered by construction: it fails this check until somebody specifies it,
# which is the "make a test drive off the set" rule applied to the gate.
_SPEC_REQUIRED_CATEGORY = "exceptions"
_SEMANTICS = "docs/runtime/INSTRUCTION_SEMANTICS.md"
_ARCH = "docs/runtime/ARCHITECTURE_ANALYSIS.md"
_STABILITY_INDEX = "docs/governance/LANGUAGE_STABILITY_INDEX.md"

# (file, kind, description, pattern) — every capture must equal the live value,
# and a pattern that matches nothing is a finding in its own right.
CLAIM_ANCHORS: list[tuple[str, str, str, str]] = [
    (_REFERENCE, "count", "header stability banner",
     r"All (\d+) active opcodes are \*\*stable\*\*"),
    (_REFERENCE, "count", "intro freeze sentence",
     r"\*\*frozen at v1\.0\*\*: (\d+) active stable opcodes"),
    (_REFERENCE, "count", "§3.1 dispatch-table total",
     r"total active opcodes in the dispatch table to \*\*(\d+)\*\*"),
    (_REFERENCE, "count", "§10 exact count from VM dispatch",
     r"opcode count \(exact from VM dispatch\): \*\*(\d+)\*\*"),
    (_REFERENCE, "version", "intro BYTECODE_VERSION",
     r"active stable opcodes, `BYTECODE_VERSION = (\d+)`"),
    (_REFERENCE, "version", "maturity snapshot BYTECODE_VERSION",
     r"^- `BYTECODE_VERSION = (\d+)`\. Future opcodes"),
    (_REFERENCE, "version", "§3.1 unbumped-version note",
     r"`BYTECODE_VERSION` remains \*\*(\d+)\*\*"),
    (_FREEZE, "count", "freeze summary — active today",
     r"\| Total opcodes \(active\) \| \*\*\d+\*\* \| \*\*(\d+)\*\* \|"),
    (_FREEZE, "count", "freeze summary — stable today",
     r"\| Stable \| \*\*\d+\*\* \| \*\*(\d+)\*\* \|"),
    (_FREEZE, "count", "stability table preamble — active today",
     r"included in the tables below — (\d+) active today"),
    (_FREEZE, "count", "summary counts — stable",
     r"\| \*\*stable\*\* \| \*\*(\d+)\*\* \|"),
    (_FREEZE, "count", "summary counts — total active",
     r"\| \*\*Total \(active\)\*\* \| \*\*(\d+)\*\* \|"),
    (_FREEZE, "count", "summary counts — totals today",
     r"Totals today: \*\*(\d+) stable\*\*"),
    (_FREEZE, "version", "freeze declaration BYTECODE_VERSION",
     r"^\*\*BYTECODE_VERSION:\*\* (\d+)"),
    (_SEMANTICS, "count", "header stability banner",
     r"All (\d+) active opcodes are stable"),
    (_ARCH, "count", "bytecode versioning note",
     r"\(frozen at v1\.0\)\. All (\d+) active opcodes"),
    (_STABILITY_INDEX, "count", "opcode set row",
     r"\| Opcode set \((\d+) opcodes\)"),
]


# -- Phase --------------------------------------------------------------------

def _compare(result: OpcodeResult, label: str, documented: set[str],
             dispatch: set[str]) -> None:
    """Require `documented` to equal the dispatch table exactly, both ways."""
    result.checks_run += 1
    missing = sorted(dispatch - documented)
    extra = sorted(documented - dispatch)
    if not missing and not extra:
        return
    details = []
    if missing:
        details.append(f"in VM dispatch but not in {label}: {', '.join(missing)}")
    if extra:
        details.append(f"in {label} but not in VM dispatch: {', '.join(extra)}")
    result.findings.append(OpcodeFinding(
        message=f"{label} does not match the VM dispatch table",
        detail="; ".join(details),
    ))


def _check_semantic_specs(result: OpcodeResult, root: str, reference: str, dispatch: set[str]) -> None:
    """Spec conformance, not just inventory (#412 phase 2).

    The inventory checks above prove the *names* agree. They say nothing about
    whether any opcode does what it is documented to do, which is what #412 was
    filed about: `nodus_gate --opcodes` was green through all three of the
    exception-unwind bugs.

    Two checks, both cheap and both about rot rather than about semantics —
    a gate cannot verify semantics, only that the thing which does is still
    pointed at the right set:

    1. every opcode in the `exceptions` category has a spec;
    2. every specified opcode is still in the dispatch table, so a rename
       leaves the spec module dangling loudly rather than silently covering a
       name nothing dispatches.
    """
    specified = parse_specified_opcodes(root)

    result.checks_run += 1
    if specified is None:
        result.findings.append(OpcodeFinding(
            message=f"{_SPEC_TESTS} has no readable SPECIFIED tuple",
            detail="opcode semantic specs cannot be verified without it",
        ))
        return

    categories = parse_reference_categories(reference)
    required = {op for op, cat in categories.items()
                if cat == _SPEC_REQUIRED_CATEGORY and op in dispatch}
    unspecified = sorted(required - specified)
    if unspecified:
        result.findings.append(OpcodeFinding(
            message=f"{_SPEC_REQUIRED_CATEGORY} opcode(s) with no semantic spec",
            detail=(f"{', '.join(unspecified)} — add a spec to {_SPEC_TESTS} "
                    "and name it in SPECIFIED"),
        ))

    result.checks_run += 1
    dangling = sorted(specified - dispatch)
    if dangling:
        result.findings.append(OpcodeFinding(
            message=f"{_SPEC_TESTS} specifies opcode(s) the VM does not dispatch",
            detail=", ".join(dangling),
        ))


def run_opcode_phase(root: str) -> OpcodeResult:
    """Verify every record of the frozen opcode set against the live VM."""
    result = OpcodeResult()

    result.checks_run += 1
    try:
        dispatch, bytecode_version = load_dispatch_opcodes(root)
    except Exception as exc:  # import or construction failure
        result.findings.append(OpcodeFinding(
            message="could not read the VM dispatch table",
            detail=f"{type(exc).__name__}: {exc}",
        ))
        return result
    result.dispatch_count = len(dispatch)
    result.bytecode_version = bytecode_version

    def _read(rel: str) -> str | None:
        path = Path(root) / rel
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            result.findings.append(OpcodeFinding(
                message=f"{rel} is unreadable",
                detail="the opcode inventory cannot be verified without it",
            ))
            return None

    reference = _read(_REFERENCE)
    freeze = _read(_FREEZE)

    if reference is not None:
        inv_active, inv_removed = parse_reference_inventory(reference)
        _compare(result, f"{_REFERENCE} §3 inventory", inv_active, dispatch)

        app_active, app_removed = parse_reference_appendix(reference)
        _compare(result, f"{_REFERENCE} appendix table", app_active, dispatch)

        # Removed opcodes must be named consistently and must stay out of the VM.
        section_removed = parse_reference_removed_section(reference)
        result.checks_run += 1
        if inv_removed != section_removed or inv_removed != app_removed:
            result.findings.append(OpcodeFinding(
                message="removed-opcode lists in BYTECODE_REFERENCE.md disagree",
                detail=(f"§3 inventory: {sorted(inv_removed)}; "
                        f"appendix: {sorted(app_removed)}; "
                        f"Removed Opcodes section: {sorted(section_removed)}"),
            ))

        result.checks_run += 1
        resurrected = sorted(inv_removed & dispatch)
        if resurrected:
            result.findings.append(OpcodeFinding(
                message="an opcode documented as removed is back in the dispatch table",
                detail=", ".join(resurrected),
            ))

        _check_semantic_specs(result, root, reference, dispatch)

    if freeze is not None:
        stable, provisional, freeze_removed = parse_freeze_stability_tables(freeze)
        _compare(result, f"{_FREEZE} stability tables", stable, dispatch)

        result.checks_run += 1
        if provisional:
            result.findings.append(OpcodeFinding(
                message="FREEZE_PROPOSAL.md lists provisional opcodes after the v1.0 freeze",
                detail=", ".join(sorted(provisional)),
            ))

        result.checks_run += 1
        still_live = sorted(freeze_removed & dispatch)
        if still_live:
            result.findings.append(OpcodeFinding(
                message="FREEZE_PROPOSAL.md marks an opcode removed but the VM still dispatches it",
                detail=", ".join(still_live),
            ))

    # Anything the front-end can emit must have a handler, or it is a runtime
    # "Unknown opcode" waiting for the right program.
    result.checks_run += 1
    emitted = scan_emitted_opcodes(root)
    unhandled = sorted(set(emitted) - dispatch)
    if unhandled:
        result.findings.append(OpcodeFinding(
            message="the compiler can emit an opcode the VM does not handle",
            detail="; ".join(f"{op} ({emitted[op][0]})" for op in unhandled),
        ))

    _check_claims(result, root, dispatch_count=len(dispatch),
                  bytecode_version=bytecode_version)

    return result


def _check_claims(result: OpcodeResult, root: str, *, dispatch_count: int,
                  bytecode_version: int) -> None:
    """Verify the counts and versions asserted in prose still hold."""
    cache: dict[str, str | None] = {}
    for rel, kind, description, pattern in CLAIM_ANCHORS:
        result.checks_run += 1
        if rel not in cache:
            try:
                cache[rel] = (Path(root) / rel).read_text(encoding="utf-8")
            except OSError:
                cache[rel] = None
        text = cache[rel]
        if text is None:
            result.findings.append(OpcodeFinding(
                message=f"{rel} is unreadable — cannot verify '{description}'",
            ))
            continue

        matches = re.findall(pattern, text, re.M)
        if not matches:
            result.findings.append(OpcodeFinding(
                message=f"{rel}: policed claim '{description}' no longer matches",
                detail=("the claim was reworded or deleted; restore the wording or "
                        f"update CLAIM_ANCHORS in {Path(__file__).name}"),
            ))
            continue

        expected = dispatch_count if kind == "count" else bytecode_version
        wrong = sorted({int(v) for v in matches if int(v) != expected})
        if wrong:
            noun = "opcode count" if kind == "count" else "BYTECODE_VERSION"
            result.findings.append(OpcodeFinding(
                message=f"{rel}: '{description}' states the wrong {noun}",
                detail=f"document says {', '.join(str(v) for v in wrong)}; live value is {expected}",
            ))
