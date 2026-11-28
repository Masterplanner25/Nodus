"""Closed-issue test for #609: an unrecognised type name is a syntax error.

`parse_type_name` in the parser was `return self.eat("ID").val` — no validation
at all — and `type_system.parse_type_name` was `TYPE_NAMES.get(name, ANY)`. So
one transposed letter turned a parameter into `any` and disabled checking on it
forever, with no diagnostic at any altitude. Two consequences followed from the
same hole: `map` was absent from `TYPE_NAMES` while looking nameable, and
`record` was present but is a keyword, so it could never reach the lookup.

5.6.0 through 5.21.0 warned. Since 6.0.0 the parser refuses the name, at its
token, with a suggestion -- so every consumer (`nodus run`, `nodus check`, the
editor) reports it the same way, because each one parses.
"""

import os
import subprocess
import sys
import tempfile

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.frontend.lexer import tokenize  # noqa: E402
from nodus.frontend.parser import Parser  # noqa: E402
from nodus.frontend.type_system import TYPE_NAMES, is_known_type_name  # noqa: E402
from nodus.runtime.diagnostics import ERROR_SEVERITY, LangSyntaxError  # noqa: E402
from nodus.tooling.diagnostics import WorkspaceDiagnosticEngine  # noqa: E402
from nodus.tooling.runner import check_source  # noqa: E402

_TYPO = 'fn b(name: strng) -> string { return name }\nfn main() { print(b("x")) }\n'


def _parse(src: str):
    return Parser(tokenize(src)).parse()


# --- 1. the hole itself ----------------------------------------------------

# closes: #609
def test_an_unknown_type_name_is_a_syntax_error_with_a_suggestion():
    with pytest.raises(LangSyntaxError) as caught:
        _parse(_TYPO)
    err = caught.value
    assert "Unknown type name 'strng'" in str(err)
    assert "did you mean 'string'?" in str(err), "the close match is what makes it actionable"
    assert (err.line, err.col) == (1, 12), "must point at the annotation, not the fn"


def test_a_correct_annotation_parses():
    _parse('fn a(name: string) -> string { return name }\n')


# --- 2. the two names the hole hid -----------------------------------------

def test_map_and_nil_and_record_are_spellable():
    """`record` was a dead entry and `map` was missing entirely."""
    for name in ("map", "nil", "record"):
        assert is_known_type_name(name), f"{name} must be a real type name"

    # `record` and `nil` are keywords, so they never arrive as an `ID`. Parsing
    # is the half that used to fail with `Expected identifier, got 'record'`.
    _parse(
        "fn m(y: map) -> map { return y }\n"
        "fn r() -> record { return record {x: 1i} }\n"
        "fn n() -> nil { return }\n"
    )


# --- 3. one question, one answer -------------------------------------------

def test_every_consumer_refuses_it_at_the_same_token():
    """`nodus run`, `nodus check` and the editor must not each decide.

    This is the #401 / #597 shape: two walkers over one question drift. Since
    the flip the parser raises, so each consumer reports the same error at the
    same position -- asserted together, because an isolated assertion passes on
    whichever consumer is already correct.
    """
    result = check_source(_TYPO, filename=None)
    assert result.get("ok") is False
    from_check = (result["error"]["line"], result["error"]["column"])

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "typo.nd")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(_TYPO)
        diagnostics = WorkspaceDiagnosticEngine().analyze(path).diagnostics_by_file
        env = dict(os.environ, PYTHONPATH=str(_REPO_ROOT / "src"))
        runs = [subprocess.run([sys.executable, "-m", "nodus", "run", path], cwd=tmp, env=env,
                               capture_output=True, text=True, timeout=120)
                for _ in (1, 2)]  # cold, then warm
    from_editor = [
        (d.line, d.column) for diags in diagnostics.values() for d in diags
        if d.severity == ERROR_SEVERITY and "Unknown type name 'strng'" in d.message
    ]
    assert from_check == (1, 12)
    assert from_editor == [(1, 12)], "the editor walker disagrees with the parser"
    for run in runs:
        assert run.returncode == 1, run.stdout + run.stderr
        assert "typo.nd:1:12: Unknown type name 'strng'" in run.stderr, run.stderr


def test_the_parser_drives_off_the_one_vocabulary():
    """Assert on the source, not just the behaviour.

    A behaviour-only test passes if the parser grows its own hardcoded tuple of
    type names beside `TYPE_NAMES`; that is exactly how two enumerations of one
    vocabulary drift apart. `is_known_type_name` is the single entry point.
    """
    source = (_REPO_ROOT / "src" / "nodus" / "frontend" / "parser.py").read_text(encoding="utf-8")
    assert "is_known_type_name(" in source, (
        "parse_type_name must consult type_system.is_known_type_name rather than "
        "test membership against a list of its own"
    )
    # Every name the vocabulary holds must actually parse as an annotation.
    for name in sorted(TYPE_NAMES):
        _parse(f"fn f(x: {name}) {{ return x }}\n")
