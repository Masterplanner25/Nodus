"""Invariants phase: the invariant-to-test ledger is machine-checked (#179).

`EXECUTION_INVARIANTS.md` documents 29 runtime invariants. Which test checks which
invariant was recorded **in prose**, in two different places — sometimes inline
under the invariant, sometimes in §8's coverage bullets — and maintained by hand.
So three things could go wrong with no CI signal:

  1. a new `### I-…` heading is added and nothing covers it;
  2. a cited test is renamed or deleted, leaving the document pointing at a file
     that no longer exists;
  3. an invariant is renamed or removed while a stale claim about it survives.

This is the same failure mode the opcode inventory had before #366, and the same
one `--opcodes` closed by reading the dispatch table rather than trusting prose.

**What this phase does not do.** It cannot verify that an invariant *holds* — the
tests do that. It verifies that the ledger tying invariants to those tests is
honest, which is the only part a gate can own. #179 asks for exactly this and
calls it "the machine-checked contract"; the contract is the mapping, not the
behaviour.

**Why a manifest rather than parsing the prose.** Reading test paths out of the
document would make the document the source of truth for its own correctness — a
citation could be dropped and the check would simply have less to verify, which
is a check that passes by having nothing to do. `tools/invariant_coverage.json`
holds one entry per invariant, and an entry with no tests must state a reason.
Same shape as `tools/shape_manifest.json` and `tools/consumers.json`.

**`unrecorded` is not `uncovered`.** 23 of the 29 entries carry no test today.
That does not mean the behaviour is untested — it means nothing ties a test to
the invariant, which is the gap this issue is about. Recording the distinction
keeps the ledger honest instead of inventing coverage.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


_DOC = "docs/runtime/EXECUTION_INVARIANTS.md"
_MANIFEST = "tools/invariant_coverage.json"

_HEADING_RE = re.compile(r"^### (I-[A-Z]+-\d+): (.*?)\s*$", re.M)
_SECTION_RE = re.compile(r"^#{2,3} ", re.M)
_TEST_RE = re.compile(r"tests/[A-Za-z0-9_/]+\.py")


@dataclass
class InvariantFinding:
    message: str
    detail: str = ""


@dataclass
class InvariantResult:
    findings: list[InvariantFinding] = field(default_factory=list)
    advisories: list[InvariantFinding] = field(default_factory=list)
    checks_run: int = 0
    documented: int = 0
    with_tests: int = 0
    unrecorded: int = 0
    error: str | None = None

    @property
    def passed(self) -> int:
        return self.checks_run - len(self.findings)


def parse_documented_invariants(text: str) -> dict[str, str]:
    """Map invariant id -> title, from `### I-…:` headings.

    Sections are bounded by the next heading of **any** level. Bounding on `###`
    alone lets the last invariant swallow §8, which silently gives it every test
    path in the coverage section — a false pass, found while writing this.
    """
    bounds = [m.start() for m in _SECTION_RE.finditer(text)] + [len(text)]
    documented: dict[str, str] = {}
    for m in _HEADING_RE.finditer(text):
        documented[m.group(1)] = m.group(2)
        next(b for b in bounds if b > m.start())  # bound exists; parse is well-formed
    return documented


def cited_tests_by_invariant(text: str) -> dict[str, set[str]]:
    """Test paths the *document* names for each invariant, inline or in §8.

    Used only for the advisory drift check — the manifest is what the failing
    checks read.
    """
    bounds = [m.start() for m in _SECTION_RE.finditer(text)] + [len(text)]
    heads = list(_HEADING_RE.finditer(text))
    cited: dict[str, set[str]] = {}
    for m in heads:
        end = next(b for b in bounds if b > m.start())
        body = text[m.end():end].replace("\\", "/")
        cited[m.group(1)] = set(_TEST_RE.findall(body))

    if "## 8. Invariant coverage status" in text:
        coverage = text.split("## 8. Invariant coverage status", 1)[1].split("\n---", 1)[0]
        for bullet in re.split(r"\n- ", coverage):
            head = re.match(r"(I-[A-Z]+-\d+)", bullet.strip())
            if head is None:
                continue
            found = set(_TEST_RE.findall(bullet.replace("\\", "/")))
            cited.setdefault(head.group(1), set()).update(found)
    return cited


def run_invariants_phase(root: str) -> InvariantResult:
    result = InvariantResult()
    root_path = Path(root)

    try:
        text = (root_path / _DOC).read_text(encoding="utf-8")
    except OSError as exc:
        result.error = f"{_DOC} is unreadable: {exc}"
        return result

    # A manifest that cannot be read is always a failure, never a skip — the rule
    # the shapes and consumers phases already follow. A check may not pass by
    # being unable to run.
    try:
        raw = json.loads((root_path / _MANIFEST).read_text(encoding="utf-8"))
        recorded = raw["invariants"]
        if not isinstance(recorded, dict):
            raise TypeError("'invariants' is not an object")
    except Exception as exc:
        result.error = f"{_MANIFEST} is unreadable: {type(exc).__name__}: {exc}"
        return result

    documented = parse_documented_invariants(text)
    result.documented = len(documented)

    # 1. Every documented invariant is classified.
    result.checks_run += 1
    unclassified = sorted(set(documented) - set(recorded))
    if unclassified:
        result.findings.append(InvariantFinding(
            message="invariant(s) documented with no entry in the coverage ledger",
            detail=(f"{', '.join(unclassified)} — add an entry to {_MANIFEST} naming "
                    "its covering test(s), or a reason it has none"),
        ))

    # 2. Every ledger entry still names a documented invariant.
    result.checks_run += 1
    orphaned = sorted(set(recorded) - set(documented))
    if orphaned:
        result.findings.append(InvariantFinding(
            message="coverage ledger names invariant(s) the document no longer has",
            detail=f"{', '.join(orphaned)} — renamed or removed in {_DOC}",
        ))

    # 3. Every named test exists. This is the check that catches a rename.
    result.checks_run += 1
    missing: list[str] = []
    for inv in sorted(set(documented) & set(recorded)):
        entry = recorded[inv] or {}
        for rel in entry.get("tests", []) or []:
            if not (root_path / rel).is_file():
                missing.append(f"{inv} -> {rel}")
    if missing:
        result.findings.append(InvariantFinding(
            message="coverage ledger names test file(s) that do not exist",
            detail="; ".join(missing),
        ))

    # 4. An entry with no tests must say why.
    result.checks_run += 1
    unexplained: list[str] = []
    for inv in sorted(set(documented) & set(recorded)):
        entry = recorded[inv] or {}
        if not (entry.get("tests") or []) and not str(entry.get("reason", "")).strip():
            unexplained.append(inv)
    if unexplained:
        result.findings.append(InvariantFinding(
            message="invariant(s) with no covering test and no stated reason",
            detail=(f"{', '.join(unexplained)} — an unrecorded invariant needs a reason, "
                    "so the gap is a decision rather than an omission"),
        ))

    for inv in set(documented) & set(recorded):
        if (recorded[inv] or {}).get("tests"):
            result.with_tests += 1
        else:
            result.unrecorded += 1

    # Advisory: the document cites a test the ledger has not learned. Not a
    # failure — prose may legitimately mention a test in passing — but it is how
    # the two drift apart, so it is reported.
    for inv, cited in cited_tests_by_invariant(text).items():
        entry = recorded.get(inv) or {}
        known = set(entry.get("tests", []) or [])
        for rel in sorted(cited - known):
            result.advisories.append(InvariantFinding(
                message=f"{inv}: {_DOC} names {rel}, the ledger does not",
                detail="add it to the entry, or the citation is the only record",
            ))

    return result
