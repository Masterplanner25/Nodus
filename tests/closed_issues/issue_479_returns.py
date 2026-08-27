"""Closed-issue test for #479's second half: `returns:` on a workflow step.

A step declared no output type. A dependent received it untyped, and nothing
declared or checked the contract between them — in a construct whose whole point
is that steps are separable units run out of order and across processes, which
makes it the boundary most worth typing.

`with { returns: "int" }` is checked the way a function's return type is: by
setting the analyzer's `current_return` for the walk of the step body, so every
`return` inside it goes through the same comparison. The body was already walked
(#401); it simply had nothing to check its own returns against.

Its prerequisite was #609 — a bare type name that silently meant `any` when
misspelled would have made this a declared-but-inert field, the exact shape this
cluster has been removing.
"""

import sys

from pathlib import Path

# closes: #479

_REPO_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.tooling.runner import check_source  # noqa: E402


def _check(step_body: str, extra_steps: str = "") -> dict:
    src = f"workflow w {{\n    {step_body}\n{extra_steps}}}\nfn main() {{ run_workflow(w) }}\n"
    return check_source(src, filename=None)


def _error(result: dict) -> str:
    return ((result.get("error") or {}).get("message") or "").strip()


def test_a_declared_return_is_checked():
    bad = _check('step a with { returns: "int" } { return "not an int" }')
    assert not bad["ok"]
    assert "expected int but got string" in _error(bad), _error(bad)


def test_a_matching_return_passes():
    assert _check('step a with { returns: "int" } { return 1i }')["ok"]


def test_an_undeclared_step_is_unchanged():
    """`returns:` is opt-in; a step without it is checked exactly as before."""
    assert _check('step a { return "anything at all" }')["ok"]


def test_the_new_type_names_work_here_too():
    """#609 added `map` and `nil` and made `record` spellable — this is a
    surface that would have silently accepted a misspelling without it."""
    assert _check('step a with { returns: "map" } { return {"k": 1i} }')["ok"]
    assert _check('step a with { returns: "nil" } { return }')["ok"]


def test_an_unknown_type_name_is_an_error_not_a_warning():
    """Unlike a function annotation (#609 warns until 6.0.0), this is refused.

    The option is new, so nothing can already rely on a misspelling being
    ignored — and a `returns:` that silently meant "any type at all" would be
    the declared-but-inert field this issue is about.
    """
    result = _check('step a with { returns: "itn" } { return 1i }')
    assert not result["ok"]
    message = _error(result)
    assert "unknown type 'itn'" in message, message
    assert "did you mean 'int'" in message, message


def test_the_type_name_must_be_quoted():
    result = _check("step a with { returns: int } { return 1i }")
    assert not result["ok"]
    assert "must be a type name in quotes" in _error(result), _error(result)


def test_returns_describes_the_step_not_the_edge():
    """D2 deferred this, and running it settles it.

    A skipped producer binds `nil` in its dependent — that is the *edge's*
    behaviour and `on: ["skipped"]` is how a dependent opts into it. `returns:`
    describes what the step returns **when it completes**. The two are different
    questions, and a `returns: "int"` that implied "the dependent receives an
    int" would be false the moment the producer was skipped.

    So `returns:` does not imply nullable, and declaring it on a step that may be
    skipped is not an error.
    """
    result = _check(
        'step gate { if (false) { checkpoint "go" } return 1i }',
        '    step produce after gate when reached("go") with { returns: "int" } { return 42i }\n'
        '    step consume after produce with { on: ["completed", "skipped"] } { return 0i }\n',
    )
    assert result["ok"], _error(result)
