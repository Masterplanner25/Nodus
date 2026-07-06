"""Tests for break / continue loop control (#309).

Covers all three loop forms (while, for, foreach), continue's re-run of the
for-increment, nesting (inner loop only), the foreach-iterator pop on break,
formatter round-trip, and the compile-time guards (outside a loop, and crossing
a try/catch/finally boundary).
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.frontend.lexer import tokenize  # noqa: E402
from nodus.frontend.parser import Parser  # noqa: E402
from nodus.frontend.ast.ast_nodes import Break, Continue  # noqa: E402
from nodus.tooling.formatter import format_source  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402


def _parse(src: str) -> list:
    return Parser(tokenize(src)).parse()


def _run(src: str) -> str:
    result = NodusRuntime(timeout_ms=None).run_source(src)
    assert result["ok"], result.get("error")
    return result.get("stdout", "").strip()


def _run_raw(src: str):
    return NodusRuntime(timeout_ms=None).run_source(src)


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------

def test_parse_break_and_continue_nodes():
    stmts = _parse("while (true) {\n  break\n  continue\n}\n")
    body = stmts[0].body.stmts
    assert isinstance(body[0], Break)
    assert isinstance(body[1], Continue)


# --------------------------------------------------------------------------
# while
# --------------------------------------------------------------------------

# closes: #309
def test_while_break():
    src = 'let i = 0i\nwhile (true) {\n  if (i == 3i) { break }\n  i += 1i\n}\nprint(i)\n'
    assert _run(src) == "3"


def test_while_continue_skips_iteration():
    # Sum only odd numbers 1..9 -> 25.
    src = (
        "let j = 0i\nlet s = 0i\n"
        "while (j < 10i) {\n  j += 1i\n  if (j % 2i == 0i) { continue }\n  s += j\n}\n"
        "print(s)\n"
    )
    assert _run(src) == "25"


# --------------------------------------------------------------------------
# for
# --------------------------------------------------------------------------

def test_for_break():
    src = 'let last = 0i\nfor (let k = 0i; k < 100i; k += 1i) {\n  if (k == 5i) { break }\n  last = k\n}\nprint(last)\n'
    assert _run(src) == "4"


def test_for_continue_reruns_increment():
    # If continue skipped the increment, this would loop forever. It must not.
    # Count multiples of 3 in [0, 10) -> {0,3,6,9} = 4.
    src = (
        "let c = 0i\n"
        "for (let m = 0i; m < 10i; m += 1i) {\n  if (m % 3i != 0i) { continue }\n  c += 1i\n}\n"
        "print(c)\n"
    )
    assert _run(src) == "4"


# --------------------------------------------------------------------------
# foreach
# --------------------------------------------------------------------------

def test_foreach_break():
    src = 'let seen = 0i\nfor x in [10i, 20i, 30i, 40i] {\n  if (x == 30i) { break }\n  seen += 1i\n}\nprint(seen)\n'
    assert _run(src) == "2"


def test_foreach_continue():
    src = 'let t = 0i\nfor y in [1i, -1i, 2i, -2i, 3i] {\n  if (y < 0i) { continue }\n  t += y\n}\nprint(t)\n'
    assert _run(src) == "6"


def test_foreach_break_does_not_strand_iterator():
    # The GET_ITER iterator lives on the VM stack; break must POP it so code
    # after the loop runs on a clean stack. A leaked iterator would corrupt the
    # following expression's operands.
    src = (
        'let hit = "no"\n'
        'for x in [1i, 2i, 3i] {\n  if (x == 2i) { break }\n}\n'
        'hit = "yes"\n'
        'print(hit)\n'
    )
    assert _run(src) == "yes"


# --------------------------------------------------------------------------
# nesting
# --------------------------------------------------------------------------

def test_break_targets_innermost_loop_only():
    src = (
        "let pairs = 0i\n"
        "for a in [1i, 2i, 3i] {\n"
        "  for b in [1i, 2i, 3i] {\n    if (b == 2i) { break }\n    pairs += 1i\n  }\n"
        "}\n"
        "print(pairs)\n"
    )
    assert _run(src) == "3"


# --------------------------------------------------------------------------
# formatter
# --------------------------------------------------------------------------

def test_formatter_roundtrips_break_continue():
    src = (
        "while (true) {\n"
        "    if (x) {\n        break\n    }\n"
        "    continue\n"
        "}\n"
    )
    assert format_source(src) == src


# --------------------------------------------------------------------------
# compile-time guards
# --------------------------------------------------------------------------

def test_break_outside_loop_is_error():
    result = _run_raw("break\n")
    assert not result["ok"]
    assert "outside a loop" in result.get("error", {}).get("message", "")


def test_continue_outside_loop_is_error():
    result = _run_raw("fn f() {\n  continue\n}\nf()\n")
    assert not result["ok"]
    assert "outside a loop" in result.get("error", {}).get("message", "")


def test_break_across_try_boundary_is_error():
    src = "while (true) {\n  try {\n    break\n  } catch e {\n    print(e)\n  }\n}\n"
    result = _run_raw(src)
    assert not result["ok"]
    assert "try/catch/finally" in result.get("error", {}).get("message", "")


def test_continue_across_try_boundary_is_error():
    src = "for x in [1i] {\n  try {\n    continue\n  } catch e { print(e) }\n}\n"
    result = _run_raw(src)
    assert not result["ok"]
    assert "try/catch/finally" in result.get("error", {}).get("message", "")


def test_loop_inside_try_allows_break():
    # break targets a loop wholly inside the try -> does not cross the boundary.
    src = 'try {\n  while (true) {\n    break\n  }\n} catch e { print(e) }\nprint("ok")\n'
    assert _run(src) == "ok"
