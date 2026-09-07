"""`copy(value)` — the deep-copy surface #814 decided was owed.

Assignment binds a reference (`tests/test_container_aliasing.py`), so before
this there was no way to hand a container somewhere and keep it from being
changed underneath you. Two of the three container kinds had an awkward
workaround — `col.map(xs, fn(x) { return x })` over a list, `keys()` and a loop
over a map — and **records had none**, because `keys()` refuses a record and its
fields cannot be enumerated.

Three decisions this file pins, each recorded in
`docs/design/v5/09-container-aliasing.md`:

* **Deep, not shallow.** Shallow is the option that was already expressible, and
  it is the one that gives false confidence — a shallow copy of
  `{"inner": [1, 2]}` still shares `inner`, which is precisely the case the
  caller thinks they have protected against.
* **Shared structure is preserved, not duplicated.** Two fields pointing at one
  list still point at one list afterwards, and a **cycle terminates**. That is a
  requirement rather than a refinement: all three container kinds can hold a
  reference to themselves (`list_push(a, a)`, `m["self"] = m`, `r.x = r`), all
  three verified constructible, so a memo-less implementation would hang.
* **A live handle is refused, naming where it is.** This reuses the line the
  language already draws — a `state` cell refuses a closure or a channel for the
  same reason (#498) — rather than inventing a second rule. Sharing the
  uncopyable leaf would return a "copy" that is not one, silently.

The error path is tested per container kind and at depth, because **the path in
the message is the useful half**: a record with fifteen fields, one of which
holds a handler, is the case this is met on.
"""

import io
import unittest
from contextlib import redirect_stdout

import nodus as lang
from nodus.runtime.diagnostics import LangRuntimeError
from nodus.runtime.module_loader import ModuleLoader


def run_program(src: str, source_path: str | None = None) -> list[str]:
    vm = lang.VM([], {}, code_locs=[], source_path=source_path)
    _loader = ModuleLoader(project_root=None, vm=vm)
    buf = io.StringIO()
    with redirect_stdout(buf):
        _loader.load_module_from_source(
            src, module_name=source_path or "<memory>", base_dir=None
        )
    return buf.getvalue().splitlines()


class CopyIsDeepTests(unittest.TestCase):
    """The property the surface exists for."""

    # closes: #814
    def test_a_copied_list_does_not_share_its_elements(self):
        src = """
let original = [1i, 2i, 3i]
let snapshot = copy(original)
snapshot[0] = 999i
print(original[0])
print(snapshot[0])
"""
        self.assertEqual(run_program(src), ["1", "999"])

    def test_a_copied_map_does_not_share_its_entries(self):
        src = """
let original = { "x": 1i }
let snapshot = copy(original)
snapshot["x"] = 999i
print(original["x"])
"""
        self.assertEqual(run_program(src), ["1"])

    def test_a_copied_record_does_not_share_its_fields(self):
        """The case with no workaround at all before this."""
        src = """
let original = record { x: 1i }
let snapshot = copy(original)
snapshot.x = 999i
print(original.x)
"""
        self.assertEqual(run_program(src), ["1"])

    def test_a_nested_container_is_copied_not_shared(self):
        """The whole difference between this and a shallow copy."""
        src = """
let original = { "inner": [1i, 2i] }
let snapshot = copy(original)
snapshot["inner"][0] = 999i
print(original["inner"][0])
print(snapshot["inner"][0])
"""
        self.assertEqual(run_program(src), ["1", "999"])

    def test_a_nested_record_is_copied_not_shared(self):
        src = """
let original = record { nested: record { y: 2i } }
let snapshot = copy(original)
snapshot.nested.y = 999i
print(original.nested.y)
"""
        self.assertEqual(run_program(src), ["2"])

    def test_containers_of_mixed_kinds_are_copied_all_the_way_down(self):
        src = """
let original = { "rows": [record { tags: ["a"] }] }
let snapshot = copy(original)
snapshot["rows"][0].tags[0] = "changed"
print(original["rows"][0].tags[0])
print(snapshot["rows"][0].tags[0])
"""
        self.assertEqual(run_program(src), ["a", "changed"])

    def test_a_scalar_copies_to_itself(self):
        src = """
print(copy(1i))
print(copy("hi"))
print(copy(true))
print(copy(nil))
"""
        self.assertEqual(run_program(src), ["1", "hi", "true", "nil"])

    def test_an_empty_container_copies(self):
        src = """
print(len(copy([])))
print(len(copy({})))
"""
        self.assertEqual(run_program(src), ["0", "0"])


class CopyPreservesSharingTests(unittest.TestCase):
    """A copy of a shape, not an expansion of it."""

    def test_two_names_for_one_list_stay_one_list_in_the_copy(self):
        src = """
let shared = [1i]
let holder = { "a": shared, "b": shared }
let snapshot = copy(holder)
snapshot["a"][0] = 7i
print(snapshot["b"][0])
print(shared[0])
"""
        self.assertEqual(run_program(src), ["7", "1"])

    def test_a_self_referential_list_terminates(self):
        src = """
let cyc = [1i]
list_push(cyc, cyc)
let snapshot = copy(cyc)
print(len(snapshot))
print(len(snapshot[1]))
"""
        self.assertEqual(run_program(src), ["2", "2"])

    def test_a_self_referential_map_terminates(self):
        src = """
let m = { "n": 1i }
m["self"] = m
let snapshot = copy(m)
print(len(keys(snapshot)))
print(snapshot["self"]["n"])
"""
        self.assertEqual(run_program(src), ["2", "1"])

    def test_a_self_referential_record_terminates(self):
        src = """
let r = record { x: 1i, me: nil }
r.me = r
let snapshot = copy(r)
print(snapshot.me.x)
"""
        self.assertEqual(run_program(src), ["1"])

    def test_the_copy_of_a_cycle_is_its_own_cycle(self):
        """Not a copy pointing back at the original — that would leak the alias."""
        src = """
let cyc = [1i]
list_push(cyc, cyc)
let snapshot = copy(cyc)
snapshot[0] = 999i
print(snapshot[1][0])
print(cyc[0])
"""
        self.assertEqual(run_program(src), ["999", "1"])


class CopyRefusesLiveHandlesTests(unittest.TestCase):
    """The message names *where*, which is the useful half."""

    def _error(self, src: str) -> str:
        with self.assertRaises(LangRuntimeError) as caught:
            run_program(src)
        return str(caught.exception)

    def test_a_bare_function_is_refused(self):
        message = self._error("copy(fn(x) { return x })")
        self.assertIn("cannot copy a function", message)

    def test_a_function_in_a_record_field_is_named(self):
        message = self._error(
            "let r = record { handler: fn(x) { return x } }\ncopy(r)"
        )
        self.assertIn("the value at handler (function)", message)

    def test_a_function_in_a_map_is_named_by_key_and_index(self):
        message = self._error(
            'let m = { "items": [1i, fn(x) { return x }] }\ncopy(m)'
        )
        self.assertIn('the value at ["items"][1] (function)', message)

    def test_a_channel_is_refused(self):
        message = self._error("let ch = channel()\ncopy(record { c: ch })")
        self.assertIn("the value at c (channel)", message)

    def test_a_stdlib_record_holding_methods_is_refused_and_says_method(self):
        """`std:hash` returns a record whose fields are builtin methods.

        `type()` reports a BuiltinMethod as `unknown`, which would make this
        message useless on exactly the values people meet it on, so the copy
        error names it itself rather than widening `type()` — a separate surface
        with #609's type-name work staged against it.
        """
        message = self._error('import "std:hash" as hash\ncopy(hash.sha256("x"))')
        self.assertIn("(method)", message)
        self.assertNotIn("unknown", message)

    def test_the_refusal_says_why(self):
        message = self._error("copy(fn(x) { return x })")
        self.assertIn("has no meaningful copy", message)


class CopyIsAnOrdinaryGlobalTests(unittest.TestCase):
    """A new global cannot break an existing program.

    Guest code can shadow a builtin name with its own `fn` — verified at 5.9.0
    (#170) and again at 5.11.0 for `sleep_until` / `spawn_after`. Re-checked here
    because it is the whole argument for adding a global rather than putting this
    in `std:collections`.
    """

    def test_a_user_function_named_copy_shadows_the_builtin(self):
        src = """
fn copy(x) { return "mine" }
print(copy([1i]))
"""
        self.assertEqual(run_program(src), ["mine"])

    def test_copy_needs_no_import(self):
        self.assertEqual(run_program("print(len(copy([1i, 2i])))"), ["2"])


class CopyAnswersTheAliasingProblemTests(unittest.TestCase):
    """End to end: the thing that was inexpressible before."""

    def test_a_callee_cannot_change_the_caller_s_container(self):
        src = """
fn tamper(items) { items[0] = 999i }
let mine = [1i]
tamper(copy(mine))
print(mine[0])
"""
        self.assertEqual(run_program(src), ["1"])

    def test_a_step_body_cannot_change_a_copied_container(self):
        """The case the design doc argues from — handing data into a step."""
        src = """
let mine = [1i]
let handed = copy(mine)
workflow w {
    step touch {
        handed[0] = 999i
        return "ok"
    }
}
let r = run_workflow(w)
print(mine[0])
print(handed[0])
"""
        self.assertEqual(run_program(src, source_path="copy.nd"), ["1", "999"])


if __name__ == "__main__":
    unittest.main()
