"""A call into a module reuses an idle child VM (#987).

Every call to a module function, the stdlib included, ran on a new VM, and
building one costs about 1.4 ms: a loop calling `s.starts_with` 48,000 times
spent 50 s doing it. `ChildVMPool` (`runtime/module.py`) keeps idle child VMs on
the caller VM, per module, and resets one to its just-built state before each
call, so a reused VM is indistinguishable from a new one.

The main test runs each program twice, pooled and with the pool switched off
(`ChildVMPool.of` returning None, which is the old path), and requires the same
output, error, instruction count and call counts. The rest pin each thing the
reset and the release decide: what survives a call (module globals), what must
not (everything the VM owns, attributes added during the call, the run's
bounds), and when a VM is not reused (re-entry, an error, a coroutine it owns).
"""

import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from nodus.runtime import module as module_runtime  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.runtime.module import ChildVMPool  # noqa: E402
from nodus.tooling.runner import run_source  # noqa: E402

MODULE = (
    "let calls = 0i\n"
    "fn count() {\n    calls = calls + 1i\n    return calls\n}\n"
    "fn double(x) { return x * 2i }\n"
    "fn broken(r) { return r.missing }\n"
    "fn apply(f, x) { return f(x) }\n"
    "fn twice(f, x) { return f(f(x)) }\n"
    "fn spin(n) {\n    let i = 0i\n    while (i < n) { i = i + 1i }\n    return i\n}\n"
    "fn start(ch) {\n    spawn(fn() { send(ch, \"from the module\") })\n    return nil\n}\n"
)


def _off(*_args, **_kwargs):
    return None


class PooledModuleCalls(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = pathlib.Path(tmp.name)
        (self.dir / "m.nd").write_text(MODULE, encoding="utf-8")

    def run_program(self, body, *, pooled=True, **limits):
        main = self.dir / "main.nd"
        src = 'import "./m.nd" as m\n' + body
        main.write_text(src, encoding="utf-8")
        kwargs = {"max_steps": None, "timeout_ms": None} | limits
        with mock.patch.dict(os.environ, {"NODUS_COMPILE_FUNCTIONS": "0"}):
            if pooled:
                result, vm = run_source(src, filename=str(main), **kwargs)
            else:
                with mock.patch.object(ChildVMPool, "of", _off):
                    result, vm = run_source(src, filename=str(main), **kwargs)
        error = result.get("error") or {}
        return {
            "ok": result.get("ok"),
            "stdout": result.get("stdout"),
            "kind": error.get("type") or error.get("kind"),
            "message": error.get("message"),
            "stack": (result.get("errors") or [{}])[0].get("stack"),
            "instructions": vm.instructions_executed if vm is not None else None,
            "calls": getattr(vm, "function_calls", None),
            "returns": getattr(vm, "returns", None),
        }

    def assert_same(self, body, **limits):
        old = self.run_program(body, pooled=False, **limits)
        new = self.run_program(body, **limits)
        self.assertEqual(new, old)
        return new

    def count_constructions(self, body):
        real = ChildVMPool.adopt
        built = []

        def counting(pool, vm):
            built.append(vm)
            return real(pool, vm)
        with mock.patch.object(ChildVMPool, "adopt", counting):
            result = self.run_program(body)
        return result, len(built)

    # closes: #987
    def test_pooled_and_unpooled_agree(self):
        cases = {
            "module state outlives a call": "let i = 0i\nwhile (i < 5i) { m.count()\n i = i + 1i }\nprint(m.count())\n",
            "the stdlib in a loop": (
                'import "std:strings" as s\nlet n = 0i\nfor w in ["apple", "be", "ant"] {\n'
                '    if (s.starts_with(w, "a")) { n = n + 1i }\n}\nprint(n)\nprint(s.upper("x"))\n'),
            "a callback into the caller": "print(m.apply(fn(x) { return x + 1i }, 4i))\nprint(m.apply(fn(x) { return x * 3i }, 4i))\n",
            "re-entry: the callback calls the module again": (
                "print(m.twice(fn(x) { return m.double(x) }, 3i))\nprint(m.double(5i))\n"),
            "an error, then a good call": (
                "try { m.broken(record { a: 1i }) } catch (e) { print(\"caught\") }\nprint(m.double(2i))\n"),
            "an uncaught error in a module call": "print(m.double(1i))\nprint(m.broken(record { a: 1i }))\n",
            "a coroutine spawned by a module function": (
                "let ch = channel()\nm.start(ch)\nm.start(ch)\nrun_loop()\nprint(recv(ch))\n"),
        }
        for name, body in cases.items():
            with self.subTest(case=name):
                self.assert_same(body)

    def test_one_vm_serves_a_loop_of_calls(self):
        result, built = self.count_constructions(
            "let i = 0i\nwhile (i < 50i) { m.double(i)\n i = i + 1i }\nprint(m.count())\n")
        self.assertTrue(result["ok"], result)
        self.assertEqual(built, 1)

    def test_a_reentrant_call_gets_its_own_vm(self):
        # `twice` is running when the callback calls `double`, so `double`
        # cannot have `twice`'s VM; afterwards both are idle and reused.
        result, built = self.count_constructions(
            "print(m.twice(fn(x) { return m.double(x) }, 3i))\nprint(m.twice(fn(x) { return m.double(x) }, 1i))\n")
        self.assertEqual(result["stdout"], "12\n4\n")
        self.assertEqual(built, 2)

    def test_a_vm_whose_call_raised_is_not_reused(self):
        result, built = self.count_constructions(
            "try { m.broken(record { a: 1i }) } catch (e) { print(\"caught\") }\nprint(m.double(2i))\n")
        self.assertEqual(result["stdout"], "caught\n4\n")
        self.assertEqual(built, 2)

    def test_a_vm_that_owns_a_coroutine_is_not_reused(self):
        result, built = self.count_constructions(
            "let ch = channel()\nm.start(ch)\nm.start(ch)\nrun_loop()\nprint(recv(ch))\nprint(recv(ch))\n")
        self.assertTrue(result["ok"], result)
        self.assertEqual(built, 2)

    def test_the_step_budget_is_cumulative_across_reused_calls(self):
        # Each call fits in the budget; the total does not. With a reused VM
        # whose count carried over, or was never charged back, this would
        # either fail too early or not at all.
        body = "let i = 0i\nwhile (i < 200i) { m.spin(20i)\n i = i + 1i }\nprint(\"done\")\n"
        result = self.assert_same(body, max_steps=2000)
        self.assertFalse(result["ok"])
        self.assertEqual(result["kind"], "sandbox")
        unlimited = self.run_program(body)
        self.assertTrue(unlimited["ok"], unlimited)
        self.assertGreater(unlimited["instructions"], 2000)

    def test_the_deadline_holds_across_reused_calls(self):
        rt = NodusRuntime(max_steps=None, timeout_ms=100)
        result = rt.run_source(
            'import "std:strings" as s\nlet i = 0i\nwhile (true) { s.repeat("a", 50i)\n i = i + 1i }\n')
        self.assertFalse(result["ok"])
        self.assertIn("timed out", result["error"]["message"].lower())


class TheReset(unittest.TestCase):
    """`reset` returns a VM to its just-built state, without touching what it
    shares with the module."""

    def make(self):
        from nodus.runtime.module_loader import ModuleLoader
        from nodus.vm.vm import VM
        code, functions, locs = ModuleLoader(project_root=None).compile_only(
            "let calls = 0i\nfn f() { return 1i }\n", module_name="m.nd")
        module = module_runtime.NodusModule("m", "m.nd", code["instructions"], functions, locs)
        module.globals["calls"] = 0
        caller = VM([("HALT",)], {}, code_locs=[], source_path=None)
        pool = ChildVMPool.of(caller, module, {"allow_env": True})
        vm = VM(module.bytecode, module.functions, code_locs=module.code_locs,
                module_globals=module.globals, source_path=module.path, allow_env=True)
        pool.adopt(vm)
        return module, pool, vm

    def test_what_a_call_leaves_is_undone(self):
        module, pool, vm = self.make()
        builtins_before = dict(vm.builtins)
        vm.stack.append("left over")
        vm.frames.append("a frame")
        vm.test_state["k"] = 1
        vm.builtins["extra"] = None
        vm.instructions_executed = 999
        vm.max_steps = 5
        vm._caller_vm = object()
        vm._added_during_the_call = True
        pool.reset(vm)
        self.assertEqual(vm.stack, [])
        self.assertEqual(vm.frames, [])
        self.assertEqual(vm.test_state, {})
        self.assertEqual(vm.builtins, builtins_before)
        self.assertEqual(vm.instructions_executed, 0)
        self.assertIsNone(vm.max_steps)
        # Set on the instance during a call; `VM` has a class-level None.
        self.assertNotIn("_caller_vm", vars(vm))
        self.assertIsNone(vm._caller_vm)
        self.assertFalse(hasattr(vm, "_added_during_the_call"))

    def test_an_idle_vm_is_reset_again_when_taken(self):
        # `release` resets too, to drop what the call left referenced; the reset
        # that guarantees a clean VM is the one in `acquire`, because a value
        # escaping a call can still run on its VM while that VM sits idle.
        module, pool, vm = self.make()
        pool.release(vm, reusable=True)
        vm.stack.append("touched while idle")
        vm.instructions_executed = 50
        self.assertIs(pool.acquire(), vm)
        self.assertEqual(vm.stack, [])
        self.assertEqual(vm.instructions_executed, 0)

    def test_an_equal_object_is_not_the_same_object(self):
        # The untouched check is by identity: a call that rebinds an attribute
        # to an equal, new container must still get the original back, or
        # whatever holds the new one shares it with the next call.
        module, pool, vm = self.make()
        original = vm.test_state
        vm.test_state = {}
        pool.reset(vm)
        self.assertIs(vm.test_state, original)

    def test_release_drops_the_caller(self):
        # The pools are keyed weakly on the caller VM; an idle VM still
        # referring to its caller would keep both alive for good.
        import gc
        import weakref
        rt = NodusRuntime(max_steps=None, timeout_ms=None)
        result = rt.run_source(
            'import "std:strings" as s\nfn f(x) { return s.upper(x) }\nprint(f("a"))\nprint(f("b"))\n')
        self.assertTrue(result["ok"], result)
        caller = weakref.ref(rt.active_vm())
        pools = module_runtime._POOLS.get(caller())
        self.assertTrue(pools and any(p.idle for p in pools.values()), "nothing was pooled")
        del rt, pools
        gc.collect()
        self.assertIsNone(caller(), "the caller VM is still alive")

    def test_module_state_is_left_alone(self):
        module, pool, vm = self.make()
        module.globals["calls"] = 7
        pool.reset(vm)
        self.assertEqual(module.globals["calls"], 7)
        self.assertIs(vm.functions, module.functions)

    def test_different_construction_means_a_different_pool(self):
        module, _, _ = self.make()
        from nodus.vm.vm import VM
        caller = VM([("HALT",)], {}, code_locs=[], source_path=None)
        a = ChildVMPool.of(caller, module, {"allow_subprocess": True})
        b = ChildVMPool.of(caller, module, {"allow_subprocess": True})
        c = ChildVMPool.of(caller, module, {"allow_subprocess": False})
        self.assertIs(a, b)
        self.assertIsNot(a, c)

    def test_no_caller_no_pool(self):
        module, _, _ = self.make()
        self.assertIsNone(ChildVMPool.of(None, module, {}))


class EveryOwnerSiteMarksTheVM(unittest.TestCase):
    """A VM that owns a coroutine is never reused. Ownership is recorded where
    it is assigned, so every `owner_vm = ` site must mark the VM."""

    def test_each_site(self):
        sites = []
        for path in sorted((REPO / "src").rglob("*.py")):
            lines = path.read_text(encoding="utf-8").splitlines()
            for i, line in enumerate(lines):
                if ".owner_vm = " in line and "getattr" not in line:
                    window = "\n".join(lines[i:i + 5])
                    sites.append(path.relative_to(REPO).as_posix())
                    self.assertIn("mark_coroutine_owner(", window,
                                  f"{path}:{i + 1} assigns owner_vm without marking the VM")
        self.assertEqual(len(sites), 2, sites)


class NoAttributeOnAnyVM(unittest.TestCase):
    """The pools and the coroutine owners live outside the VM. A `VM` must stay
    under PyPy's 80-attribute map limit (#702), and the first version of this
    change put one attribute on every VM and another on any VM that spawned a
    coroutine, which `tests/test_vm_attribute_budget.py` caught on CI."""

    def test_module_calls_and_spawns_add_none(self):
        # The same program, pooled and with the pool switched off: the VM that
        # ran it must hold exactly the same attributes either way.
        src = ('import "std:strings" as s\nprint(s.upper("a"))\nprint(s.upper("b"))\n'
               "let ch = channel()\nspawn(fn() { send(ch, 1i) })\nrun_loop()\nprint(recv(ch))\n")
        names = []
        for pooled in (False, True):
            rt = NodusRuntime(max_steps=None, timeout_ms=None)
            if pooled:
                result = rt.run_source(src)
            else:
                # Patched where it is called: both sites import it by name.
                with mock.patch.object(ChildVMPool, "of", _off), \
                        mock.patch("nodus.builtins.coroutine.mark_coroutine_owner", lambda vm: None), \
                        mock.patch("nodus.runtime.continuation.mark_coroutine_owner", lambda vm: None):
                    result = rt.run_source(src)
            self.assertTrue(result["ok"], result)
            names.append(sorted(vars(rt.active_vm())))
        self.assertEqual(names[1], names[0])


if __name__ == "__main__":
    unittest.main()
