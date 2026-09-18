"""Restoring another VM's context does not adopt that VM's builtins (#856).

A context in ``_capture_module_ctx`` layout is "code and namespaces together"
-- and the capturing VM's ``builtins`` table. Every core builtin is a closure
over the VM that registered it, so restoring a **caller's** context wholesale
(``_try_enter_foreign_closure``, to run the caller's closure in this loop)
swapped this VM's builtins for the caller's. From that frame on, ``coroutine()``,
``spawn()`` and ``run_loop()`` acted on the caller's VM:

    B.fn -> A.fan_out(worker_from_B) -> worker -> A.fan_out(...) -> spawn

The inner spawn ran with B-VM builtins, so its coroutine was owned by B's VM,
pinned (via B's own ``_caller_vm``) to the *root* chunk, resumed straight into
a ``HALT`` at an address that meant nothing there, and left ``running`` and
never re-queued. No error. The inner ``run_loop()`` returned at once and the
result was ``{}``.

Every case in ``test_cross_module_closure.py`` keeps the closure and the module
function on the same side of one boundary, which is why they stayed green.
This file crosses it twice. ``examples/orchestration/judge_panel.nd`` is the
shape in the wild -- a fan-out whose worker fans out again.
"""

import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
SRC = REPO / "src"
NODUS_PY = REPO / "nodus.py"

sys.path.insert(0, str(SRC))

from nodus.builtins.nodus_builtins import BUILTIN_NAMES  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.vm.vm import VM  # noqa: E402


MODULE_A = """\
    // A: a function whose local is written by a coroutine it spawns.
    export fn collect(worker) {
        let bucket = {}
        spawn(coroutine(fn() { bucket["k"] = worker(1) }))
        run_loop()
        return bucket
    }
    export fn fan_out(items, worker) {
        let n = len(items)
        let bucket = {}
        let i = 0
        while (i < n) {
            let idx = i
            let item = items[i]
            spawn(coroutine(fn() { bucket[str(idx)] = worker(item) }))
            i = i + 1
        }
        run_loop()
        let results = []
        let k = 0
        while (k < n) {
            list_push(results, bucket[str(k)])
            k = k + 1
        }
        return results
    }
"""

MODULE_B = """\
    import "./a.nd" as a
    // B's closure, running inside A's coroutine, calls back into A -- which
    // spawns again. The inner spawn is the one that used to be dropped.
    export fn nested() {
        return a.collect(fn(_) { return a.collect(fn(x) { return x + 1 }) })
    }
    export fn nested_fan_out() {
        return a.fan_out([1, 2], fn(x) {
            return a.fan_out([10, 20], fn(y) { return x * y })
        })
    }
    // Control: one boundary only. Always worked; must keep working.
    export fn single() {
        return a.collect(fn(x) { return x + 1 })
    }
"""


# closes: #856
class NestedForeignCoroutineTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = pathlib.Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.write("a.nd", MODULE_A)
        self.write("b.nd", MODULE_B)

    def write(self, name: str, source: str) -> None:
        (self.tmpdir / name).write_text(textwrap.dedent(source), encoding="utf-8")

    def run_cli(self, source: str) -> str:
        self.write("main.nd", source)
        proc = subprocess.run(
            [sys.executable, str(NODUS_PY), "run", str(self.tmpdir / "main.nd"),
             "--time-limit", "30"],
            capture_output=True, text=True, timeout=120, cwd=str(self.tmpdir),
            env={"PYTHONPATH": str(SRC), "SYSTEMROOT": "C:\\Windows", "PATH": ""},
        )
        self.assertEqual(proc.returncode, 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
        return proc.stdout

    def run_embedded(self, source: str) -> str:
        self.write("main.nd", source)
        rt = NodusRuntime(timeout_ms=None, max_steps=None, allowed_paths=[str(self.tmpdir)])
        result = rt.run_file(str(self.tmpdir / "main.nd"))
        self.assertTrue(result["ok"], result.get("error") or result)
        return result["stdout"]

    def assertBoth(self, source: str, expected: str) -> None:
        for mode, run in (("cli", self.run_cli), ("embedded", self.run_embedded)):
            self.assertIn(expected, run(source), f"[{mode}]")

    def test_a_coroutine_spawned_two_boundaries_deep_runs(self):
        self.assertBoth('import "./b.nd" as b\nprint(b.nested())', '{"k": {"k": 2.0}}')

    def test_a_nested_cross_module_fan_out_returns_every_inner_result(self):
        self.assertBoth('import "./b.nd" as b\nprint(b.nested_fan_out())',
                        "[[10.0, 20.0], [20.0, 40.0]]")

    def test_one_boundary_still_works(self):
        self.assertBoth('import "./b.nd" as b\nprint(b.single())', '{"k": 2.0}')


class ForeignCtxIsAlwaysAdoptedTests(unittest.TestCase):
    """Assert on the source: a behaviour test covers only the doors it knows.

    Two things in `vm.py` produce a context captured on another VM --
    `_ClosureProxy.origin_ctx` and `_caller_module_ctx()` -- and two methods
    consume one. Each consumer must adopt before it installs or returns.
    """

    VM_SRC = (SRC / "nodus" / "vm" / "vm.py").read_text(encoding="utf-8")

    def _method(self, name: str) -> str:
        start = self.VM_SRC.index(f"    def {name}(")
        nxt = self.VM_SRC.find("\n    def ", start + 1)
        return self.VM_SRC[start:nxt]

    def test_try_enter_foreign_closure_restores_only_an_adopted_context(self):
        body = self._method("_try_enter_foreign_closure")
        restores = [ln.strip() for ln in body.splitlines() if "_restore_module_ctx(" in ln]
        installs = [ln for ln in restores if "(saved)" not in ln]  # the unwind restore is same-VM
        self.assertEqual(installs, ["self._restore_module_ctx(self._adopt_foreign_ctx(origin_ctx))"])

    def test_foreign_closure_origin_never_returns_a_raw_foreign_capture(self):
        body = self._method("_foreign_closure_origin")
        self.assertNotIn("return origin\n", body)
        self.assertNotIn("return self._caller_module_ctx()", body)
        self.assertIn("return self._adopt_foreign_ctx(origin)", body)
        self.assertIn("return self._adopt_foreign_ctx(self._caller_module_ctx())", body)


class AdoptForeignCtxTests(unittest.TestCase):
    """The helper itself, so the property is pinned independently of any program."""

    def test_core_builtins_are_this_vms_and_host_builtins_are_kept(self):
        mine, theirs = VM([], {}), VM([], {})
        theirs.builtins["host_only"] = object()  # a module's host builtin, not core
        foreign = theirs._capture_module_ctx()
        adopted = mine._adopt_foreign_ctx(foreign)
        # Program half is untouched ...
        self.assertEqual(adopted[:6], foreign[:6])
        self.assertEqual(adopted[7:], foreign[7:])
        # ... builtins half is this VM's, plus the foreign host entry.
        for name in BUILTIN_NAMES:
            self.assertIs(adopted[6][name], mine.builtins[name], name)
        self.assertIs(adopted[6]["host_only"], theirs.builtins["host_only"])

    def test_a_context_from_this_vm_is_returned_as_is(self):
        vm = VM([], {})
        ctx = vm._capture_module_ctx()
        self.assertIs(vm._adopt_foreign_ctx(ctx), ctx)
        self.assertIsNone(vm._adopt_foreign_ctx(None))


if __name__ == "__main__":
    unittest.main()
