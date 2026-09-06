"""The four facts `docs/design/v5/08-durable-coroutines.md` rests on (#180).

A design document is a claim about the tree, and this tree's own history says
those rot silently: #715 found a governing document that had recorded a reversed
policy as current, and the sections that rotted were the ones holding a *list*
something else also held. This file is that list, held once, where CI reads it.

Nothing here implements durable coroutines. Each test pins a premise, and each
premise, if it stopped being true, would falsify a specific section of the design
rather than merely inconvenience it:

| premise | §  | falsifies |
|---|---|---|
| the continuation capture is exactly seven pieces of state | 3.1 | the inventory a serialiser would be written against |
| the operand stack is empty at a statement boundary | 3.2 | that a checkpoint can capture at all |
| identical source compiles identically across processes | 3.3 | that a saved `ip` means anything after a restart |
| a coroutine's entry point is often anonymous, and locals may be non-durable | 3.4 | that identity and durability need declaring, not inferring |

The last one is the odd member: it pins facts that are *obstacles*. That is
deliberate. If a later change made every coroutine entry nameable, §5's
recommendation would be unnecessary work, and nobody would find out from a test
that only checked the happy path.
"""

import ast
import json
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402

_DESIGN = _REPO_ROOT / "docs/design/v5/08-durable-coroutines.md"


# --------------------------------------------------------------------------
# A probe that reports what is live inside a coroutine at a statement boundary.
# --------------------------------------------------------------------------

_PROBE_SOURCE = """
fn named_worker(n) {
    let acc = n * 2i
    probe({"case": "named-top-level"})
    return acc
}

fn make_closure(base) {
    return fn() {
        let inner = base + 1i
        probe({"case": "closure-over-local"})
        return inner
    }
}

fn holds_a_channel() {
    let ch = channel()
    let n = 1i
    probe({"case": "local-holds-a-channel"})
    return n
}

fn main() {
    spawn(coroutine(fn() { return named_worker(5i) }))
    run_loop()
    spawn(coroutine(make_closure(10i)))
    run_loop()
    spawn(coroutine(holds_a_channel))
    run_loop()
}
"""


_CHECKPOINT_SOURCE = """
workflow w {
    step one {
        let a = 1i
        let b = [1i, 2i]
        checkpoint "half-way"
        return a
    }
}

fn main() {
    let r = run_workflow(w)
    print("steps=\(len(r["steps"]))")
}
"""


def _json_safe(value) -> bool:
    try:
        json.dumps(value)
    except Exception:
        return False
    return True


def _observe() -> dict:
    """Run the probe program and report what each coroutine held mid-flight.

    Deliberately reads the live objects rather than any accessor: the design is
    a claim about what the runtime *has*, and an accessor could paper over a
    change in what it has.
    """
    report: dict = {}

    def probe(payload):
        vm = runtime.active_vm()
        coroutine = vm.current_coroutine
        function = getattr(coroutine.closure, "function", None)
        frames = []
        for frame in coroutine.frames:
            merged = dict(getattr(frame, "locals", {}) or {})
            array = getattr(frame, "locals_array", None)
            slots = getattr(frame, "locals_name_to_slot", None)
            if array is not None and slots:
                for name, index in slots.items():
                    if 0 <= index < len(array):
                        merged[name] = array[index]
            frames.append({
                "fn": getattr(frame, "fn_name", None),
                "return_ip": getattr(frame, "return_ip", None),
                "locals": {k: _json_safe(v) for k, v in merged.items()},
            })
        report[payload["case"]] = {
            "display_name": getattr(function, "display_name", None),
            "addr": getattr(function, "addr", None),
            "upvalues": len(getattr(coroutine.closure, "upvalues", []) or []),
            "operand_stack_depth": len(coroutine.stack),
            "frames": frames,
        }
        return {"ok": True}

    runtime = NodusRuntime(timeout_ms=None, max_steps=None)
    runtime.register_function("probe", probe)
    result = runtime.run_source(_PROBE_SOURCE)
    assert result.get("ok"), result.get("error")
    assert set(report) == {
        "named-top-level", "closure-over-local", "local-holds-a-channel"
    }, f"the probe program did not reach every case: {sorted(report)}"
    return report


class TheContinuationCaptureIsAnInventoryTests(unittest.TestCase):
    """§3.1. `save_current_coroutine_state` is the existing capture, and the
    design is written against its contents. A new piece of per-coroutine
    continuation state added there is a hole in a serialiser written from that
    table — and it would be added for good reasons, by someone with no cause to
    open a design document about a feature that does not exist yet."""

    _EXPECTED = {
        "ip",
        "stack",
        "frames",
        "handler_stack",
        "deferred_return",
        "deferred_return_depth",
        "deferred_error",
        "deferred_error_depth",
        "module_ctx",
    }

    def test_the_capture_writes_exactly_the_state_the_design_enumerates(self):
        tree = ast.parse(
            (_REPO_ROOT / "src/nodus/vm/vm.py").read_text(encoding="utf-8-sig")
        )
        captured = set()
        found = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name != "save_current_coroutine_state":
                continue
            found = True
            for inner in ast.walk(node):
                if not isinstance(inner, ast.Assign):
                    continue
                for target in inner.targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "coroutine"
                    ):
                        captured.add(target.attr)
        self.assertTrue(
            found,
            "`save_current_coroutine_state` is gone. It is the design's premise "
            "that a continuation is already captured on every suspend — if the "
            "capture moved, docs/design/v5/08-durable-coroutines.md §3.1 is "
            "describing a method that no longer exists.",
        )
        self.assertEqual(
            self._EXPECTED,
            captured,
            "the set of per-coroutine continuation state has changed. Update "
            "§3.1's table in docs/design/v5/08-durable-coroutines.md and say "
            "whether the new member is durable, then update this test. A "
            "serialiser written against the old table would silently drop it.",
        )


class TheOperandStackIsEmptyAtAStatementBoundaryTests(unittest.TestCase):
    """§3.2. The hardest part of capturing a continuation is arbitrary
    intermediate values on the operand stack. At a statement boundary there are
    none, which is why a `checkpoint` statement is a capturable point and an
    expression-position `checkpoint(...)` would not be."""

    def test_no_coroutine_holds_operand_stack_at_a_statement_boundary(self):
        for case, observed in sorted(_observe().items()):
            with self.subTest(case=case):
                self.assertEqual(
                    0,
                    observed["operand_stack_depth"],
                    "a coroutine held operand-stack values at a statement "
                    "boundary, so a checkpoint there would have to serialise "
                    "arbitrary intermediate values — which is the case §3.2 "
                    "says does not arise",
                )

    def test_the_stack_is_empty_at_a_real_checkpoint(self):
        """Measured at the construct itself, not at a stand-in.

        The version of this test that shipped first asserted that the compiler
        source *contained* `isinstance(stmt, CheckpointStmt)`, and a neuter that
        rewrote the line to `if False and isinstance(...)` left it green — the
        assertion matched a substring of the very code it was checking. So this
        one drives a real `checkpoint` and reads the stack depth at the moment
        the builtin is entered.
        """
        from nodus.vm.vm import VM

        observed: list[tuple[str, int | None]] = []
        aliased: list[bool] = []
        original = VM.builtin_workflow_checkpoint

        def _spy(vm_self, label):
            coroutine = vm_self.current_coroutine
            # `load_coroutine_context` aliases the two (`self.stack =
            # coroutine.stack`), so a serialiser reading either gets the live
            # operand stack. Pinned here because that identity is the reason
            # the coroutine's recorded stack is the running one and not a
            # snapshot taken at the last suspend.
            aliased.append(
                coroutine is not None and vm_self.stack is coroutine.stack
            )
            observed.append(
                (label, None if coroutine is None else len(vm_self.stack))
            )
            return original(vm_self, label)

        VM.builtin_workflow_checkpoint = _spy
        try:
            runtime = NodusRuntime(timeout_ms=None, max_steps=None)
            result = runtime.run_source(_CHECKPOINT_SOURCE)
        finally:
            VM.builtin_workflow_checkpoint = original

        self.assertTrue(result.get("ok"), result.get("error"))
        self.assertEqual(
            [True],
            aliased,
            "the VM's operand stack is no longer the coroutine's own list, so "
            "what a serialiser would read at a checkpoint is not what the "
            "coroutine is running on",
        )
        self.assertEqual(
            [("half-way", 0)],
            observed,
            "a real `checkpoint` was reached with a non-empty operand stack (or "
            "was not reached at all). §3.2 of the design says a checkpoint sits "
            "at a statement boundary and therefore captures no intermediate "
            "values; that is what makes the position capturable.",
        )

    def test_checkpoint_is_refused_in_expression_position(self):
        """The premise above is a property of *where the construct sits*, so it
        is withdrawn the moment `checkpoint` becomes an expression."""
        runtime = NodusRuntime(timeout_ms=None, max_steps=None)
        result = runtime.run_source(
            _CHECKPOINT_SOURCE.replace(
                'checkpoint "half-way"', 'let z = checkpoint "half-way"'
            )
        )
        self.assertIn(
            "Undefined variable: checkpoint",
            (result.get("stderr") or "") + str(result.get("error") or ""),
            "`checkpoint` is now accepted in expression position, so it no "
            "longer necessarily sits at a statement boundary and the "
            "empty-stack premise in §3.2 does not follow",
        )


class CompilationIsDeterministicAcrossProcessesTests(unittest.TestCase):
    """§3.3. A saved `ip` is an index into a compiled chunk, so it survives a
    restart only if identical source compiles identically. Two fresh
    interpreters, cache cleared, byte-compared."""

    _PROGRAM = textwrap.dedent("""
        fn a(n) { let x = n + 1i; return x }
        fn b(n) { return a(n) * 2i }
        fn main() {
            let c = coroutine(fn() { return b(3i) })
            spawn(c)
            run_loop()
        }
    """)

    def _addresses(self, tmp: Path) -> str:
        probe = textwrap.dedent(f"""
            import json, sys
            sys.path.insert(0, {str(_REPO_ROOT / "src")!r})
            from nodus.runtime.embedding import NodusRuntime
            rt = NodusRuntime(timeout_ms=None, max_steps=None)
            res = rt.run_source({self._PROGRAM!r})
            assert res.get("ok"), res.get("error")
            vm = rt.active_vm()
            out = {{}}
            for name, value in sorted(vm.functions.items()):
                addr = getattr(value, "addr", None)
                if addr is not None:
                    out[name] = addr
            sys.stdout.write("ADDRS " + json.dumps(out, sort_keys=True))
        """)
        result = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True, text=True, timeout=120, cwd=str(tmp),
        )
        if result.returncode != 0:
            raise AssertionError(result.stderr[-1200:])
        marker = "ADDRS "
        self.assertIn(marker, result.stdout, result.stdout)
        return result.stdout.split(marker, 1)[1].strip()

    def test_identical_source_compiles_to_identical_addresses(self):
        import shutil
        import tempfile

        first_dir = Path(tempfile.mkdtemp(prefix="nodus-det-a-"))
        second_dir = Path(tempfile.mkdtemp(prefix="nodus-det-b-"))
        try:
            first = self._addresses(first_dir)
            second = self._addresses(second_dir)
        finally:
            shutil.rmtree(first_dir, ignore_errors=True)
            shutil.rmtree(second_dir, ignore_errors=True)
        self.assertNotEqual("{}", first, "the probe reported no addresses at all")
        self.assertEqual(
            first,
            second,
            "identical source compiled to different addresses in two processes, "
            "so a persisted instruction pointer does not survive a restart and "
            "§3.3 of the design is wrong",
        )


class DurabilityMustBeDeclaredRatherThanInferredTests(unittest.TestCase):
    """§3.4 and §5. These pin *obstacles*. If one disappeared the design would be
    recommending unnecessary machinery, and only a test that asserts the obstacle
    would say so."""

    def test_the_idiomatic_spawn_has_no_durable_name(self):
        observed = _observe()["named-top-level"]
        self.assertTrue(
            observed["display_name"].startswith("__anon"),
            "`spawn(coroutine(fn() { ... }))` now reports a durable name "
            f"({observed['display_name']!r}). If a coroutine's entry point can "
            "be named without being declared, §5 option A stops being an index "
            "dressed as a name and the recommendation should be revisited.",
        )

    def test_a_named_top_level_entry_does_carry_its_name(self):
        """The control. Without it the test above is satisfied by a build where
        no function has a usable name at all."""
        observed = _observe()["local-holds-a-channel"]
        self.assertEqual("holds_a_channel", observed["display_name"])
        self.assertEqual(0, observed["upvalues"])

    def test_a_closure_over_a_local_carries_upvalues(self):
        """Upvalue *values* may be durable; `Cell` identity is not. Two closures
        sharing a captured variable (#671) would come back from a resume holding
        independent cells, so this case must be refused rather than approximated."""
        self.assertEqual(1, _observe()["closure-over-local"]["upvalues"])

    def test_a_local_can_hold_a_value_that_cannot_be_written_down(self):
        frames = _observe()["local-holds-a-channel"]["frames"]
        locals_by_name = {
            name: safe for frame in frames for name, safe in frame["locals"].items()
        }
        self.assertIn("ch", locals_by_name, f"probe saw no `ch` local: {frames}")
        self.assertFalse(
            locals_by_name["ch"],
            "a channel in a local is now JSON-serialisable, which would remove "
            "the runtime half of §4.1's refusal rule",
        )
        self.assertTrue(
            locals_by_name.get("n"),
            "the control: an ordinary int local must still be durable, or this "
            "test is passing because nothing is serialisable",
        )


class TheDesignDocumentIsPresentTests(unittest.TestCase):
    """These tests are only meaningful as the premises *of* something."""

    def test_the_design_document_exists_and_names_this_file(self):
        self.assertTrue(_DESIGN.exists(), f"{_DESIGN} is missing")
        text = _DESIGN.read_text(encoding="utf-8-sig")
        self.assertIn("test_durable_coroutine_premises.py", text)
        self.assertIn("Status: proposal", text)


if __name__ == "__main__":
    unittest.main()
