"""Closed-issue test for #893: nodus-lang honours its Python 3.10 floor.

`tomllib` is stdlib only from 3.11, and `requires-python` allows 3.10, so every
module that loads TOML must guard the import and `tomli` must be a declared
dependency for 3.10 — or importing nodus fails on its own declared floor.

The actual proof that 3.10 works is the `py310-floor` CI job, which imports and
runs on a 3.10 interpreter; that cannot run here on 3.11. What this file guards
is the recurring shape that caused it: a *bare* `import tomllib` on one path
(`project.py`) while its sibling (`user_config.py`) had the guard. It asserts on
the source, so a new bare importer fails here the day it lands, and that the
backport is actually declared.
"""
import ast
import re
from pathlib import Path

import pytest

# closes: #893

_REPO_ROOT = Path(__file__).parents[2]
_SRC = _REPO_ROOT / "src" / "nodus"


def _bare_tomllib_importers() -> list[str]:
    """Modules that `import tomllib` outside a try/except fallback."""
    offenders = []
    for path in _SRC.rglob("*.py"):
        # utf-8-sig: a BOM on any source file would otherwise crash ast.parse.
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            # An import of tomllib not nested inside a Try is unguarded.
            if isinstance(node, ast.Import) and any(a.name == "tomllib" for a in node.names):
                guarded = any(
                    isinstance(parent, ast.Try) and _contains(parent, node)
                    for parent in ast.walk(tree)
                )
                if not guarded:
                    offenders.append(path.relative_to(_REPO_ROOT).as_posix())
    return offenders


def _contains(parent: ast.AST, child: ast.AST) -> bool:
    return any(node is child for node in ast.walk(parent))


def test_no_module_imports_tomllib_without_a_fallback():
    offenders = _bare_tomllib_importers()
    assert not offenders, (
        "a bare `import tomllib` breaks Python 3.10 (stdlib from 3.11 only); "
        f"guard it like user_config.py does: {offenders}"
    )


def test_tomli_is_declared_for_310():
    pyproject = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    deps = re.search(r"dependencies = \[(.*?)\]", pyproject, re.S)
    assert deps, "no dependencies block found"
    assert re.search(r'tomli\b.*python_version\s*<\s*["\']3\.11["\']', deps.group(1)), (
        "tomli must be a dependency for python_version < 3.11, or the tomllib "
        "fallback has nothing to import on 3.10"
    )


@pytest.mark.parametrize("module", ["nodus.tooling.project", "nodus.tooling.user_config"])
def test_the_toml_loaders_import(module):
    """They import on the test interpreter; the 3.10 proof is the py310-floor CI job."""
    __import__(module)
