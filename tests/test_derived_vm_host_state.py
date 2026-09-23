"""A VM derived from another inherits the host state it works for (#868).

`test_vm_authority_inheritance.py` covers what a derived VM may *do*. This covers
who it is working *for* — the tool registry, the effect store, the agent registry,
the workflow runner — which was the other half of the same question and was
answered separately at every derivation site.

The four sites carried four different hand-written lists, and they had drifted:

| Site | Host state it copied, before |
|---|---|
| `NodusModule.invoke_function` | 7 attributes |
| tool handler child VM | 6 — `session_id` had been left off |
| `VM._resume_target_vm` | 2 |
| DAP `evaluate` | 0 |

**The failure is silent in every case, because every consumer has a plausible
fallback.** `tool.call` against an empty registry returns an error *value* that a
step can return as success — the reported symptom, a `publish` step reporting
`published: true` with no file written. `agent_call` with no `agent_registry`
reaches the process-global one, which `services/agent_runtime.py` calls "a
cross-tenant capability leak rather than merely shared state".

Two things these tests are shaped to avoid, both of which produced false greens
while this was being written:

- **Comparing a default to a default.** The first survey of what the resume child
  lost reported six attributes as inherited that simply had `None` on both sides.
  `_loaded_parent` below sets every value non-default for that reason.
- **A source assertion that cannot fail.** Deleting `input_fn` from
  `AUTHORITY_ATTRIBUTES` left the authority suite green, because its comparison
  iterates that same tuple — removing a name removes the assertion with it. The
  list-driven test here has the same shape, so the three attributes that actually
  bite are *also* asserted by name.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus.runtime.capability import (  # noqa: E402
    HOST_STATE_ATTRIBUTES,
    inherit_host_state,
)
from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.services.agent_runtime import register_agent  # noqa: E402
from nodus.vm.vm import VM  # noqa: E402

PARKED = '''
workflow w {
    step a { return workflow_wait("go", "k1", {}) }
    step b after a { return {"done": true} }
}
'''


class _MarkerEffectStore:
    """Distinguishable from the `InMemoryEffectStore` a fresh VM builds itself."""

    def get(self, key):
        return None

    def put(self, key, value):
        return True


def _loaded_parent() -> VM:
    """A VM whose host state is non-default in every respect.

    Every value differs from what `VM.__init__` would produce, so an attribute
    that is not inherited shows up as a difference rather than coincidentally
    matching. This is the lesson from the survey that found the bug: six rows
    read "inherited" because both sides were `None`.
    """
    vm = VM([1], {}, code_locs=[(None, 0, 0)], source_path="parent.nd")
    vm.effect_store = _MarkerEffectStore()
    vm.tool_registry = {"host.echo": {"name": "host.echo", "handler": lambda a: a}}
    vm.agent_registry = {"host.agent": {"handler": lambda p: p}}
    vm.workflow_runner = object()
    vm.budget_meters = {"tokens": lambda: 1.0}
    vm.worker_dispatcher = object()
    vm.circuit_breakers = {"cb": object()}
    vm.on_error = lambda *a, **k: None
    vm.agent_timeout_ms = 4321
    vm.coroutine_timeout_ms = 1234
    vm.trace_id = "trace-marker"
    vm.session_id = "session-marker"
    vm.trace_errors = True
    return vm


def _host_state(vm) -> dict:
    return {name: getattr(vm, name, "<missing>") for name in HOST_STATE_ATTRIBUTES}


def _assert_inherited(case, parent, child):
    lost = {
        name: (value, _host_state(child)[name])
        for name, value in _host_state(parent).items()
        if _host_state(child)[name] is not value
    }
    case.assertEqual(
        lost, {},
        "host state lost when deriving a VM: "
        + ", ".join(f"{n}: parent={p!r} child={c!r}" for n, (p, c) in lost.items()),
    )


# closes: #868
class TheResumeChildInheritsHostState(unittest.TestCase):
    """`_resume_target_vm` was the site the issue was reported against."""

    def test_the_resume_child_inherits_every_host_state_attribute(self):
        parent = _loaded_parent()
        child = parent._resume_target_vm("g_not_registered_anywhere")
        self.assertIsNot(child, parent, "expected a derived VM for this case")
        _assert_inherited(self, parent, child)

    def test_the_tool_registry_specifically_survives(self):
        # Named on its own because the list-driven test above iterates
        # HOST_STATE_ATTRIBUTES: deleting a name removes the propagation and the
        # comparison together, so it cannot fail on its own.
        parent = _loaded_parent()
        child = parent._resume_target_vm("g_not_registered_anywhere")
        self.assertIn("host.echo", child.tool_registry)

    def test_the_effect_store_specifically_survives(self):
        parent = _loaded_parent()
        child = parent._resume_target_vm("g_not_registered_anywhere")
        self.assertIs(child.effect_store, parent.effect_store)
        self.assertNotIsInstance(child.effect_store, type(VM([], {}).effect_store))

    def test_the_agent_registry_specifically_survives(self):
        parent = _loaded_parent()
        child = parent._resume_target_vm("g_not_registered_anywhere")
        self.assertIs(child.agent_registry, parent.agent_registry)

    def test_the_registry_and_its_lock_travel_together(self):
        # One dict guarded by two different locks is a race. If the dict is
        # shared the lock has to be, or neither.
        parent = _loaded_parent()
        child = parent._resume_target_vm("g_not_registered_anywhere")
        self.assertIs(child.tool_registry, parent.tool_registry)
        self.assertIs(child._tool_registry_lock, parent._tool_registry_lock)


# closes: #868
class EveryDerivationSiteCarriesBoth(unittest.TestCase):
    """A fifth site cannot inherit authority and forget the rest.

    Asserted on the source rather than the behaviour: a behaviour test passes on
    whichever site is already correct, and the defect here IS a site nobody
    taught.
    """

    SITES = (
        "src/nodus/vm/vm.py",
        "src/nodus/runtime/module.py",
        "src/nodus/builtins/tool_module.py",
        "src/nodus/dap/server.py",
    )

    def _read(self, relative):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, relative), "r", encoding="utf-8") as handle:
            return handle.read()

    def test_every_inherit_authority_call_site_also_inherits_host_state(self):
        for relative in self.SITES:
            source = self._read(relative)
            authority = source.count("inherit_authority(")
            host_state = source.count("inherit_host_state(")
            # Subtract the import lines, which name both without calling either.
            self.assertGreaterEqual(
                host_state, authority - source.count("import inherit_authority"),
                f"{relative} derives a VM and inherits authority but not host "
                f"state: {authority} inherit_authority( vs {host_state} "
                f"inherit_host_state(",
            )

    def test_no_site_hand_copies_an_attribute_the_shared_list_owns(self):
        # The drift this replaces: `tool_module.py` copied six of `module.py`'s
        # seven. A site that goes back to assigning one by hand is how the lists
        # diverge again.
        owned = ("effect_store", "memory_store", "circuit_breakers", "agent_registry")
        for relative in self.SITES:
            source = self._read(relative)
            for attribute in owned:
                for spelling in (f"vm.{attribute} = ", f"child_vm.{attribute} = ",
                                 f"child.{attribute} = "):
                    self.assertNotIn(
                        spelling, source,
                        f"{relative} assigns {attribute} by hand; "
                        f"inherit_host_state owns it",
                    )


# closes: #868
class TheReportedSymptom(unittest.TestCase):
    """End to end: a tool call in a resumed step reaches the host handler.

    This is the case that was reported — the run finished `ok` with every step
    `completed` while the handler had never been called.
    """

    SOURCE = '''
import "std:tool" as tool
workflow w {
    step a { return workflow_wait("go", "k1", {}) }
    step b after a {
        let r = tool.call("host.echo", {"x": "hi"})
        return {"kind": type(r), "value": str(r)}
    }
}
'''

    def _runtime(self, calls, captured):
        runtime = NodusRuntime(timeout_ms=None)
        runtime.register_function(
            "_cap", lambda r: captured.__setitem__("r", r), arity=1)
        runtime.tool_registry.register({
            "name": "host.echo", "description": "echo", "schema": {},
            "handler": lambda args: calls.append(args) or {"echo": args},
        })
        return runtime

    def test_a_resumed_step_reaches_the_host_tool_handler(self):
        calls: list = []
        captured: dict = {}
        started = self._runtime(calls, captured)
        started.run_source(self.SOURCE + "\n_cap(run_workflow(w))\n")
        graph_id = started._to_host_value(captured["r"])["graph_id"]
        self.assertEqual(started._to_host_value(captured["r"])["status"], "waiting")

        # "Another process": a second runtime primes a VM with the same
        # declarations, so `vm.code` is non-empty and the resume diverts.
        resumer = self._runtime(calls, captured)
        resumer.run_source(self.SOURCE)
        vm = resumer._get_active_vm()
        self.assertIn("host.echo", vm.tool_registry)

        result = resumer._to_host_value(
            vm.builtin_resume_workflow(graph_id, None, {"ok": True}))
        step = result["steps"]["b"]
        self.assertEqual(
            step["kind"], "record",
            f"tool.call in a resumed step returned {step['kind']}: {step['value']}",
        )
        self.assertEqual(len(calls), 1, "the host handler was never called")


# closes: #868
class ModuleFunctionsSeeTheirTenantsAgents(unittest.TestCase):
    """The instance found by asking what else had this shape.

    `agent_registry` is read straight off the VM, so a module function's child VM
    resolved `agent_call` against the **process-global** registry while the same
    call at top level resolved against the runtime's own — #185's tenant
    isolation, undone by crossing a module boundary.
    """

    @classmethod
    def setUpClass(cls):
        register_agent("host.agent", lambda p: {"who": "GLOBAL"}, description="global")

    def _tenant_runtime(self, workdir, captured):
        runtime = NodusRuntime(
            agent_registry={}, allowed_paths=[workdir], timeout_ms=None)
        runtime.register_agent("host.agent", lambda p: {"who": "TENANT"})
        runtime.register_function(
            "_cap", lambda r: captured.__setitem__("r", r), arity=1)
        return runtime

    def test_a_module_function_resolves_its_runtimes_agent_registry(self):
        with tempfile.TemporaryDirectory() as workdir:
            with open(os.path.join(workdir, "helper.nd"), "w", encoding="utf-8") as h:
                h.write('export fn ask() {\n    return agent_call("host.agent", {})\n}\n')
            cwd = os.getcwd()
            os.chdir(workdir)
            try:
                captured: dict = {}
                runtime = self._tenant_runtime(workdir, captured)
                # The control and the case in one program: if these disagree, the
                # module boundary is resolving against a different registry.
                runtime.run_source('_cap(agent_call("host.agent", {}))')
                top_level = runtime._to_host_value(captured["r"])["result"]

                captured.clear()
                runtime = self._tenant_runtime(workdir, captured)
                runtime.run_source('import "./helper.nd" as helper\n_cap(helper.ask())')
                in_module = runtime._to_host_value(captured["r"])["result"]
            finally:
                os.chdir(cwd)

        self.assertEqual(top_level, {"who": "TENANT"}, "control: top level")
        self.assertEqual(
            in_module, {"who": "TENANT"},
            "a module function reached the process-global agent registry instead "
            "of its runtime's own",
        )


# closes: #868
class InheritHostStateItself(unittest.TestCase):
    def test_a_none_on_the_parent_does_not_clobber_a_usable_default(self):
        # A bare VM has no `workflow_runner` and is meant to fall through to the
        # process-global one; assigning the parent's None must not replace a
        # child's real object either.
        parent = VM([], {})
        parent.workflow_runner = None
        child = VM([], {})
        sentinel = object()
        child.workflow_runner = sentinel
        inherit_host_state(child, parent)
        self.assertIs(child.workflow_runner, sentinel)

    def test_a_missing_parent_is_a_no_op(self):
        child = VM([], {})
        before = _host_state(child)
        inherit_host_state(child, None)
        self.assertEqual(_host_state(child), before)


if __name__ == "__main__":
    unittest.main()
