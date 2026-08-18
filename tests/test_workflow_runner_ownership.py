"""A VM resolves its workflow runner from context, not module state (#390).

Every workflow builtin called `get_default_workflow_runner()` directly, so the VM
had no handle on which runner it belonged to. Any two participants in one process
— a service, an embedded runtime, a test — shared one store, one graph registry
and one sweeper thread, with no way to tell whose run was whose.

Four separate bugs in #376 traced back to that, and each was fixed with a *timing*
defence (`min_idle_ms`, claim-before-rehydrate) against a *structural* problem.
Ownership makes the class unreachable rather than individually patchable: a sweeper
that can only see its own runner's runs cannot adopt someone else's.

Same move as #185 for `memory_store` and `agent_registry`: the VM asks its own
context instead of reaching for a process global. The fallback is kept, so a bare
VM and the CLI behave exactly as before.
"""

import inspect
import unittest

from nodus.runtime.embedding import NodusRuntime
from nodus.vm.vm import VM


class RunnerResolutionTests(unittest.TestCase):
    # closes: #390
    def test_a_bare_vm_falls_back_to_the_process_global_runner(self):
        from nodus_lang_workflow.runner import get_default_workflow_runner

        vm = VM([("HALT",)], {})
        self.assertIsNone(vm.workflow_runner, "a bare VM owns no runner")
        self.assertIs(vm.resolve_workflow_runner(), get_default_workflow_runner())

    def test_a_vm_given_a_runner_uses_it(self):
        sentinel = object()
        vm = VM([("HALT",)], {})
        vm.workflow_runner = sentinel
        self.assertIs(vm.resolve_workflow_runner(), sentinel)

    def test_no_workflow_builtin_reaches_for_the_global_directly(self):
        """Assert on the source: a behaviour test passes as long as *one* call site
        is routed, and there were five. A sixth added later would reintroduce the
        defect silently."""
        source = inspect.getsource(VM)
        # The only permitted mentions are inside the resolver itself.
        resolver = inspect.getsource(VM.resolve_workflow_runner)
        outside = source.replace(resolver, "")
        self.assertNotIn(
            "get_default_workflow_runner()",
            outside,
            "a workflow builtin still resolves the runner from module state; it "
            "must go through VM.resolve_workflow_runner() (#390)",
        )

    def test_a_runtime_can_be_given_its_own_runner(self):
        sentinel = object()
        rt = NodusRuntime(timeout_ms=None, workflow_runner=sentinel)
        try:
            rt.run_source("let x = 1i", filename="t.nd")
            self.assertIs(rt.active_vm().workflow_runner, sentinel)
        finally:
            rt.shutdown()

    def test_a_runtime_without_one_keeps_the_previous_behaviour(self):
        """No embedding API breaks: unowned still means the process-global runner."""
        rt = NodusRuntime(timeout_ms=None)
        try:
            rt.run_source("let x = 1i", filename="t.nd")
            self.assertIsNone(rt.active_vm().workflow_runner)
        finally:
            rt.shutdown()


class ServiceOwnershipTests(unittest.TestCase):
    # closes: #390
    def test_the_service_threads_its_runner_into_every_vm_it_builds(self):
        """`RuntimeService` built VMs in eight places; each now goes through one
        factory, so a new call site cannot forget."""
        from nodus.services.server import RuntimeService

        source = inspect.getsource(RuntimeService)
        self.assertNotIn(
            "VM([], {}, code_locs=[], source_path=None, allowed_paths=self.allowed_paths)".replace(
                "VM([", "VM(["
            ),
            source.replace(inspect.getsource(RuntimeService._new_vm), ""),
            "a RuntimeService method still constructs a VM directly; use _new_vm() "
            "so the service's workflow runner is threaded in (#390)",
        )

    def test_the_factory_attaches_the_services_own_runner(self):
        from nodus.services.server import RuntimeService

        source = inspect.getsource(RuntimeService._new_vm)
        self.assertIn("vm.workflow_runner = self.workflow_runner", source)


if __name__ == "__main__":
    unittest.main()
