"""Every `nodus` import written in a documentation Python block must resolve.

`docs/tooling/TESTING.md` told contributors to write parser tests starting with

    from lexer import tokenize
    from parser import Parser
    from ast_nodes import Let, Num

None of the three resolves. `parser` is additionally the name of a Python stdlib
module removed in 3.10, so the failure reads as an environment problem rather
than a wrong path. The page had said this since it was written, and nothing
checked it: `docs/tooling/` was outside the doc gate's scan, and the gate runs
`nodus` blocks in any case, never Python ones.

Scope is deliberately narrow. Only imports of `nodus*` are checked -- those are
the ones this repository owns and can therefore be wrong about. A doc importing
`fastapi` or `httpx` is describing an embedder's environment, not making a claim
about this tree, and failing on an optional dependency would make the test a
nuisance that gets deleted.

Symbols are checked too, not just modules: a module path that resolves while the
name it is imported for does not is the same defect one level down.
"""

from __future__ import annotations

import importlib
import re
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

#: ```python fences, non-greedy, so an unterminated block cannot swallow the file.
_PY_BLOCK = re.compile(r"^```python\s*$(.*?)^```\s*$", re.M | re.S)

#: `from nodus.x.y import A, B` and `import nodus.x.y`
_FROM = re.compile(r"^\s*from\s+(nodus[A-Za-z0-9_.]*)\s+import\s+([^\n#]+)", re.M)
_PLAIN = re.compile(r"^\s*import\s+(nodus[A-Za-z0-9_.]*)\s*$", re.M)

#: Any `from <word> import ...` where <word> is a bare, unqualified name.
_BARE = re.compile(r"^\s*from\s+([a-z_][a-z0-9_]*)\s+import\s", re.M)


def _internal_module_basenames() -> set[str]:
    """Every module basename under `src/nodus/`, derived rather than listed.

    Documenting an internal module by its bare name -- `from parser import
    Parser` rather than `from nodus.frontend.parser import Parser` -- is the
    defect this file was written for, and it is invisible to a scan that only
    looks at imports already spelled `nodus...`. Deriving the set means a module
    added or renamed later is covered without anyone remembering to come back.
    """
    root = _REPO_ROOT / "src" / "nodus"
    return {p.stem for p in root.rglob("*.py") if p.stem != "__init__"}

#: Directories whose documents deliberately name things this tree does not have.
#: Each needs a stated reason; the point is that the list stays short and
#: arguable, not that it stays empty.
_SKIP_DIRS = {
    # Dated records of what was true on the day they were written. `docs/evals/`
    # is explicitly not meant to move with the tree -- v3.0.0's eval imports
    # `run_source` from the package root, which was correct then.
    "docs/evals",
    # Specs for libraries that are planned or scaffolded, not built. Importing
    # `nodus_container` is the document's subject, not a claim about this tree.
    "docs/ecosystem",
    # Superseded documents kept as history.
    "docs/history",
}


def _documents() -> list[Path]:
    docs = _REPO_ROOT / "docs"
    return sorted(
        p for p in docs.rglob("*.md")
        if not any(p.relative_to(_REPO_ROOT).as_posix().startswith(d + "/")
                   for d in _SKIP_DIRS)
    )


def _imports() -> list[tuple[Path, str, tuple[str, ...]]]:
    """(document, module, symbols) for every nodus import in a python block."""
    found: list[tuple[Path, str, tuple[str, ...]]] = []
    for doc in _documents():
        text = doc.read_text(encoding="utf-8")
        for block in _PY_BLOCK.findall(text):
            for module, names in _FROM.findall(block):
                symbols = tuple(
                    n.strip().split(" as ")[0].strip()
                    for n in names.split(",")
                    if n.strip() and n.strip() not in {"(", ")"}
                )
                found.append((doc, module, symbols))
            for module in _PLAIN.findall(block):
                found.append((doc, module, ()))
    return found


def _bare_internal_imports() -> list[tuple[Path, str]]:
    """(document, module) for bare imports of a name that is a nodus module."""
    internal = _internal_module_basenames()
    found: list[tuple[Path, str]] = []
    for doc in _documents():
        for block in _PY_BLOCK.findall(doc.read_text(encoding="utf-8")):
            for module in _BARE.findall(block):
                if module not in internal:
                    continue
                # `nodus` itself is both an internal basename and a real
                # top-level package, and so is anything else importable on its
                # own. The defect is a name that matches an internal module and
                # resolves nowhere -- that is the property, not the name clash.
                try:
                    importlib.import_module(module)
                except ImportError:
                    found.append((doc, module))
    return found


class DocPythonImportsTests(unittest.TestCase):
    def test_the_scan_finds_something(self):
        """A scan that silently matches nothing passes forever and checks nothing.

        This is the failure mode that has bitten source-assertions in this repo
        repeatedly, so the sweep asserts on its own yield before anything else.
        """
        found = _imports()
        self.assertGreater(
            len(found), 10,
            "found almost no `nodus` imports in documentation Python blocks -- "
            "the fence or import patterns have probably stopped matching",
        )

    def test_every_documented_nodus_import_resolves(self):
        for doc, module, symbols in _imports():
            relative = doc.relative_to(_REPO_ROOT).as_posix()
            with self.subTest(document=relative, module=module):
                try:
                    imported = importlib.import_module(module)
                except ImportError as exc:
                    self.fail(
                        f"{relative} documents `import {module}`, which does not "
                        f"resolve: {exc}"
                    )
                for symbol in symbols:
                    if symbol == "*":
                        continue
                    with self.subTest(symbol=symbol):
                        if hasattr(imported, symbol):
                            continue
                        # `from package import submodule` is legal even when the
                        # package does not re-export it, and `hasattr` is False
                        # until something imports it. Checking the attribute
                        # alone reports `from nodus.cli import cli` as broken
                        # when it works.
                        try:
                            importlib.import_module(f"{module}.{symbol}")
                        except ImportError:
                            self.fail(
                                f"{relative} documents "
                                f"`from {module} import {symbol}`, but {module} "
                                f"has no attribute {symbol!r} and no such submodule"
                            )


    def test_internal_modules_are_documented_by_their_full_path(self):
        """`from parser import Parser` is the defect, and it resolves nowhere.

        A bare name that happens to match a module under `src/nodus/` is never
        importable by a reader: nothing puts those directories on `sys.path`.
        `parser` is the worst of them, being also a Python stdlib module removed
        in 3.10, so the failure reads as an environment problem rather than a
        wrong path.
        """
        offenders = [
            (doc.relative_to(_REPO_ROOT).as_posix(), module)
            for doc, module in _bare_internal_imports()
        ]
        self.assertEqual(
            [], offenders,
            "these documents import a nodus internal module by its bare name; "
            "write the full dotted path instead",
        )


if __name__ == "__main__":
    unittest.main()
