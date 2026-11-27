"""Closed-issue test for #1007: compile-to-Python works without the optimizer.

The optimizer fuses a function's `FRAME_SIZE n; STORE_ARG...` prologue into
`ENTER` (#969), and compile-to-Python translated `ENTER` but not `STORE_ARG`.
So under `--no-opt`, or `run_source(..., optimize=False)`, every function with
a parameter stayed interpreted, silently: the self-hosted frontend compiled 0
of its functions instead of 42. `STORE_ARG` is now a no-op in the prologue,
where the generated function binds its parameters itself, and refused anywhere
else.
"""
import glob
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus.builtins.nodus_builtins import BUILTIN_NAMES  # noqa: E402
from nodus.compiler.compiler import Compiler  # noqa: E402
from nodus.compiler.optimizer import optimize_bytecode  # noqa: E402
from nodus.frontend.lexer import tokenize  # noqa: E402
from nodus.frontend.parser import Parser  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.runtime.module_loader import collect_module_info  # noqa: E402
from nodus.vm import pycompile  # noqa: E402

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BUILTINS = {name: None for name in BUILTIN_NAMES}

_PROGRAM = (
    "fn noargs() {\n    let t = 0i\n    for x in range(0i, 100i) { t = t + x }\n    return t\n}\n"
    "fn witharg(n) {\n    let t = 0i\n    for x in range(0i, n) { t = t + x }\n    return t\n}\n"
    "fn pair(a, b) {\n    let t = 0i\n    for x in range(0i, a) { t = t + x * b }\n    return t\n}\n"
    "print(noargs())\nprint(witharg(100i))\nprint(pair(10i, 3i))\n"
)


def _run(optimize, compiled):
    rt = NodusRuntime(timeout_ms=None, max_steps=None, compile_functions=compiled)
    result = rt.run_source(_PROGRAM, filename="p.nd", optimize=optimize)
    assert result.get("ok"), result.get("error")
    state = rt.active_vm()._pycompile
    return (result["stdout"], rt.get_execution_stats()["instructions_executed"],
            state.compiled_count if state is not None else 0)


def _bytecode(source, optimize):
    ast = Parser(tokenize(source)).parse()
    info = collect_module_info(ast, "m", "")
    info.qualified = {name: name for name in info.defs}
    compiler = Compiler(module_infos={"m": info}, module_defs_index={},
                        builtin_names=set(BUILTIN_NAMES))
    code, functions, locs = compiler.compile_program(ast)
    if optimize:
        code, functions, locs = optimize_bytecode(code, functions, locs,
                                                  removable=compiler.uncaptured_resets)
    return code, functions


# closes: #1007
class WithoutTheOptimizerFunctionsWithParametersCompile(unittest.TestCase):
    def test_the_same_functions_compile_either_way(self):
        out_on, _, n_on = _run(True, True)
        out_off, _, n_off = _run(False, True)
        self.assertEqual(n_on, 3)
        self.assertEqual(n_off, n_on, "the optimizer decided what compiles")
        self.assertEqual(out_off, out_on)

    def test_compiled_matches_interpreted_without_the_optimizer(self):
        # Same output and the same instruction count, as with the optimizer on:
        # the no-op STORE_ARGs are still counted, as the interpreter counts them.
        self.assertEqual(_run(False, True)[:2], _run(False, False)[:2])

    def test_the_cli_runs_no_opt_compile(self):
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "p.nd"), "w", encoding="utf-8") as handle:
                handle.write(_PROGRAM)
            env = dict(os.environ, PYTHONPATH=os.path.join(_REPO, "src"))
            proc = subprocess.run([sys.executable, "-m", "nodus", "run", "--no-opt", "--compile", "p.nd"],
                                  cwd=directory, capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.split(), ["4950", "4950", "135"])


class StoreArgIsANoOpOnlyInThePrologue(unittest.TestCase):
    def test_a_store_arg_in_the_body_keeps_the_function_interpreted(self):
        code, functions = _bytecode("fn f(a) {\n    let t = a\n    return t\n}\n", optimize=False)
        start = functions["f"].addr
        self.assertEqual([code[start][0], code[start + 1][0]], ["FRAME_SIZE", "STORE_ARG"])
        self.assertIsNone(pycompile.eligible_functions(code, functions, _BUILTINS)["f"])
        # The body's first instruction, replaced by one with the same (zero)
        # stack effect in the analysis: only the position differs.
        code = list(code)
        code[start + 2] = ("STORE_ARG", "a")
        self.assertEqual(pycompile.eligible_functions(code, functions, _BUILTINS)["f"],
                         "STORE_ARG outside the prologue")


class NoVerdictDependsOnTheOptimizer(unittest.TestCase):
    """The guard the issue asked for. An opcode only the optimizer emits, which
    the translator handles while not handling what it replaces, would open
    this gap again; it shows here as a function eligible one way only."""

    def test_the_stdlib_selfhost_and_eval_programs(self):
        paths = sorted(glob.glob(os.path.join(_REPO, "src", "nodus", "stdlib", "*.nd"))
                       + glob.glob(os.path.join(_REPO, "examples", "selfhost", "*.nd"))
                       + glob.glob(os.path.join(_REPO, "tests", "eval", "*.nd")))
        checked = 0
        for path in paths:
            with open(path, encoding="utf-8") as handle:
                source = handle.read()
            try:
                on = pycompile.eligible_functions(*_bytecode(source, True), _BUILTINS)
                off = pycompile.eligible_functions(*_bytecode(source, False), _BUILTINS)
            except Exception:  # noqa: BLE001 - a file needing its imports to compile
                continue
            for name, why in on.items():
                checked += 1
                with self.subTest(file=os.path.basename(path), function=name):
                    self.assertEqual(why is None, off.get(name, "missing") is None,
                                     f"optimized: {why!r}; unoptimized: {off.get(name)!r}")
        self.assertGreater(checked, 100, "too few functions checked to mean anything")


if __name__ == "__main__":
    unittest.main()
