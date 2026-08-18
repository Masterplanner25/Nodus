"""Two runtimes in one process do not share guest-writable state (#185).

`GLOBAL_MEMORY_STORE` was bound at import and shared by every `NodusRuntime`, so
in a multi-tenant host — the nodus-sdk FastAPI bridge, say — one request's script
could read another's. Verified before the fix:

    rt_a.run_source('memory_put("secret", "password123")')
    rt_b.run_source('print(memory_get("secret"))')   -> password123

**Memory and agents are treated differently, deliberately.** The issue groups them
as one defect ("similar process-level scope"); they are not the same:

- A guest script *writes* memory — `memory_put` is a builtin — so a shared store
  is a channel one tenant's script can push data through to another's.
- A guest cannot register an agent at all. The only agent builtins are
  `agent_call`, `agent_available` and `agent_describe`; registration is host-only,
  from Python. A shared registry therefore holds what the *host* put there.

So memory is isolated by default and agents are not. Isolating agents too would
break the ordinary `register_agent(...)` then `run_source(...)` flow — it broke 11
existing tests when tried — to prevent a leak guests have no way to cause.
"""

import unittest

from nodus.runtime.embedding import NodusRuntime
from nodus.services.agent_runtime import register_agent, unregister_agent
from nodus.services.memory_runtime import GLOBAL_MEMORY_STORE, MemoryStore
from nodus.vm.vm import VM


def read_back(rt, key="k"):
    return (rt.run_source(f'print(memory_get("{key}"))', filename="t.nd").get("stdout") or "").strip()


class MemoryIsolationTests(unittest.TestCase):
    # closes: #185
    def test_one_runtime_cannot_read_anothers_memory(self):
        a, b = NodusRuntime(timeout_ms=None), NodusRuntime(timeout_ms=None)
        try:
            a.run_source('memory_put("secret", "password123")', filename="a.nd")
            self.assertEqual(read_back(b, "secret"), "nil")
        finally:
            a.shutdown()
            b.shutdown()

    def test_one_runtime_cannot_overwrite_anothers_memory(self):
        """Reading is the headline; clobbering is the quieter half."""
        a, b = NodusRuntime(timeout_ms=None), NodusRuntime(timeout_ms=None)
        try:
            a.run_source('memory_put("k", "A")', filename="a.nd")
            b.run_source('memory_put("k", "B")', filename="b.nd")
            self.assertEqual(read_back(a), "A")
            self.assertEqual(read_back(b), "B")
        finally:
            a.shutdown()
            b.shutdown()

    def test_a_runtime_still_sees_its_own_memory_across_runs(self):
        """The control that stops 'isolated' becoming 'broken'."""
        rt = NodusRuntime(timeout_ms=None)
        try:
            rt.run_source('memory_put("k", "mine")', filename="t.nd")
            self.assertEqual(read_back(rt), "mine")
        finally:
            rt.shutdown()

    def test_sharing_is_available_when_asked_for_explicitly(self):
        shared = MemoryStore()
        a = NodusRuntime(timeout_ms=None, memory_store=shared)
        b = NodusRuntime(timeout_ms=None, memory_store=shared)
        try:
            a.run_source('memory_put("k", "A")', filename="a.nd")
            self.assertEqual(read_back(b), "A")
        finally:
            a.shutdown()
            b.shutdown()

    def test_share_process_state_restores_the_old_behaviour(self):
        """One word, for a host that was relying on the previous default."""
        a = NodusRuntime(timeout_ms=None, share_process_state=True)
        b = NodusRuntime(timeout_ms=None, share_process_state=True)
        try:
            a.run_source('memory_put("k", "A")', filename="a.nd")
            self.assertEqual(read_back(b), "A")
        finally:
            a.shutdown()
            b.shutdown()

    def test_a_bare_vm_still_uses_the_process_global_store(self):
        """The CLI builds a VM directly and is single-tenant by construction;
        changing its default would be churn without a threat model."""
        self.assertIs(VM([("HALT",)], {}).memory_store, GLOBAL_MEMORY_STORE)


class AgentRegistryTests(unittest.TestCase):
    def setUp(self):
        register_agent("iso.probe", lambda p: {"ok": True})

    def tearDown(self):
        unregister_agent("iso.probe")

    def test_host_registered_agents_remain_visible_by_default(self):
        """`register_agent(...)` then `run_source(...)` is the documented flow and
        must keep working. Isolating agents by default broke 11 existing tests."""
        rt = NodusRuntime(timeout_ms=None)
        try:
            out = rt.run_source('print(agent_available())', filename="t.nd").get("stdout") or ""
            self.assertIn("iso.probe", out)
        finally:
            rt.shutdown()

    def test_a_host_can_still_scope_agents_per_runtime(self):
        """Available for a host that genuinely wants per-tenant agent sets."""
        rt = NodusRuntime(timeout_ms=None, agent_registry={})
        try:
            out = rt.run_source('print(agent_available())', filename="t.nd").get("stdout") or ""
            self.assertNotIn("iso.probe", out)
        finally:
            rt.shutdown()

    def test_a_scoped_registry_also_blocks_calling_the_agent(self):
        """Not merely hidden from the listing."""
        rt = NodusRuntime(timeout_ms=None, agent_registry={})
        try:
            r = rt.run_source('let x = agent_call("iso.probe", {})\nprint(x["ok"])', filename="t.nd")
            self.assertIn("false", (r.get("stdout") or ""))
        finally:
            rt.shutdown()


if __name__ == "__main__":
    unittest.main()
