"""A parameter keeps its argument when a later local reuses its name (#949).

The compiler records one slot per local *name* (`FunctionInfo.local_slots`), and
a later definition overwrote an earlier one. `STORE_ARG` binds each argument
through that map by name. So in `fn f(text) { ... let text = ... }` the argument
went into the later local's slot, and reads of the parameter, which use the
parameter's own slot, saw `nil` from function entry. The same held for a `for`
variable or a `catch` variable named like a parameter.

Closure capture looked slots up through the same map. A closure capturing `x`,
in a function that also declares another `x` inside a block, captured whichever
`x` was declared last. The upvalue already records the slot the compiler
resolved; capture now uses it.

A third reader, the durability check that decides what a checkpoint would have
to save, walked the map by name. It could not see a slot whose name had been
taken over, so it missed whatever was held there. It now walks every slot.

What is NOT here: `fn f(x) { let x = x + 1i }`, and a read before a block's
`let`. Those see nil for a different reason, block hoisting and the `let`
compile order, and are #957.
"""

import sys
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus.runtime.embedding import NodusRuntime  # noqa: E402


def _run(source: str) -> list[str]:
    result = NodusRuntime(timeout_ms=None).run_source(source)
    if not result.get("ok"):
        raise AssertionError(str((result.get("error") or {}).get("message") or result))
    return (result.get("stdout") or "").split()


# closes: #949
class AParameterKeepsItsArgument(unittest.TestCase):
    def test_a_let_of_the_same_name_in_a_nested_block(self):
        source = (
            "fn f(text) {\n"
            "    print(text)\n"
            "    let i = 0i\n"
            "    while (i < 1i) {\n"
            '        let text = "inner"\n'
            "        print(text)\n"
            "        i = i + 1i\n"
            "    }\n"
            "    print(text)\n"
            "}\n"
            'f("param")\n'
        )
        self.assertEqual(_run(source), ["param", "inner", "param"])

    def test_a_for_variable_of_the_same_name(self):
        source = (
            "fn g(item) {\n"
            "    print(item)\n"
            "    for item in [1i, 2i] {\n"
            "        print(item)\n"
            "    }\n"
            "}\n"
            'g("param")\n'
        )
        self.assertEqual(_run(source), ["param", "1", "2"])

    def test_a_catch_variable_of_the_same_name(self):
        source = (
            "fn h(e) {\n"
            "    print(e)\n"
            "    try {\n"
            '        throw "boom"\n'
            "    } catch e {\n"
            "        print(e)\n"
            "    }\n"
            "}\n"
            'h("param")\n'
        )
        self.assertEqual(_run(source), ["param", "boom"])

    def test_a_function_expression(self):
        # A function value is compiled by the same code; checked anyway, because
        # the report names both forms.
        source = (
            "let f = fn(text) {\n"
            "    print(text)\n"
            "    if (true) {\n"
            '        let text = "inner"\n'
            "    }\n"
            "}\n"
            'f("param")\n'
        )
        self.assertEqual(_run(source), ["param"])

    def test_several_parameters_each_keep_their_own(self):
        source = (
            "fn f(a, b, c) {\n"
            "    if (true) {\n"
            "        let b = 0i\n"
            "        let a = 0i\n"
            "    }\n"
            "    print(a)\n"
            "    print(b)\n"
            "    print(c)\n"
            "}\n"
            "f(1i, 2i, 3i)\n"
        )
        self.assertEqual(_run(source), ["1", "2", "3"])


# closes: #949
class AClosureCapturesTheVariableItNames(unittest.TestCase):
    def test_the_outer_variable_when_a_block_shadows_it(self):
        source = (
            "fn f() {\n"
            "    let x = 1i\n"
            "    if (true) {\n"
            "        let x = 2i\n"
            "    }\n"
            "    return fn() {\n"
            "        return x\n"
            "    }\n"
            "}\n"
            "print(f()())\n"
        )
        self.assertEqual(_run(source), ["1"])

    def test_the_inner_variable_when_captured_inside_the_block(self):
        # The control: capturing inside the block must still get the inner one.
        source = (
            "fn f() {\n"
            "    let x = 1i\n"
            "    let fs = []\n"
            "    if (true) {\n"
            "        let x = 2i\n"
            "        push(fs, fn() {\n"
            "            return x\n"
            "        })\n"
            "    }\n"
            "    return fs[0i]()\n"
            "}\n"
            "print(f())\n"
        )
        self.assertEqual(_run(source), ["2"])

    def test_a_captured_parameter_with_a_later_shadow(self):
        source = (
            "fn f(a) {\n"
            "    let get = fn() {\n"
            "        return a\n"
            "    }\n"
            "    if (true) {\n"
            '        let a = "inner"\n'
            "    }\n"
            "    return get()\n"
            "}\n"
            'print(f("param"))\n'
        )
        self.assertEqual(_run(source), ["param"])

    def test_the_captured_variable_is_shared_not_copied(self):
        # Capture by slot must still hand back the same Cell the frame uses.
        source = (
            "fn f() {\n"
            "    let n = 0i\n"
            "    let bump = fn() {\n"
            "        n = n + 1i\n"
            "    }\n"
            "    bump()\n"
            "    bump()\n"
            "    return n\n"
            "}\n"
            "print(f())\n"
        )
        self.assertEqual(_run(source), ["2"])


# closes: #949
class TheDurabilityCheckSeesEverySlot(unittest.TestCase):
    def test_a_slot_no_name_points_at_is_still_listed(self):
        from types import SimpleNamespace

        from nodus.runtime.durability import _frame_locals

        # Slot 1 is a shadowed `x`: the name map points `x` at slot 0 only.
        frame = SimpleNamespace(locals={}, locals_array=["outer", "held"],
                                locals_name_to_slot={"x": 0})
        listed = dict(_frame_locals(frame))
        self.assertEqual(listed.get("x"), "outer")
        self.assertIn("held", listed.values(), "a slot the name map does not reach was skipped")


if __name__ == "__main__":
    unittest.main()
