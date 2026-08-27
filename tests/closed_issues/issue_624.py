"""Closed-issue test for #624: the tool handler contract, and the doc that taught it wrong.

A tool handler is called with **exactly one argument** — the args record
(`run_closure(handler, [args])`). A handler declaring any other number could
never run, and registration accepted it; the failure surfaced at *call* time as
a bare `Stack underflow` naming the handler.

The refusal shipped with #479. What this issue adds is the reason anyone wrote a
multi-parameter handler in the first place: **the guide's own example showed
one**, in spirit —

    handler: fn(query) { return http_get("...?q=" + query) }

alongside a `schema` declaring `query`. That reads unmistakably as "the parameter
is the schema key". It is not: `query` is bound to the whole record, so the
example produced `?q=record {"query": "..."}`. The block was allowlisted, so the
doc gate never ran it.

Deciding not to add argument spreading is also recorded here — see
`test_a_single_parameter_handler_receives_the_whole_record`.
"""

import sys

from pathlib import Path

# closes: #624

_REPO_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus import NodusRuntime  # noqa: E402

_GUIDE = _REPO_ROOT / "docs" / "guide" / "ai-primitives.md"


def _run(src: str) -> dict:
    return NodusRuntime().run_source(src)


def test_a_single_parameter_handler_receives_the_whole_record():
    """The contract, pinned — and the reason spreading was not added.

    Supporting `fn(query, limit)` by spreading the record would make the
    one-parameter case ambiguous: is `fn(args)` the whole record, or the value of
    a key named `args`? Backwards compatibility forces the first, which would
    leave the semantics arity-dependent — one rule for one parameter and another
    for two. One clear rule is worth more than the convenience.
    """
    result = _run(
        'import "std:tool" as tool\n'
        "fn main() {\n"
        '  tool.register({name: "app.t", description: "d",\n'
        "                 handler: fn(args) { return args.query },\n"
        '                 schema: {query: "string"}})\n'
        '  print(tool.invoke("app.t", {query: "hello"}))\n'
        "}\n"
    )
    assert result["ok"], (result.get("error") or {}).get("message")
    assert result["stdout"].strip() == "hello"


def test_a_misnamed_single_parameter_still_receives_the_record():
    """`fn(query)` is legal and cannot be refused — which is why the guide says
    to name it `args`. This pins the trap so the doc claim stays true."""
    result = _run(
        'import "std:tool" as tool\n'
        "fn main() {\n"
        '  tool.register({name: "app.t", description: "d",\n'
        "                 handler: fn(query) { return str(query) },\n"
        '                 schema: {query: "string"}})\n'
        '  print(tool.invoke("app.t", {query: "hello"}))\n'
        "}\n"
    )
    assert result["ok"], (result.get("error") or {}).get("message")
    out = result["stdout"].strip()
    assert "record" in out and "query" in out, (
        f"the parameter must receive the whole record, not the value; got {out!r}"
    )


def test_the_guide_documents_the_contract():
    guide = _GUIDE.read_text(encoding="utf-8")
    assert "handler takes exactly one parameter" in guide, (
        "the guide must state the contract, since the natural thing to write is wrong"
    )
    assert "fn(args)" in guide, "the guide must show the correct shape"


def test_the_guides_example_uses_the_correct_shape():
    """The example is what people copy, and it was wrong.

    It is also self-contained and gate-checked now — its allowlist entry stopped
    matching when it changed — so a future edit that reintroduces the wrong shape
    fails `nodus_gate --runtime` rather than sitting there.
    """
    guide = _GUIDE.read_text(encoding="utf-8")
    example_start = guide.index("myapp.search")
    example = guide[example_start:example_start + 600]
    assert "handler: fn(args)" in example, (
        "the registration example must take the args record"
    )
    assert "args.query" in example, "and must read the field off it"
