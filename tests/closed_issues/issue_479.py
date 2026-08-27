"""Closed-issue test for #479: the tool declaration is checked against its handler.

#479 asks for `tool.register` to *derive* its schema from the handler's
signature. Building it found that describes a shape this registry does not have.

**A tool handler takes exactly one parameter: the args record.** `tool_invoke`
calls `run_closure(handler, [args])` — one argument, always. So the `schema`
names the keys of that one record, and a signature cannot carry them. The
issue's own example (`fn greet(name: string, times: int)` as a handler)
registered fine on `main` and then died on invoke with a bare `Stack underflow`;
that defect is #624.

What the signature *can* check is **arity**, which is what was going unchecked —
the issue's premise ("the declaration and the function it declares are
independent artifacts") holds exactly, on a different field than it expected.

Two other things land here, both prerequisites the issue names:

- the compiler no longer discards the declared signature, which is what
  `returns:` will need;
- `_NODUS_TO_JSON_TYPE` stops being a third enumeration of the type vocabulary.
"""

import sys

from pathlib import Path

# closes: #479

_REPO_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus import NodusRuntime  # noqa: E402
from nodus.builtins.nodus_builtins import BUILTIN_NAMES  # noqa: E402
from nodus.builtins.tool_module import (  # noqa: E402
    _NODUS_TO_JSON_TYPE,
    _UNSCHEMABLE_TYPES,
)
from nodus.compiler.compiler import Compiler  # noqa: E402
from nodus.frontend.lexer import tokenize  # noqa: E402
from nodus.frontend.parser import Parser  # noqa: E402
from nodus.frontend.type_system import TYPE_NAMES  # noqa: E402


def _register(handler_params: str, extra: str = "") -> dict:
    src = (
        'import "std:tool" as tool\n'
        f"fn h({handler_params}) {{ return 1i }}\n"
        "fn main() {\n"
        f'  let r = tool.register({{name: "app.t", handler: h, description: "g"{extra}}})\n'
        '  if (type(r) == "error") { print("REFUSED|\\(r.message)") }\n'
        '  else { print("OK|\\(tool.call("app.t", {a: 1i}))") }\n'
        "}\n"
    )
    result = NodusRuntime().run_source(src)
    assert result["ok"], (result.get("error") or {}).get("message")
    status, _, detail = result["stdout"].strip().partition("|")
    return {"status": status, "detail": detail}


# --- the contract the signature can actually check --------------------------

def test_a_one_parameter_handler_is_the_contract():
    out = _register("args")
    assert out["status"] == "OK", out["detail"]


def test_a_multi_parameter_handler_is_refused_at_registration():
    """It could never be invoked. #624 has the characterisation."""
    out = _register("name, times")
    assert out["status"] == "REFUSED"
    assert "declares 2 parameters" in out["detail"], out["detail"]
    assert "exactly one argument" in out["detail"], out["detail"]
    assert "args record" in out["detail"], (
        "the message must name the contract, or it is just another refusal"
    )


def test_a_zero_parameter_handler_is_refused():
    out = _register("")
    assert out["status"] == "REFUSED"
    assert "takes no parameters" in out["detail"], out["detail"]


def test_the_issues_own_example_is_refused_rather_than_crashing():
    """It registered and then died with `Stack underflow` (#624)."""
    out = _register("name, times", extra=', schema: {city: "string"}')
    assert out["status"] == "REFUSED"
    assert "Stack underflow" not in out["detail"]


# --- the prerequisite the issue names ---------------------------------------

def test_the_compiler_keeps_the_declared_signature():
    """`FunctionInfo.params` was names only, so nothing downstream could see
    what a function declared. `returns:` — the other half of #479 — needs this."""
    ast = Parser(tokenize(
        "fn greet(name: string, times: int) -> string { return name }\n"
        "fn plain(a, b) { return a }\n"
    )).parse()
    compiler = Compiler(module_infos=None, module_defs_index={},
                        builtin_names=set(BUILTIN_NAMES))
    compiler.compile_program(ast)

    greet = compiler.functions["greet"]
    assert greet.param_types == ["string", "int"]
    assert greet.return_type == "string"

    plain = compiler.functions["plain"]
    assert plain.param_types == [None, None], "unannotated stays unannotated"
    assert plain.return_type is None


# --- one vocabulary, not three ----------------------------------------------

def test_the_tool_schema_vocabulary_covers_every_type_name():
    """`_NODUS_TO_JSON_TYPE` was a private list of seven and had already drifted.

    Driven off `TYPE_NAMES` so a tenth type cannot be added in one place and
    missed here — the same reason #609 put the parser on `is_known_type_name`.
    """
    covered = set(_NODUS_TO_JSON_TYPE) | set(_UNSCHEMABLE_TYPES) | {"any"}
    missing = sorted(set(TYPE_NAMES) - covered)
    assert not missing, (
        f"type name(s) {missing} exist in the language but have no answer in a "
        "tool schema — map them, or name them in _UNSCHEMABLE_TYPES with a reason"
    )
    unknown = sorted(covered - set(TYPE_NAMES))
    assert not unknown, f"tool schema names type(s) the language does not have: {unknown}"


def test_record_is_schemable_and_function_is_refused_with_a_reason():
    assert _NODUS_TO_JSON_TYPE["record"] == "object"
    assert "function" in _UNSCHEMABLE_TYPES
    out = _register("args", extra=', schema: {cb: "function"}')
    assert out["status"] == "REFUSED"
    assert "cannot appear in a tool schema" in out["detail"], out["detail"]
