"""A compiler-applied guarantee must hold against the program's author (#411).

`@exactly_once` and `@retry` lower to calls on `effect_*` / `retry_call`. Those
calls used to go through ordinary name resolution, and `VM._op_call` resolves user
functions *before* builtins — so a program could supply the machinery the compiler
injected into its own code:

    fn effect_resolve(aid) { return {done: true, cached: {result: "FORGED"}} }

    @exactly_once
    fn work() { return "real" }

    print(work())        // -> FORGED; the annotated body never ran

Audit 03 §8 named this lowering as one of only three things Nodus genuinely gains
by owning the compiler — *"the compiler lowering guarantees every annotated
function gets the resolve→pending→execute→complete envelope … **You cannot forget
it.**"* You could not forget it. You could defeat it.

The fix emits the lowering's calls through `BUILTIN_CALL_PREFIX`, which
`_op_call` dispatches straight to the builtin table before any user lookup.

**Two things these tests exist to pin, beyond "the forgery fails":**

1. **Local bindings, not just globals.** A *parameter* named `effect_resolve`
   forged the envelope exactly as well as a top-level `fn` did. That vector is not
   in the issue, and it is why reserving a list of global names — the issue's
   option (2) — would not have been a fix.
2. **The guarantee still has to do its job.** A lowering that silently stopped
   calling the effect builtins at all would pass every negative test here. Each
   forgery test has a positive control: dedup must still short-circuit, and
   `@retry` must still retry.
"""

import unittest

from nodus.builtins.nodus_builtins import BUILTIN_CALL_PREFIX
from nodus.runtime.embedding import NodusRuntime

try:  # `@retry` lowers onto nodus-retry, which is an optional extra.
    import nodus_retry  # noqa: F401

    HAS_NODUS_RETRY = True
except ImportError:  # pragma: no cover - depends on the install
    HAS_NODUS_RETRY = False


def run(source: str) -> dict:
    rt = NodusRuntime(timeout_ms=None)
    try:
        return rt.run_source(source, filename="t.nd")
    finally:
        rt.shutdown()


class TestExactlyOnceIsNotForgeable(unittest.TestCase):
    # closes: #411
    def test_shadowing_effect_resolve_does_not_defeat_the_envelope(self):
        result = run(
            'fn effect_resolve(aid) { return {done: true, cached: {result: "FORGED"}} }\n'
            "\n"
            "@exactly_once\n"
            'fn work() { return "real" }\n'
            "\n"
            'print(work())\n'
        )
        self.assertTrue(result.get("ok"), result)
        self.assertIn("real", result["stdout"])
        self.assertNotIn("FORGED", result["stdout"])

    def test_shadowing_every_effect_builtin_does_not_defeat_the_envelope(self):
        """The whole envelope at once, not just the resolve step."""
        result = run(
            'fn effect_action_id(n, p, s) { return "forged-aid" }\n'
            'fn effect_resolve(aid) { return {done: true, cached: {result: "FORGED"}} }\n'
            "fn effect_pending(aid, m) { return nil }\n"
            "fn effect_complete(aid, s, r) { return nil }\n"
            "\n"
            "@exactly_once\n"
            'fn work() { return "real" }\n'
            "\n"
            'print(work())\n'
        )
        self.assertTrue(result.get("ok"), result)
        self.assertIn("real", result["stdout"])
        self.assertNotIn("FORGED", result["stdout"])

    def test_a_parameter_cannot_forge_the_envelope(self):
        """Not in #411, and the reason a reserved-global-names fix is insufficient.

        A parameter is a *local* binding, so it resolves ahead of any global and
        ahead of the builtin. Before the fix this printed FORGED-VIA-PARAM.
        """
        result = run(
            "@exactly_once\n"
            'fn work(effect_resolve) { return "real" }\n'
            "\n"
            'fn forge(aid) { return {done: true, cached: {result: "FORGED-VIA-PARAM"}} }\n'
            "\n"
            'print(work(forge))\n'
        )
        self.assertTrue(result.get("ok"), result)
        self.assertIn("real", result["stdout"])
        self.assertNotIn("FORGED", result["stdout"])

    def test_positive_control_dedup_still_short_circuits(self):
        """Without this, a lowering that stopped calling the builtins entirely
        would pass every test above."""
        result = run(
            "@exactly_once\n"
            'fn work(n) { print("body ran"); return "real-\\(n)" }\n'
            "\n"
            'print(work(1i))\n'
            'print(work(1i))\n'
        )
        self.assertTrue(result.get("ok"), result)
        out = result["stdout"]
        self.assertEqual(out.count("body ran"), 1, f"body ran more than once:\n{out}")
        self.assertEqual(out.count("real-1"), 2, f"cached result not returned:\n{out}")

    def test_a_shadow_declared_after_the_annotated_fn_also_fails(self):
        """Definition order must not matter. Both are hoisted; neither wins."""
        result = run(
            "@exactly_once\n"
            'fn charge(amount) { return "CHARGED \\(amount)" }\n'
            "\n"
            'fn effect_resolve(aid) { return {done: true, cached: {result: "FORGED"}} }\n'
            "\n"
            'print(charge(100i))\n'
        )
        self.assertTrue(result.get("ok"), result)
        self.assertIn("CHARGED 100", result["stdout"])
        self.assertNotIn("FORGED", result["stdout"])


class TestModuleBoundary(unittest.TestCase):
    """The bound #411 claimed: a caller cannot forge an *imported* module's envelope.

    This was already true before the fix — a library's annotated function resolved
    the effect builtins in its own module scope — and it is what bounded the
    issue's severity. Pinned with a genuine two-file import so it stays true, since
    the fix changes how those calls resolve.
    """

    def test_a_caller_cannot_forge_an_imported_modules_envelope(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "lib.nd"), "w", encoding="utf-8") as fh:
                fh.write(
                    "@exactly_once\n"
                    'fn charge(amount) { return "CHARGED \\(amount)" }\n'
                )
            main = os.path.join(td, "main.nd")
            with open(main, "w", encoding="utf-8") as fh:
                fh.write(
                    'import "./lib.nd" as lib\n'
                    'fn effect_resolve(aid) { return {done: true, cached: {result: "FORGED"}} }\n'
                    'print(lib.charge(100i))\n'
                )

            rt = NodusRuntime(timeout_ms=None, allowed_paths=[td], project_root=td)
            try:
                result = rt.run_file(main)
            finally:
                rt.shutdown()

        self.assertTrue(result.get("ok"), result)
        self.assertIn("CHARGED 100", result["stdout"])
        self.assertNotIn("FORGED", result["stdout"])


class TestRetryIsNotForgeable(unittest.TestCase):
    # closes: #411
    def test_shadowing_retry_call_does_not_defeat_the_annotation(self):
        """Asserted on the forgery, not on success — so it holds either way.

        `@retry` needs the optional `nodus-lang[retry]` extra. Without it the run
        fails with a dependency error, which is *also* "not forged"; with it, the
        real body runs. Both are correct outcomes and both are regressions from
        what happened before the fix, where the shadow was simply called and
        printed FORGED-RETRY — including on a machine with no nodus-retry at all,
        because the shadow replaced the builtin that would have raised.

        Checking `ok` here is what made this fail on CI while passing locally: the
        dev venv has nodus-retry installed and a clean runner does not.
        """
        result = run(
            'fn retry_call(f, policy) { return "FORGED-RETRY" }\n'
            "\n"
            "@retry(max_attempts: 3)\n"
            'fn work() { return "real" }\n'
            "\n"
            'print(work())\n'
        )
        self.assertNotIn("FORGED", result["stdout"])
        if result.get("ok"):
            self.assertIn("real", result["stdout"])
        else:
            # The only acceptable failure is the missing optional dependency.
            self.assertEqual(result["error"].get("kind"), "dependency", result)

    @unittest.skipUnless(HAS_NODUS_RETRY, "requires the optional nodus-lang[retry] extra")
    def test_positive_control_retry_still_retries(self):
        result = run(
            'let state = {"n": 0i}\n'
            "\n"
            "@retry(max_attempts: 3)\n"
            "fn flaky() {\n"
            '    state["n"] = state["n"] + 1i\n'
            '    if (state["n"] < 3i) { throw "boom" }\n'
            '    return "ok after \\(state["n"])"\n'
            "}\n"
            "\n"
            "print(flaky())\n"
        )
        self.assertTrue(result.get("ok"), result)
        self.assertIn("ok after 3", result["stdout"])


class TestWorkflowLoweringIsNotForgeable(unittest.TestCase):
    """The same hole, in a second lowering — found by asking what else had the shape.

    #411 named `workflow_state` in passing as "same for any builtin a lowering
    depends on" without demonstrating it. It was live: the workflow lowering emits
    `let __workflow_state = workflow_state()` at the head of every step body, plus
    five `__action_*` calls, all as ordinary `Call(Var(...))`. Shadowing
    `workflow_state` replaced the state map every step reads.

    This is why the fix lives in a shared helper rather than on `Compiler` — the
    lowerings are split across the compiler and `orchestration/`, and fixing only
    the annotations would have left this one forgeable.
    """

    # closes: #411
    def test_shadowing_workflow_state_does_not_replace_step_state(self):
        result = run(
            'fn workflow_state() { return {"total": 9999i} }\n'
            "\n"
            "workflow w {\n"
            "    state total = 0i\n"
            "\n"
            "    step add {\n"
            "        total = total + 1i\n"
            '        print("total is \\(total)")\n'
            "    }\n"
            "}\n"
            "\n"
            "let r = run_workflow(w)\n"
            'print("failed: \\(r["failed"])")\n'
        )
        self.assertTrue(result.get("ok"), result)
        self.assertIn("total is 1", result["stdout"])
        self.assertNotIn("10000", result["stdout"])
        self.assertIn("failed: []", result["stdout"])

    def test_positive_control_workflow_state_still_flows_between_steps(self):
        """A lowering that stopped calling `workflow_state` would pass the test
        above and break every stateful workflow."""
        result = run(
            "workflow w {\n"
            "    state total = 0i\n"
            '    step add { total = total + 1i; print("total is \\(total)") }\n'
            '    step more after add { total = total + 5i; print("then \\(total)") }\n'
            "}\n"
            "let r = run_workflow(w)\n"
            'print("failed: \\(r["failed"])")\n'
        )
        self.assertTrue(result.get("ok"), result)
        self.assertIn("total is 1", result["stdout"])
        self.assertIn("then 6", result["stdout"])
        self.assertIn("failed: []", result["stdout"])

    def test_the_action_matcher_sees_through_the_prefix(self):
        """Binding the call must not break the code that *matches* on it.

        `_is_action_builtin` decides whether a step body's trailing action becomes
        a `Return`. It compared the raw callee name, so prefixing the call silently
        stopped it matching and every step ending in an action returned nil — four
        `test_goal_dsl` cases failed with "Indexing is only supported on lists,
        maps, and strings" a full call away from the cause.

        The same defect as #411 in miniature: a name-based decision broken by a
        rename.
        """
        from nodus.frontend.ast.ast_nodes import Call, Str, Var
        from nodus.orchestration.workflow_lowering import (
            ACTION_BUILTINS,
            _is_action_builtin,
            builtin_call,
        )

        for name in ACTION_BUILTINS:
            with self.subTest(action=name):
                self.assertTrue(
                    _is_action_builtin(builtin_call(name, [Str("t")])),
                    f"{name} not recognised in its bound form",
                )
                self.assertTrue(
                    _is_action_builtin(Call(Var(name), [Str("t")])),
                    f"{name} not recognised in its plain form",
                )
        self.assertFalse(_is_action_builtin(Call(Var("not_an_action"), [])))

    def test_a_step_ending_in_an_action_still_returns_its_result(self):
        """The behaviour the matcher exists for, end to end."""
        result = run(
            'import "std:tool" as tool\n'
            'tool.register({name: "t.echo", description: "echo",\n'
            '               handler: fn(args) { return {ok: true} }})\n'
            "workflow w {\n"
            '    step s { tool "t.echo" }\n'
            "}\n"
            "let r = run_workflow(w)\n"
            'print("failed: \\(r["failed"])")\n'
        )
        self.assertTrue(result.get("ok"), result)
        self.assertIn("failed: []", result["stdout"])

    def test_no_workflow_lowering_emits_an_unbound_builtin_call(self):
        """Assert on the source, as for the annotation lowerings."""
        import inspect

        from nodus.orchestration import workflow_lowering

        src = inspect.getsource(workflow_lowering)
        for name in (
            "workflow_state", "__action_tool", "__action_agent",
            "__action_memory_put", "__action_memory_get", "__action_emit",
        ):
            self.assertNotIn(
                f'Call(Var("{name}")',
                src,
                f"workflow lowering emits Var({name!r}) directly; it must use "
                "builtin_call() or a program can shadow it (#411)",
            )


class TestReservedCompilerNamespace(unittest.TestCase):
    """The prefix a lowering uses cannot be entered from source."""

    # closes: #411
    def test_a_function_cannot_be_defined_in_the_reserved_namespace(self):
        result = run(
            f"fn {BUILTIN_CALL_PREFIX}effect_resolve(aid) {{ return 1i }}\n"
            'print("defined")\n'
        )
        self.assertFalse(result.get("ok"), result)
        self.assertIn("reserved", str(result["error"]["message"]))

    def test_a_let_cannot_be_defined_in_the_reserved_namespace(self):
        result = run(f"let {BUILTIN_CALL_PREFIX}foo = 1i\nprint(\"defined\")\n")
        self.assertFalse(result.get("ok"), result)
        self.assertIn("reserved", str(result["error"]["message"]))

    def test_a_parameter_cannot_be_named_in_the_reserved_namespace(self):
        result = run(
            f"fn f({BUILTIN_CALL_PREFIX}x) {{ return 1i }}\nprint(f(1i))\n"
        )
        self.assertFalse(result.get("ok"), result)
        self.assertIn("reserved", str(result["error"]["message"]))

    def test_the_ordinary_nodus_prefix_is_still_usable(self):
        """Only `__nodus_builtin__` is reserved. The lowering's own temporaries use
        `__nodus_aid` / `__nodus_st` / `__nodus_res`, and reserving all of
        `__nodus_` would break them and anyone else using the prefix."""
        result = run('let __nodus_ordinary = 1i\nprint(__nodus_ordinary)\n')
        self.assertTrue(result.get("ok"), result)
        self.assertIn("1", result["stdout"])


class TestLoweringEmitsBoundCalls(unittest.TestCase):
    """Assert on the source of the guarantee, not only its behaviour.

    Per this codebase's rule: a behaviour test passes on whichever path already
    works. If a future lowering is added that emits an ordinary `Call(Var(name))`,
    the tests above say nothing about it — this one does.
    """

    # closes: #411
    def test_no_lowering_emits_an_unbound_builtin_call(self):
        import inspect

        from nodus.compiler.compiler import Compiler

        for lowering in (Compiler._lower_exactly_once, Compiler._lower_retry):
            src = inspect.getsource(lowering)
            for name in (
                "effect_action_id", "effect_resolve", "effect_pending",
                "effect_complete", "retry_call",
            ):
                self.assertNotIn(
                    f'Var("{name}")',
                    src,
                    f"{lowering.__name__} emits Var({name!r}) directly; it must use "
                    "Compiler.builtin_call() or the program can shadow it (#411)",
                )

    def test_builtin_call_produces_the_reserved_prefix(self):
        from nodus.compiler.compiler import Compiler

        call = Compiler.builtin_call("effect_resolve", [])
        self.assertEqual(call.callee.name, f"{BUILTIN_CALL_PREFIX}effect_resolve")


if __name__ == "__main__":
    unittest.main()
