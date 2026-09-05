"""Every route that runs submitted code goes through one guard (#754).

`RuntimeService` builds VMs itself and hands them submitted source. What bounds
those VMs is `_apply_runtime_policies`, and its value depends entirely on being
the **only** way through: a route that builds a VM and runs code without it gets
an unconfined one, and looks exactly like a route that works.

That is this codebase's signature defect — a correct check that only some of
several paths go through — and the server is a good place for it to happen,
because a route is a dozen lines and the guard is one of them. #405 hit exactly
this twice: the capability policy was consulted at `_invoke_host_function` and
not `VM.call_builtin`, and a derived VM built a fresh one and shed the parent's
limits.

So this file asserts the *shape* rather than any one route's behaviour. A
behavioural test passes on whichever routes are already correct and says nothing
about the tenth one somebody adds next year.

**The runner set is derived from the import list, not written out here.** A
hand-maintained list of "functions that run code" is the same drifted-vocabulary
problem one level up — it would go stale the moment `runner.py` exported
something new, and it would go stale *silently*, reporting zero unguarded
routes because it had stopped looking for the right names. Deriving it means a
new runner import is covered the day it lands, and `ANALYSERS` below has to be
justified per name.
"""

import ast
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

_SERVER = _REPO_ROOT / "src" / "nodus" / "services" / "server.py"

#: Imported from `nodus.tooling.runner` but read-only: they parse, type-check or
#: disassemble, and never construct a VM or execute anything. Each is excluded by
#: name so that adding a genuine runner cannot be waved through by a pattern.
ANALYSERS = frozenset({
    "build_ast",            # parses to an AST
    "check_source",         # static diagnostics
    "disassemble_source",   # compiles and prints; never runs
    "workflow_checkpoints", # reads checkpoints off a stored record
    # These invoke something the *host* registered, not submitted source. A
    # tool or agent handler is host code by construction -- a guest cannot
    # register one (see the agent-isolation note in embedding.py).
    "tool_call_result",
    "agent_call_result",
    # Store operations against the memory backend.
    "memory_get_result",
    "memory_put_result",
    "memory_keys_result",
    "memory_delete_result",
})

#: Helpers that build a VM and apply the guard themselves, so a route handing
#: one of these off is guarded transitively. `_new_vm` applies the policies as
#: of #754 — the service should not be *able* to hand out an unconfined VM, and
#: "every route remembers to call the guard afterwards" is a convention, which
#: is the thing the recurring shape eats. Both are verified below rather than
#: trusted, since an entry here silences a whole route.
GUARDING_FACTORIES = frozenset({"_workflow_vm_factory", "_new_vm"})

#: Methods that delegate wholly to another guarded method on the same object.
DELEGATES = frozenset({"_worker_sweeper_loop"})

GUARD = "_apply_runtime_policies"


def _tree():
    return ast.parse(_SERVER.read_text(encoding="utf-8"))


def _runner_names(tree) -> set[str]:
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "nodus.tooling.runner"
        for alias in node.names
    }
    assert imported, "the import scan found nothing -- it is looking in the wrong place"
    return (imported - ANALYSERS) | {"sweep", "deliver_event", "rehydrate_run"}


def _service(tree):
    return next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "RuntimeService"
    )


def _called_names(fn) -> set[str]:
    names = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name:
                names.add(name)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


_NESTED_FIELDS = ("body", "orelse", "finalbody", "handlers")


def _surface_names(stmt) -> set[str]:
    """Names called by this statement itself, *not* by statements nested in it.

    The distinction is the whole test. `_called_names` recurses, so for an `if`
    it returns everything in both branches — and an earlier version used that,
    which let a guard inside one branch mark the code *after* the `if` as
    guarded. The neutered tree passed. Nested bodies are visited by `walk`
    instead, each carrying only what actually precedes it.
    """
    names: set[str] = set()
    stack = [stmt]
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name:
                names.add(name)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        for field, value in ast.iter_fields(node):
            if isinstance(value, list):
                items = [item for item in value if isinstance(item, ast.AST)]
                # Do not descend into nested *statements*; `walk` visits those
                # with the guard state that actually reaches them.
                if items and isinstance(items[0], (ast.stmt, ast.excepthandler)):
                    continue
                stack.extend(items)
            elif isinstance(value, ast.AST):
                stack.append(value)
    return names


def _unguarded_runner_calls(fn, runners: set[str]) -> list[str]:
    """Runner calls with no guard *before them on their own path*.

    Per-method granularity is not enough, and that is not a hypothetical: the
    first version of this file asked only whether a method mentioned the guard
    anywhere, and it stayed green when the guard was deleted from one of
    `execute`'s two branches. A method with a guarded branch and an unguarded
    one is the defect this file exists to catch — the shape, occurring *inside*
    a single method rather than across two.

    So each runner call is checked against the statements that actually precede
    it: earlier in its own block, and earlier in every enclosing block. That is
    an approximation of dominance and deliberately a conservative one — it does
    not follow `else` branches or loops back, so it can only over-report, which
    is the safe direction for a guard.
    """
    offenders: list[str] = []

    def walk(body, guarded_above: bool):
        guarded = guarded_above
        for stmt in body:
            names = _surface_names(stmt)
            hit = sorted(names & runners)
            if hit and not (guarded or names & GUARDING_FACTORIES):
                # The guard may be applied within this same statement (rare, but
                # `x = f(guard(vm))` is legal); only report if it is not.
                if GUARD not in names:
                    offenders.append(f"line {stmt.lineno}: {', '.join(hit)}")
            if GUARD in names or names & GUARDING_FACTORIES:
                guarded = True
            for field in ("body", "orelse", "finalbody"):
                nested = getattr(stmt, field, None)
                if isinstance(nested, list) and nested and isinstance(nested[0], ast.stmt):
                    walk(nested, guarded)
            for handler in getattr(stmt, "handlers", []) or []:
                walk(handler.body, guarded)

    walk(fn.body, False)
    return offenders


class TheGuardIsTheOnlyWayThroughTests(unittest.TestCase):
    # closes: #754
    def test_every_code_running_route_applies_the_policies(self):
        tree = _tree()
        runners = _runner_names(tree)
        offenders = []
        checked = 0
        for fn in _service(tree).body:
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if fn.name in DELEGATES:
                continue
            called = _called_names(fn)
            if not (called & runners):
                continue
            checked += 1
            for where in _unguarded_runner_calls(fn, runners):
                offenders.append(f"{fn.name}, {where}")

        self.assertGreater(
            checked, 5,
            "the scan found almost no code-running routes, which means it is "
            "matching the wrong names rather than that the server has none",
        )
        self.assertEqual(
            [], offenders,
            f"{len(offenders)} RuntimeService route(s) run submitted code without "
            f"{GUARD}. That VM is unconfined -- it keeps the permissive defaults "
            f"of the runner path, whatever the operator passed to `nodus serve`.",
        )

    # closes: #754
    def test_the_delegate_exemption_is_real(self):
        """`DELEGATES` is an escape hatch, so it has to be checked rather than
        trusted: each name must actually call a guarded method of this class."""
        tree = _tree()
        service = _service(tree)
        by_name = {
            fn.name: fn for fn in service.body
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for name in DELEGATES:
            with self.subTest(delegate=name):
                self.assertIn(name, by_name, "exempting a method that does not exist")
                called = _called_names(by_name[name])
                guarded_targets = {
                    other for other in called
                    if other in by_name and (
                        GUARD in _called_names(by_name[other])
                        or _called_names(by_name[other]) & GUARDING_FACTORIES
                    )
                }
                self.assertTrue(
                    guarded_targets,
                    f"{name} is exempt but calls nothing that applies the guard",
                )

    # closes: #754
    def test_the_guarding_factory_actually_guards(self):
        tree = _tree()
        service = _service(tree)
        for name in GUARDING_FACTORIES:
            fn = next(
                (f for f in service.body
                 if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and f.name == name),
                None,
            )
            with self.subTest(factory=name):
                self.assertIsNotNone(fn, f"{name} no longer exists")
                self.assertIn(
                    GUARD, _called_names(fn),
                    f"{name} is trusted to apply the guard and does not",
                )


if __name__ == "__main__":
    unittest.main()
