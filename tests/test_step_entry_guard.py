"""A workflow step body runs only when the graph runner starts it (#394).

`step B after A` was the strongest ordering claim the runtime made, and it held
only for execution routed through `run_workflow`/`run_task_graph`. A lowered flow
is an ordinary map, its `steps` an ordinary list, and each step's `fn` an ordinary
callable, so `build["steps"][1]["fn"](nil)` ran `test` with `lint` never having
run. `I-WFLOW-04` described `ready_tasks()`; the document's own preamble defines
an invariant as a guarantee made *to scripts*, and by that definition the claim
was false.

The recurring-bug-shape rule applies with force here, because the obvious fixes
are both the wrong shape:

  - "raise unless a workflow context is active" passes for a step body calling a
    *sibling's* `fn`, which is the same ordering violation from inside the run;
  - "allow `run_closure`, refuse `call_closure`" mistakes the door for the
    authority. `run_closure` has two dozen callers -- `std:retry`, `std:test`,
    tool handlers, the iterator protocol -- and a guest can hand a step closure
    to any of them.

So authorization is a positive capability the runner grants for one entry, and
the guard lives in exactly one function. This file asserts on the *source* as
well as the behaviour, because a behaviour-only test passes as soon as the doors
it happens to know about are shut.
"""

import ast
import io
import os
import pathlib
import sys
import tempfile
import unittest

# Derived, not hardcoded: this file *reads* source out of the tree, so a literal
# "C:/dev/Coding Language" passes locally and fails on the Linux CI runner --
# which is exactly what it did. Other tests here hardcode it harmlessly because
# they only feed `sys.path`, where a non-existent entry is ignored.
REPO = pathlib.Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO / "src"))

from nodus.runtime.embedding import NodusRuntime  # noqa: E402


FLOW = """
let log = {"s": ""}

workflow build {
    step lint { log["s"] = log["s"] + "lint;" return "linted" }
    step test after lint { log["s"] = log["s"] + "test;" return "tested" }
}
"""


def run(source: str):
    return NodusRuntime(timeout_ms=None).run_source(source)


# --------------------------------------------------------------------------
# Behaviour: the routed path still works, and every door into a step is shut.
# --------------------------------------------------------------------------


# closes: #394
class StepOrderingIsAnInvariantTests(unittest.TestCase):

    def test_the_routed_path_still_runs_both_steps_in_order(self):
        """The positive control. If this ever stops firing the rest proves nothing."""
        result = run(FLOW + """
let r = run_workflow(build)
print("failed=\\(r["failed"]) log=\\(log["s"])")
""")
        self.assertTrue(result["ok"], result)
        self.assertIn("failed=[]", result["stdout"])
        self.assertIn("log=lint;test;", result["stdout"])

    def test_door_1_a_direct_call_on_the_step_closure_is_refused(self):
        result = run(FLOW + """
let f = build["steps"][1]["fn"]
print(f(nil))
""")
        self.assertFalse(result["ok"])
        self.assertIn("build.test", result["error"]["message"])
        self.assertIn("cannot be called directly", result["error"]["message"])

    def test_door_2_handing_the_closure_to_a_run_closure_caller_is_refused(self):
        """`std:retry` reaches `run_closure`, the method the runner also uses."""
        result = run("""
import "std:retry"
""" + FLOW + """
let f = build["steps"][0]["fn"]
try {
    retry.run(f, {"max_attempts": 1i})
    print("BYPASSED")
} catch e {
    print("refused")
}
print("log='\\(log["s"])'")
""")
        self.assertTrue(result["ok"], result)
        self.assertIn("refused", result["stdout"])
        self.assertIn("log=''", result["stdout"])

    def test_door_4_a_guest_coroutine_over_the_step_closure_is_refused(self):
        """The runner's own route (I-WFLOW-03), so the grant must ride on the coroutine."""
        result = run(FLOW + """
let c = coroutine(build["steps"][0]["fn"])
spawn(c)
run_loop()
print("log='\\(log["s"])'")
""")
        # A coroutine error surfaces at top level rather than at `run_loop()`;
        # that is the pre-existing model for any throwing coroutine, not
        # something this guard introduced. What matters is that `lint` did not
        # run: the log is still empty.
        self.assertIn("log=''", result["stdout"])

    def test_a_refused_coroutine_does_not_strand_the_scheduler(self):
        """Raising mid-start left the coroutine half-started and `run_loop` spun
        to the execution deadline, reporting a timeout rather than the refusal.
        A guard that corrupts what it refuses is worse than no guard."""
        result = run(FLOW + """
let c = coroutine(build["steps"][0]["fn"])
spawn(c)
run_loop()
print("survived")
""")
        self.assertIn("survived", result["stdout"])
        if not result["ok"]:
            self.assertNotIn("timed out", result["error"]["message"].lower())

    def test_goal_steps_are_marked_too(self):
        result = run("""
let log = {"s": ""}
goal ship {
    step build { log["s"] = log["s"] + "build;" return "built" }
    step deploy after build { log["s"] = log["s"] + "deploy;" return "deployed" }
}
let r = run_goal(ship)
print("failed=\\(r["failed"]) log=\\(log["s"])")
""")
        self.assertTrue(result["ok"], result)
        self.assertIn("log=build;deploy;", result["stdout"])

        refused = run("""
let log = {"s": ""}
goal ship {
    step build { return "built" }
    step deploy after build { return "deployed" }
}
print(ship["steps"][1]["fn"](nil))
""")
        self.assertFalse(refused["ok"])
        self.assertIn("ship.deploy", refused["error"]["message"])

    def test_the_mark_survives_the_bytecode_cache(self):
        """The half that inspection missed.

        Guarding the compilation path alone left the bypass reachable on the
        *second* run of any script: `FunctionInfo` is serialized into the cached
        module and `step_owner` was not among the fields written, so a warm cache
        handed back an unmarked closure and `build["steps"][1]["fn"](nil)` ran.
        Run 1 refused, run 2 executed — the same sibling-path shape as #521 and
        #400, where the bytecode cache was a third route to a question two other
        places already answered. Found by running it twice, not by reading.
        """
        import subprocess

        with tempfile.TemporaryDirectory() as workdir:
            script = os.path.join(workdir, "bypass.nd")
            with io.open(script, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(FLOW + '\nprint(build["steps"][1]["fn"](nil))\n')

            env = {**os.environ, "PYTHONPATH": str(REPO / "src")}
            for run_number in (1, 2, 3):
                proc = subprocess.run(
                    [sys.executable, str(REPO / "nodus.py"), "run", script],
                    cwd=workdir, capture_output=True, text=True, env=env, timeout=120,
                )
                combined = proc.stdout + proc.stderr
                with self.subTest(run=run_number):
                    self.assertIn("cannot be called directly", combined,
                                  f"run {run_number} (cache is warm from run 2 on) "
                                  f"let the step body through")
                    self.assertNotIn("-> tested", combined)
            self.assertTrue(os.path.isdir(os.path.join(workdir, ".nodus", "cache")),
                            "no cache was written, so runs 2 and 3 proved nothing")

    def test_an_ordinary_function_is_untouched(self):
        """The mark is set by the lowering and nothing else, so a plain closure --
        including one that merely lives in a map -- still calls normally."""
        result = run("""
fn greet(x) { return "hi \\(x)" }
let m = {"fn": greet}
print(m["fn"]("world"))
let anon = fn() { return "anon" }
print(anon())
""")
        self.assertTrue(result["ok"], result)
        self.assertIn("hi world", result["stdout"])
        self.assertIn("anon", result["stdout"])


# --------------------------------------------------------------------------
# Source: the set of closure-entry sites, so a fifth door fails the suite.
# --------------------------------------------------------------------------

# Every place a `Frame` is built. The value says why the site is safe:
#   "guarded"        -- enters a caller-supplied closure, so it must call
#                       `guard_step_entry`; asserted below.
#   "builds-its-own" -- constructs its `Closure` locally from a module's own
#                       function table. A step body is an anonymous `FnExpr` and
#                       never lands there, so it is unreachable by this route.
#   "no-closure"     -- a named top-level function; `closure=None`.
#
# This mapping is the point of the file. Adding a fifth way to enter a closure
# fails `test_the_set_of_closure_entry_sites_is_closed` until somebody classifies
# it, rather than silently reopening #394.
CLOSURE_ENTRY_SITES = {
    ("src/nodus/vm/vm.py", "call_closure"): "guarded",
    ("src/nodus/vm/vm.py", "run_closure"): "guarded",
    ("src/nodus/vm/vm.py", "_try_enter_foreign_closure"): "guarded",
    ("src/nodus/builtins/coroutine.py", "builtin_coroutine_resume"): "guarded",
    ("src/nodus/vm/vm.py", "_try_enter_module_call"): "builds-its-own",
    ("src/nodus/vm/vm.py", "_op_call"): "no-closure",
}


def _frame_construction_sites() -> dict[tuple[str, str], str]:
    """Every function in `src/` that constructs a `Frame`, with its closure arg."""
    found: dict[tuple[str, str], str] = {}
    for path in sorted(REPO.joinpath("src").rglob("*.py")):
        source = io.open(path, encoding="utf-8").read()
        if "Frame(" not in source:
            continue
        tree = ast.parse(source)
        functions = [n for n in ast.walk(tree)
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and getattr(node.func, "id", None) == "Frame"):
                continue
            enclosing = None
            for fn in functions:
                if fn.lineno <= node.lineno <= (fn.end_lineno or fn.lineno):
                    if enclosing is None or fn.lineno > enclosing.lineno:
                        enclosing = fn
            kwargs = {k.arg: ast.unparse(k.value) for k in node.keywords}
            rel = path.relative_to(REPO).as_posix()
            found[(rel, enclosing.name if enclosing else "?")] = kwargs.get("closure")
    return found


def _function_source(rel_path: str, name: str) -> str:
    source = io.open(REPO / rel_path, encoding="utf-8").read()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"{name} not found in {rel_path}")


class ClosureEntrySitesAreEnumeratedTests(unittest.TestCase):

    def test_the_set_of_closure_entry_sites_is_closed(self):
        discovered = set(_frame_construction_sites())
        known = set(CLOSURE_ENTRY_SITES)
        new = discovered - known
        self.assertFalse(new, (
            f"New closure-entry site(s): {sorted(new)}. A `Frame` built over a "
            f"caller-supplied closure is a door into a workflow step body (#394). "
            f"Call `VM.guard_step_entry` there and add it to CLOSURE_ENTRY_SITES, "
            f"or record why it cannot reach one."
        ))
        gone = known - discovered
        self.assertFalse(gone, f"Entry site(s) disappeared, update the map: {sorted(gone)}")

    def test_every_caller_supplied_entry_consults_the_guard(self):
        for (rel, name), kind in sorted(CLOSURE_ENTRY_SITES.items()):
            if kind != "guarded":
                continue
            with self.subTest(site=f"{rel}::{name}"):
                self.assertIn("guard_step_entry", _function_source(rel, name),
                              f"{name} enters a caller-supplied closure without "
                              f"consulting the #394 guard")

    def test_the_locally_built_entry_really_builds_its_own_closure(self):
        """`builds-its-own` is a claim, so check it rather than trusting the label."""
        body = _function_source("src/nodus/vm/vm.py", "_try_enter_module_call")
        self.assertIn("closure = Closure(", body)

    def test_the_decision_lives_in_one_place(self):
        """The retry defect (#392/#393) survived ten weeks as a wrapper argument
        one of five callers passed. Keep the authority in the guard, not spread
        across the doors."""
        vm_source = io.open(REPO / "src/nodus/vm/vm.py", encoding="utf-8").read()
        self.assertEqual(1, vm_source.count("def guard_step_entry"))
        self.assertIn("step_owner", _function_source("src/nodus/vm/vm.py",
                                                     "guard_step_entry"))

    def test_the_mark_is_carried_across_every_functioninfo_rebuild(self):
        """`FunctionInfo` is rebuilt in three places outside the compiler: the
        cache round-trip and the optimizer's two remappers. Each drops whatever
        it does not name, which is how the warm-cache bypass survived the first
        version of this fix."""
        module_src = io.open(REPO / "src/nodus/runtime/module.py", encoding="utf-8").read()
        self.assertIn('"step_owner": fn.step_owner', module_src,
                      "the cache does not serialize the mark")
        self.assertIn("step_owner=(raw[\"step_owner\"]", module_src,
                      "the cache does not restore the mark")

        optimizer_src = io.open(REPO / "src/nodus/compiler/optimizer.py", encoding="utf-8").read()
        rebuilds = optimizer_src.count("FunctionInfo(info.name")
        carried = optimizer_src.count("step_owner=info.step_owner")
        self.assertEqual(rebuilds, carried,
                         f"{rebuilds} FunctionInfo rebuild(s) in the optimizer but "
                         f"{carried} carry `step_owner`")

    def test_exactly_one_site_originates_a_step_mark(self):
        """A guest cannot mark a function, and -- the half that matters -- cannot
        unmark one.

        `step_owner` appears in two roles and they must not be confused. Exactly
        one site *originates* a mark, computing it from a step's own name; the
        rest merely *carry* an existing one across a FunctionInfo rebuild. This
        test failed once already, on the propagation sites added when the warm
        cache turned out to drop the mark -- which is the distinction being
        drawn here rather than an exception being made.
        """
        ORIGINATOR = "src/nodus/orchestration/workflow_lowering.py"
        CARRIERS = {
            "src/nodus/compiler/compiler.py",        # FnExpr -> FnDef -> FunctionInfo
            "src/nodus/compiler/optimizer.py",       # two address remappers
            "src/nodus/runtime/module.py",           # the bytecode cache round-trip
        }
        # Neither originates nor carries: one declares the field, one reads it.
        DECLARES = {"src/nodus/frontend/ast/ast_nodes.py"}
        READS = {"src/nodus/vm/vm.py"}

        sites: dict[str, list[int]] = {}
        for path in sorted(REPO.joinpath("src").rglob("*.py")):
            source = io.open(path, encoding="utf-8").read()
            for lineno, line in enumerate(source.splitlines(), 1):
                if "step_owner" not in line or line.lstrip().startswith("#"):
                    continue
                sites.setdefault(path.relative_to(REPO).as_posix(), []).append(lineno)

        self.assertEqual(
            set(sites), {ORIGINATOR} | CARRIERS | DECLARES | READS,
            f"`step_owner` touched somewhere unclassified: {sorted(sites)}. A new "
            f"*carrier* is fine -- add it to CARRIERS. A new *originator* is not: "
            f"the mark must come from the lowering alone.",
        )

        originating = io.open(REPO / ORIGINATOR, encoding="utf-8").read()
        self.assertIn('step_owner=f"{flow_name}.{step.name}"', originating)

        for reader in sorted(READS):
            body = io.open(REPO / reader, encoding="utf-8").read()
            for lineno in sites[reader]:
                line = body.splitlines()[lineno - 1]
                self.assertIn("getattr", line,
                              f"{reader}:{lineno} touches `step_owner` other than by "
                              f"reading it in the guard")

        # Every carrier copies; none of them computes a mark of its own.
        for carrier in sorted(CARRIERS):
            body = io.open(REPO / carrier, encoding="utf-8").read()
            with self.subTest(carrier=carrier):
                for lineno in sites[carrier]:
                    line = body.splitlines()[lineno - 1]
                    self.assertNotIn('step_owner=f"', line,
                                     f"{carrier}:{lineno} originates a mark")
                    self.assertNotIn("step_owner='", line,
                                     f"{carrier}:{lineno} originates a mark")

# --------------------------------------------------------------------------
# The runner's grant.
# --------------------------------------------------------------------------


class OnlyTheRunnerGrantsAuthorizationTests(unittest.TestCase):

    def test_the_grant_is_made_only_by_the_graph_runner(self):
        grants = []
        for path in sorted(REPO.joinpath("src").rglob("*.py")):
            source = io.open(path, encoding="utf-8").read()
            for lineno, line in enumerate(source.splitlines(), 1):
                if "step_authorized=True" in line or "step_authorized = True" in line:
                    grants.append((path.relative_to(REPO).as_posix(), lineno))
        self.assertTrue(grants, "nothing grants authorization -- no step could run")
        self.assertEqual(
            {rel for rel, _ in grants},
            {"src/nodus/orchestration/task_graph.py"},
            f"authorization granted outside the graph runner: {grants}",
        )

    def test_the_default_is_unauthorized(self):
        """The two dozen other `run_closure` callers must not have to know about
        this. Keep the safe value the default one."""
        from nodus.runtime.coroutine import Coroutine
        import inspect
        from nodus.vm.vm import VM

        self.assertIs(False, Coroutine(closure=None).step_authorized)
        signature = inspect.signature(VM.run_closure)
        self.assertIs(False, signature.parameters["step_authorized"].default)


if __name__ == "__main__":
    unittest.main()
