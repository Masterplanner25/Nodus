"""Closed-issue test for #609: an unrecognised type name is no longer silent.

`parse_type_name` in the parser was `return self.eat("ID").val` — no validation
at all — and `type_system.parse_type_name` was `TYPE_NAMES.get(name, ANY)`. So
one transposed letter turned a parameter into `any` and disabled checking on it
forever, with no diagnostic at any altitude. Two consequences followed from the
same hole: `map` was absent from `TYPE_NAMES` while looking nameable, and
`record` was present but is a keyword, so it could never reach the lookup.

Staged like #545 and #547: a warning in 5.x, an error at 6.0.0.

The tests below cover four things, and the third is the one that matters
structurally.
"""

import os
import sys
import tempfile

from pathlib import Path

# closes: #609

_REPO_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.frontend.lexer import tokenize  # noqa: E402
from nodus.frontend.parser import Parser  # noqa: E402
from nodus.frontend.type_system import TYPE_NAMES, is_known_type_name  # noqa: E402
from nodus.runtime.diagnostics import WARNING_SEVERITY  # noqa: E402
from nodus.tooling.diagnostics import WorkspaceDiagnosticEngine  # noqa: E402
from nodus.tooling.runner import check_source  # noqa: E402

_TYPO = 'fn b(name: strng) -> string { return name }\nfn main() { print(b("x")) }\n'


def _parse(src: str) -> Parser:
    parser = Parser(tokenize(src))
    parser.parse()
    return parser


# --- 1. the hole itself ----------------------------------------------------

def test_unknown_type_name_is_recorded_with_a_suggestion():
    parser = _parse(_TYPO)
    assert len(parser.unknown_type_names) == 1
    unknown = parser.unknown_type_names[0]
    assert unknown.name == "strng"
    assert unknown.suggestion == "string", "the close match is what makes it actionable"
    assert (unknown.line, unknown.col) == (1, 12), "must point at the annotation, not the fn"


def test_a_correct_annotation_records_nothing():
    parser = _parse('fn a(name: string) -> string { return name }\n')
    assert parser.unknown_type_names == []


# --- 2. the two names the hole hid -----------------------------------------

def test_map_and_nil_and_record_are_spellable():
    """`record` was a dead entry and `map` was missing entirely."""
    for name in ("map", "nil", "record"):
        assert is_known_type_name(name), f"{name} must be a real type name"

    # `record` and `nil` are keywords, so they never arrive as an `ID`. Parsing
    # is the half that used to fail with `Expected identifier, got 'record'`.
    parser = _parse(
        "fn m(y: map) -> map { return y }\n"
        "fn r() -> record { return record {x: 1i} }\n"
        "fn n() -> nil { return }\n"
    )
    assert parser.unknown_type_names == []


# --- 3. one question, one answer -------------------------------------------

def test_both_consumers_report_the_same_unknown_names():
    """`nodus check` and the editor walker must not each decide for themselves.

    This is the #401 / #597 shape: two walkers over one question drift, and the
    one that never learned the case fails silently. Both read the parser's list,
    and this asserts they agree rather than asserting each in isolation — an
    isolated assertion passes on whichever consumer is already correct.
    """
    parser = _parse(_TYPO)
    expected = {(u.name, u.line, u.col) for u in parser.unknown_type_names}
    assert expected, "the fixture must actually contain an unknown type name"

    result = check_source(_TYPO, filename=None)
    from_check = {
        (w["message"].split("'")[1], w["line"], w["column"])
        for w in (result.get("warnings") or [])
    }
    assert from_check == expected, "nodus check disagrees with the parser"

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "typo.nd")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(_TYPO)
        diagnostics = WorkspaceDiagnosticEngine().analyze(path).diagnostics_by_file
    from_editor = {
        (d.message.split("'")[1], d.line, d.column)
        for diags in diagnostics.values()
        for d in diags
        if d.severity == WARNING_SEVERITY and d.message.startswith("Unknown type name")
    }
    assert from_editor == expected, "the editor walker disagrees with the parser"


# --- 4. staging: a warning, not yet an error -------------------------------

def test_an_unknown_type_name_warns_and_does_not_fail_the_check():
    result = check_source(_TYPO, filename=None)
    assert result.get("ok") is True, (
        "until 6.0.0 this is a warning — failing now would break projects that "
        "check clean today, which is why #545 and #547 stage the same way"
    )
    warnings = result.get("warnings") or []
    assert len(warnings) == 1
    assert "6.0.0" in warnings[0]["message"], "the message must say when it starts failing"


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
        parser = _parse(f"fn f(x: {name}) {{ return x }}\n")
        assert parser.unknown_type_names == [], f"{name} is in TYPE_NAMES but does not parse"
