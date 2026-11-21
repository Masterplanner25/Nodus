"""`let` is lexical (#957).

A name means the outer binding until the `let` that shadows it, and a function
literal bound by `let` can call itself. Before this, three compiler decisions
each handed a program `nil`, with no error:

- `predeclare_block` defined every `let` in a block before the block's first
  statement, so a read before the `let` saw the new, empty variable.
- `let` defined its name before compiling the initializer, so
  `let x = x + 1i` read the new `x`, and failed with `Cannot add nil and int`.
- The slot was reset *after* the initializer had built a closure. The closure
  held the old cell, so `let fact = fn(n) { ... fact(n - 1i) }` called `nil`.

The rule is now in `docs/language/LANGUAGE_SPEC.md` under Variables and Assignment.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus.runtime.embedding import NodusRuntime  # noqa: E402


def _run(source: str) -> list[str]:
    result = NodusRuntime(timeout_ms=None).run_source(source)
    if not result.get("ok"):
        raise AssertionError(str((result.get("error") or {}).get("message") or result))
    return (result.get("stdout") or "").split()


def _error(source: str) -> str:
    result = NodusRuntime(timeout_ms=None).run_source(source)
    if result.get("ok"):
        raise AssertionError(f"expected an error, got {result.get('stdout')!r}")
    return str((result.get("error") or {}).get("message") or "")


# closes: #957
class TheInitializerSeesTheOuterBinding(unittest.TestCase):
    def test_a_parameter(self):
        self.assertEqual(_run("fn f(x) {\n    let x = x + 1i\n    return x\n}\nprint(f(1i))\n"), ["2"])

    def test_an_outer_local(self):
        source = (
            "fn f() {\n"
            "    let n = 10i\n"
            "    if (true) {\n"
            "        let n = n * 2i\n"
            "        print(n)\n"
            "    }\n"
            "    print(n)\n"
            "}\n"
            "f()\n"
        )
        self.assertEqual(_run(source), ["20", "10"])

    def test_a_destructuring_let_swaps(self):
        source = (
            "fn f() {\n"
            "    let a = 1i\n"
            "    let b = 2i\n"
            "    let [a, b] = [b, a]\n"
            "    return [a, b]\n"
            "}\n"
            "print(f())\n"
        )
        self.assertEqual(_run(source), ["[2,", "1]"])


# closes: #957
class AReadBeforeTheLetSeesTheOuterBinding(unittest.TestCase):
    def test_in_a_nested_block(self):
        source = (
            "fn g() {\n"
            "    let y = 1i\n"
            "    if (true) {\n"
            "        print(y)\n"
            "        let y = 2i\n"
            "        print(y)\n"
            "    }\n"
            "    print(y)\n"
            "}\n"
            "g()\n"
        )
        self.assertEqual(_run(source), ["1", "2", "1"])

    def test_in_the_same_scope_as_a_parameter(self):
        source = "fn k(x) {\n    print(x)\n    let x = 5i\n    print(x)\n}\nk(9i)\n"
        self.assertEqual(_run(source), ["9", "5"])

    def test_a_global_function_until_a_local_shadows_it(self):
        source = (
            'fn helper() {\n    return "global"\n}\n'
            "fn f() {\n"
            "    print(helper())\n"
            '    let helper = fn() {\n        return "local"\n    }\n'
            "    print(helper())\n"
            "}\n"
            "f()\n"
        )
        self.assertEqual(_run(source), ["global", "local"])


# closes: #957
class ALocalClosureCanCallItself(unittest.TestCase):
    def test_factorial(self):
        source = (
            "fn outer() {\n"
            "    let fact = fn(n) {\n"
            "        if (n <= 1i) {\n"
            "            return 1i\n"
            "        }\n"
            "        return n * fact(n - 1i)\n"
            "    }\n"
            "    return fact(5i)\n"
            "}\n"
            "print(outer())\n"
        )
        self.assertEqual(_run(source), ["120"])

    def test_inside_a_loop_each_iteration_gets_its_own(self):
        # The per-iteration reset that loop closures rely on still happens, now
        # before the closure is built rather than after.
        source = (
            "fn f() {\n"
            "    let out = []\n"
            "    for base in [1i, 10i] {\n"
            "        let count = fn(n) {\n"
            "            if (n == 0i) {\n"
            "                return base\n"
            "            }\n"
            "            return count(n - 1i)\n"
            "        }\n"
            "        push(out, count)\n"
            "    }\n"
            "    return [out[0i](3i), out[1i](3i)]\n"
            "}\n"
            "print(f())\n"
        )
        self.assertEqual(_run(source), ["[1,", "10]"])

    def test_mutual_recursion_fails_loudly_not_with_nil(self):
        # Lexical, as in Rust: `odd` is not declared when `even` is compiled.
        # It is an error naming the function, not a call to nil.
        source = (
            "fn rec() {\n"
            "    let even = fn(n) {\n"
            "        if (n == 0i) {\n"
            "            return true\n"
            "        }\n"
            "        return odd(n - 1i)\n"
            "    }\n"
            "    let odd = fn(n) {\n"
            "        return even(n - 1i)\n"
            "    }\n"
            "    return even(4i)\n"
            "}\n"
            "print(rec())\n"
        )
        self.assertIn("odd", _error(source))


class WhatMustNotChange(unittest.TestCase):
    """Controls: behaviour the old compile order already got right."""

    def test_loop_closures_capture_each_iteration(self):
        source = (
            "fn f() {\n"
            "    let fs = []\n"
            "    for i in [1i, 2i, 3i] {\n"
            "        let v = i * 10i\n"
            "        push(fs, fn() {\n            return v\n        })\n"
            "    }\n"
            "    return [fs[0i](), fs[1i](), fs[2i]()]\n"
            "}\n"
            "print(f())\n"
        )
        self.assertEqual(_run(source), ["[10,", "20,", "30]"])

    def test_a_captured_counter_is_shared(self):
        source = (
            "fn f() {\n"
            "    let n = 0i\n"
            "    let bump = fn() {\n        n = n + 1i\n    }\n"
            "    bump()\n"
            "    bump()\n"
            "    return n\n"
            "}\n"
            "print(f())\n"
        )
        self.assertEqual(_run(source), ["2"])

    def test_module_level_redeclaration(self):
        self.assertEqual(_run("let top = 1i\nlet top = top + 1i\nprint(top)\n"), ["2"])

    def test_the_cli_agrees(self):
        # The CLI compiles through the same path; checked once, end to end.
        import subprocess

        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with tempfile.TemporaryDirectory() as directory:
            script = os.path.join(directory, "t.nd")
            with open(script, "w", encoding="utf-8") as handle:
                handle.write("fn f(x) {\n    let x = x + 1i\n    return x\n}\nprint(f(1i))\n")
            env = dict(os.environ)
            env["PYTHONPATH"] = os.path.join(repo, "src")
            proc = subprocess.run(
                [sys.executable, os.path.join(repo, "nodus.py"), "run", script, "--time-limit", "30"],
                cwd=directory, env=env, capture_output=True, text=True, timeout=120,
            )
        self.assertEqual(proc.stdout.strip(), "2", proc.stderr)


if __name__ == "__main__":
    unittest.main()
