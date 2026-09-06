"""A closure the root program owns can be resolved from inside a module (#783).

The fourth direction in the #691 / #696 family. A `Closure` is an address plus
upvalues, and the address means nothing without the chunk it was compiled
against, so the VM has to be able to answer *which chunk owns this closure* from
wherever it happens to be running.

It could answer for a `_ClosureProxy`, for a live cross-module frame, for a
detached caller VM, and for any **module** it can reach. It could not answer for
**its own program**, which is the one chunk that is not a module. A module that
spawns a closure capturing a caller's closure runs the wrapper after its own
frame has popped, so all four existing sources are empty:

| source | why it is empty here |
|---|---|
| `_ClosureProxy.origin_ctx` | the same-VM #105 path wraps nothing |
| a frame's `cross_module_ctx` | that frame has popped — #696's case |
| `_caller_vm` | `None` on the same-VM path |
| `_module_owning` | searches modules; this closure is the root program's |

The call then executed at the right address against the wrong chunk, which
surfaces as `Stack underflow` — and only from inside a coroutine, because from
`main` the detached-VM path supplies `_caller_vm`.

**Two neighbouring gaps are deliberately not fixed here and are pinned below**,
so that a later reader does not mistake this file for covering them: #785 (a
sibling module's closure) and #786 (a root-level `let`). Both were found by
probing this fix's neighbourhood, and #785 was verified to fail identically with
this fix stashed.
"""

import ast
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

_INNER = """
fn wrap_and_spawn(body) {
    return spawn(fn() { return body() })
}

fn wrap_and_return(body) {
    return fn() { return body() }
}

fn call_now(body) {
    return body()
}

fn spawn_from_list(items) {
    return spawn(fn() { return items[0]() })
}

fn spawn_from_map(m) {
    return spawn(fn() { return m["f"]() })
}

fn double_nested(body) {
    return spawn(fn() { return fn() { return body() }() })
}
"""

_OUTER = """
import "./inner.nd" as inner

fn forward(body) {
    return inner.wrap_and_spawn(body)
}

fn own_closure() {
    return fn() { print("outer-own") }
}
"""


def _run(program: str, timeout: float = 90.0) -> tuple[str, str]:
    """Run `program` against the two fixture modules; return (stdout, stderr).

    A subprocess with its own directory: the modules must exist on disk, and a
    fresh CWD keeps the bytecode cache — which resolves against the *script's*
    project root, not the repo's — from serving one case's compilation to
    another.
    """
    import shutil
    import tempfile

    workdir = Path(tempfile.mkdtemp(prefix="nodus-783-"))
    try:
        (workdir / "inner.nd").write_text(_INNER, encoding="utf-8")
        (workdir / "outer.nd").write_text(_OUTER, encoding="utf-8")
        probe = textwrap.dedent(f"""
            import sys
            sys.path.insert(0, {str(_REPO_ROOT / "src")!r})
            from nodus.runtime.embedding import NodusRuntime
            res = NodusRuntime(timeout_ms=None, max_steps=None).run_source(
                {program!r}, filename="probe.nd"
            )
            sys.stdout.write("OUT<<" + (res.get("stdout") or "").strip() + ">>")
            sys.stdout.write("ERR<<" + (res.get("stderr") or "").strip() + ">>")
        """)
        result = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True, text=True, timeout=timeout, cwd=str(workdir),
        )
        if result.returncode != 0:
            raise AssertionError(result.stderr[-1500:])
        out = result.stdout.split("OUT<<", 1)[1].split(">>ERR<<")[0]
        err = result.stdout.split(">>ERR<<", 1)[1].rsplit(">>", 1)[0]
        return out, err
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _in_coroutine(body: str) -> str:
    return (
        'import "./inner.nd" as m\n'
        'import "./outer.nd" as o\n'
        "fn main() {\n"
        f"    spawn(coroutine(fn(){{ {body} return 1i }}))\n"
        "    run_loop()\n"
        "}\n"
    )


class ARootOwnedClosureResolvesFromInsideAModuleTests(unittest.TestCase):
    # closes: #783
    def test_a_module_can_spawn_a_wrapper_around_a_callers_closure(self):
        """The reported defect. `Stack underflow` before this."""
        out, err = _run(_in_coroutine('m.wrap_and_spawn(fn(){ print("A") });'))
        self.assertEqual("", err)
        self.assertEqual("A", out)

    # closes: #783
    def test_the_same_call_from_main_still_works(self):
        """The control, and it must run. From `main` the detached-VM path
        supplies `_caller_vm`, so this half was never broken — a fix that only
        made the coroutine case pass by breaking this one would look green
        against the test above alone."""
        out, err = _run(
            'import "./inner.nd" as m\n'
            'fn main() { m.wrap_and_spawn(fn(){ print("B") }); run_loop() }\n'
        )
        self.assertEqual("", err)
        self.assertEqual("B", out)

    # closes: #783
    def test_a_wrapper_the_module_returns_for_the_caller_to_spawn(self):
        out, err = _run(_in_coroutine('spawn(m.wrap_and_return(fn(){ print("C") }));'))
        self.assertEqual("", err)
        self.assertEqual("C", out)

    # closes: #783
    def test_the_callers_closure_arrives_nested_in_a_container(self):
        """#339 found the *entry* side had missed containers; the same shapes
        must work on the way back out."""
        for label, call in (
            ("list", 'm.spawn_from_list([fn(){ print("D") }]);'),
            ("map", 'm.spawn_from_map({"f": fn(){ print("D") }});'),
        ):
            with self.subTest(container=label):
                out, err = _run(_in_coroutine(call))
                self.assertEqual("", err)
                self.assertEqual("D", out)

    # closes: #783
    def test_two_closure_layers_inside_the_module(self):
        out, err = _run(_in_coroutine('m.double_nested(fn(){ print("E") });'))
        self.assertEqual("", err)
        self.assertEqual("E", out)

    # closes: #783
    def test_the_closure_crosses_two_module_boundaries(self):
        """`main -> outer.forward -> inner.wrap_and_spawn`. Ownership must name
        the root however many boundaries the value crossed."""
        out, err = _run(_in_coroutine('o.forward(fn(){ print("F") });'))
        self.assertEqual("", err)
        self.assertEqual("F", out)

    # closes: #783
    def test_a_wrapped_caller_closure_can_still_suspend(self):
        """Resolving the chunk must not cost the closure its ability to yield —
        the whole point of the same-VM path (#105)."""
        out, err = _run(_in_coroutine('m.wrap_and_spawn(fn(){ sleep(1i); print("G") });'))
        self.assertEqual("", err)
        self.assertEqual("G", out)

    # closes: #783
    def test_a_root_level_function_is_callable_from_the_wrapped_closure(self):
        """Resolution has to supply the chunk's `functions` table, not only its
        code — a closure that resolves but cannot call anything is half a fix."""
        out, err = _run(
            'import "./inner.nd" as m\n'
            'fn helper() { return "helped" }\n'
            "fn main() {\n"
            '    spawn(coroutine(fn(){ m.wrap_and_spawn(fn(){ print(helper()) }); return 1i }))\n'
            "    run_loop()\n"
            "}\n"
        )
        self.assertEqual("", err)
        self.assertEqual("helped", out)


class KnownNeighbouringGapsTests(unittest.TestCase):
    """Pinned as **known broken**, with their issue numbers, so this file cannot
    be read as covering them. Each asserts the specific failure rather than
    merely "it errors", so the day one starts working the test says which."""

    # closes: #783
    def test_a_sibling_modules_closure_is_still_unresolvable(self):
        """#785. `outer` owns the closure, `inner` is asked to call it, and
        neither imports the other — so `_module_owning`'s reachability walk
        cannot find `outer` from inside `inner`.

        Pre-existing: verified to fail identically with the #783 fix stashed,
        and it fails with the calling frames **still alive**, which is what
        distinguishes it from #783 and #696.
        """
        _out, err = _run(_in_coroutine("m.call_now(o.own_closure());"))
        self.assertIn(
            "Stack underflow", err,
            "#785 appears to be fixed — if so, delete this test and close it "
            "rather than leaving a passing assertion that a bug exists",
        )

    # closes: #783
    def test_a_root_level_let_is_not_visible_once_the_entry_frame_has_popped(self):
        """#786, and the asymmetry worth not shipping silently: the wrapped
        closure can call a root-level `fn` (asserted above) but cannot read a
        root-level `let`. The binding lives in the entry frame rather than in a
        namespace that outlives it, so #783's context tuple carries the correct
        — and empty — namespace."""
        _out, err = _run(
            'import "./inner.nd" as m\n'
            'let TOKEN = "main-let"\n'
            "fn main() {\n"
            '    spawn(coroutine(fn(){ m.wrap_and_spawn(fn(){ print(TOKEN) }); return 1i }))\n'
            "    run_loop()\n"
            "}\n"
        )
        self.assertIn(
            "Undefined variable: TOKEN", err,
            "#786 appears to be fixed — if so, delete this test and close it",
        )


class TheBaseProgramIsRecordedWhereverAProgramIsLoadedTests(unittest.TestCase):
    """`_base_program` is the new answer to "what is this VM's own program", and
    it is only as good as the set of places that keep it current."""

    # closes: #783
    def test_every_site_that_loads_a_program_records_the_base(self):
        """Assertion on the source. A site that assigns `self.functions` outside
        a context restore has changed which program the VM is running, and a
        base left pointing at the previous one silently stops resolving.

        `_restore_module_ctx` is excluded because that *is* the context swap —
        recording there would make the base track the module being entered,
        which is the opposite of what it means.
        """
        source = (_REPO_ROOT / "src/nodus/vm/vm.py").read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
        offenders = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name in ("_restore_module_ctx", "_record_base_program"):
                continue
            assigns_functions = any(
                isinstance(inner, ast.Assign)
                and any(
                    isinstance(t, ast.Attribute)
                    and t.attr == "functions"
                    and isinstance(t.value, ast.Name)
                    and t.value.id == "self"
                    for t in inner.targets
                )
                for inner in ast.walk(node)
            )
            if not assigns_functions:
                continue
            records = any(
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and inner.func.attr == "_record_base_program"
                for inner in ast.walk(node)
            )
            if not records:
                offenders.append(node.name)
        self.assertEqual(
            [],
            offenders,
            "these methods load a program into the VM without recording it as "
            "the base, so a closure the program owns will not resolve from "
            "inside a module (#783): " + ", ".join(offenders),
        )

    # closes: #783
    def test_no_function_is_registered_in_two_chunks(self):
        """Why the fallback's position in the chain is safe.

        #783 warned that the root fallback must come *after* `_module_owning`,
        or a closure a module owns would resolve to the root. That warning was
        wrong, and the honest way to record it is to pin the invariant that
        makes it wrong rather than the ordering it recommended: a `FunctionInfo`
        is registered in exactly one chunk's `functions` table, so the two
        ownership tests are mutually exclusive and cannot disagree. Moving the
        fallback above `_module_owning` leaves the whole suite green — checked.

        Asserted over a real compiled program rather than a hand-built state,
        because the claim is about what the compiler produces.
        """
        import shutil
        import tempfile

        from nodus.runtime.embedding import NodusRuntime
        from nodus.runtime.module_loader import NodusModule

        workdir = Path(tempfile.mkdtemp(prefix="nodus-783-ids-"))
        try:
            (workdir / "inner.nd").write_text(_INNER, encoding="utf-8")
            (workdir / "outer.nd").write_text(_OUTER, encoding="utf-8")
            runtime = NodusRuntime(timeout_ms=None, max_steps=None)
            result = runtime.run_file(str(workdir / "outer.nd"))
            self.assertTrue(result.get("ok"), result.get("error"))
            vm = runtime.active_vm()

            tables = {"<base>": vm._base_program[1]}
            for namespace in (vm.module_globals, vm.host_globals):
                for name, value in namespace.items():
                    if isinstance(value, NodusModule):
                        tables[name] = value.functions
            self.assertGreaterEqual(
                len(tables), 2,
                "the fixture reached no module, so this proves nothing about "
                "two chunks",
            )

            owners: dict[int, str] = {}
            shared: list[str] = []
            for chunk, functions in tables.items():
                for fn_name, fn_info in functions.items():
                    previous = owners.get(id(fn_info))
                    if previous is not None and previous != chunk:
                        shared.append(f"{fn_name} in {previous} and {chunk}")
                    owners[id(fn_info)] = chunk
            self.assertEqual(
                [], shared,
                "a FunctionInfo is registered in two chunks, so base ownership "
                "and module ownership can disagree and the order of the two "
                "checks in `_foreign_closure_origin` becomes load-bearing: "
                + ", ".join(shared),
            )
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    # closes: #783
    def test_a_stale_base_cannot_mis_resolve(self):
        """The safety property the design leans on.

        `ModuleLoader._execute_module` drives `reset_program` once per module on
        one shared VM, so between those calls the base names a module rather
        than the root. That is tolerated because every consumer goes through an
        **identity** check on the functions table: a base naming the wrong
        program owns nothing the caller asks about, and resolution falls through
        to `None` — the behaviour from before this existed.
        """
        from nodus.compiler.compiler import FunctionInfo
        from nodus.vm.vm import VM

        vm = VM([], {}, code_locs=[], source_path=None)
        mine = FunctionInfo(
            name="f", params=[], addr=0, upvalues=[], display_name="f"
        )
        impostor = FunctionInfo(
            name="f", params=[], addr=0, upvalues=[], display_name="f"
        )
        vm._base_program = ([], {"f": mine}, {}, {}, [], None, vm.bytecode_version)
        self.assertTrue(vm._base_program_owns(mine))
        self.assertFalse(
            vm._base_program_owns(impostor),
            "ownership matched on name rather than identity — two chunks "
            "routinely both hold an `__anon_1`, so a name match would resolve a "
            "closure to a program that merely has a function of the same name",
        )


if __name__ == "__main__":
    unittest.main()
