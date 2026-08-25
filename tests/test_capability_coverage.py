"""Every builtin is classified: it carries authority, or it is named as not (#473).

The capability vocabulary stopped at the four `NodusRuntime` confinement
switches, so a `CapabilityPolicy` that denied everything denied nothing on the
surfaces that were not sandbox flags -- `tool_call`, `syscall`, `agent_call` and
the whole memory store were invisible to it, and `DenyList("tool.invoke")`
raised `unknown capability`.

The chokepoint was never the problem. `VM.call_builtin` consulted the map
faithfully; the map never grew past the flags. So the test that matters is not
"does a policy see `tool_call`" -- a behaviour test passes the moment one name
is added -- but "is the classification total", which fails for the *next*
builtin nobody classified.

That is the same shape as `TASK_STATUSES` and `FLOW_DECLARATIONS`: name the set
once, and let a test drive off it.
"""

import unittest

from nodus.builtins.nodus_builtins import BUILTIN_NAMES
from nodus.runtime.capability import (
    AGENT_CALL,
    ALL_CAPABILITIES,
    BUILTIN_CAPABILITIES,
    FS_READ,
    MEMORY_READ,
    MEMORY_WRITE,
    NO_AUTHORITY_BUILTIN_NAMES,
    NO_AUTHORITY_BUILTINS,
    SYSCALL,
    TOOL_INVOKE,
    CapabilityDecision,
    CapabilityPolicy,
    DenyList,
)
from nodus.runtime.embedding import NodusRuntime


class RecordingDenyAll(CapabilityPolicy):
    def __init__(self):
        self.seen: list[tuple] = []

    def check(self, request):
        self.seen.append((request.target, request.capability))
        return CapabilityDecision.deny(f"{request.capability} denied by test")


class ClassificationIsTotalTests(unittest.TestCase):
    """The guard that outlives this fix."""

    # closes: #473
    def test_every_builtin_is_classified(self):
        unclassified = (
            set(BUILTIN_NAMES)
            - set(BUILTIN_CAPABILITIES)
            - set(NO_AUTHORITY_BUILTIN_NAMES)
        )
        self.assertEqual(
            unclassified,
            set(),
            "these builtins are neither governed nor declared authority-free; "
            "add each to BUILTIN_CAPABILITIES or to a NO_AUTHORITY_BUILTINS "
            "group with a reason: " + ", ".join(sorted(unclassified)),
        )

    def test_no_builtin_is_classified_both_ways(self):
        both = set(BUILTIN_CAPABILITIES) & set(NO_AUTHORITY_BUILTIN_NAMES)
        self.assertEqual(both, set(), f"contradictory classification: {sorted(both)}")

    def test_no_classification_names_a_builtin_that_does_not_exist(self):
        """A stale name reads as coverage and provides none."""
        phantom = (
            set(BUILTIN_CAPABILITIES) | set(NO_AUTHORITY_BUILTIN_NAMES)
        ) - set(BUILTIN_NAMES)
        self.assertEqual(phantom, set(), f"classified but not a builtin: {sorted(phantom)}")

    def test_no_authority_groups_do_not_repeat_a_name(self):
        flat = [n for names in NO_AUTHORITY_BUILTINS.values() for n in names]
        self.assertEqual(len(flat), len(set(flat)), "a builtin is listed twice")

    def test_every_group_has_a_reason_and_members(self):
        """The dict key *is* the justification; an empty or unnamed group hides one."""
        for reason, names in NO_AUTHORITY_BUILTINS.items():
            self.assertTrue(reason.strip(), "a group has no stated reason")
            self.assertTrue(names, f"group {reason!r} classifies nothing")

    def test_every_capability_used_is_a_declared_one(self):
        unknown = set(BUILTIN_CAPABILITIES.values()) - ALL_CAPABILITIES
        self.assertEqual(unknown, set(), f"undeclared capability in use: {sorted(unknown)}")


class PolicySeesAuthorityBearingSurfacesTests(unittest.TestCase):
    """The four surfaces #473 reported, plus the reads #467 reported."""

    def _first_seen(self, source: str, **kwargs):
        policy = RecordingDenyAll()
        NodusRuntime(timeout_ms=None, capability_policy=policy, **kwargs).run_source(
            source
        )
        return policy.seen[0] if policy.seen else None

    # closes: #473
    def test_memory_write_is_visible(self):
        self.assertEqual(
            self._first_seen('fn main() { memory_put("k", "v") }'),
            ("memory_put", MEMORY_WRITE),
        )

    # closes: #473
    def test_memory_read_is_visible(self):
        self.assertEqual(
            self._first_seen('fn main() { let _ = memory_get("k") }'),
            ("memory_get", MEMORY_READ),
        )

    # closes: #473
    def test_tool_call_is_visible(self):
        self.assertEqual(
            self._first_seen('fn main() { let _ = tool_call("x.y", {}) }'),
            ("tool_call", TOOL_INVOKE),
        )

    # closes: #473
    def test_syscall_is_visible(self):
        self.assertEqual(
            self._first_seen('fn main() { let _ = syscall("sys.v1.memory.get", {"key": "k"}) }'),
            ("syscall", SYSCALL),
        )

    # closes: #473
    def test_agent_call_is_visible(self):
        self.assertEqual(
            self._first_seen('fn main() { let _ = agent_call("a", "p") }'),
            ("agent_call", AGENT_CALL),
        )

    # closes: #473
    def test_a_denied_surface_actually_refuses(self):
        """Seeing the request is half of it; the call must not proceed."""
        policy = RecordingDenyAll()
        result = NodusRuntime(
            timeout_ms=None, capability_policy=policy
        ).run_source("""
fn main() {
    memory_put("k", "leaked-value")
    print("SHOULD NOT REACH")
}
""")
        self.assertNotIn("SHOULD NOT REACH", result["stdout"])
        self.assertEqual(result["error"]["type"], "sandbox")

    def test_denylist_accepts_the_new_names(self):
        """`DenyList("tool.invoke")` raised `unknown capability` before this."""
        for name in (TOOL_INVOKE, SYSCALL, AGENT_CALL, MEMORY_READ, MEMORY_WRITE):
            DenyList(name)  # must not raise


class ActionDslReachesThePolicyTests(unittest.TestCase):
    """`action tool "x"` lowers to `__action_tool`, not to `tool_call`.

    A host cannot shadow either -- `register_function` refusing to override a
    builtin is a deliberate security boundary (#441-#444). So gating one
    spelling and not the other would leave the DSL form uninterposable, which is
    the concrete consequence #473 reported.
    """

    def _seen(self, body: str):
        policy = RecordingDenyAll()
        NodusRuntime(timeout_ms=None, capability_policy=policy).run_source(
            "workflow w { step s { %s\n return 1i } }\n"
            "fn main() { let _ = run_workflow(w) }" % body
        )
        return policy.seen

    # closes: #473
    def test_action_tool_reaches_the_policy(self):
        self.assertEqual(self._seen('action tool "x.y" with { }'),
                         [("__action_tool", TOOL_INVOKE)])

    # closes: #473
    def test_action_agent_reaches_the_policy(self):
        self.assertEqual(self._seen('action agent "a" with { }'),
                         [("__action_agent", AGENT_CALL)])


class FilesystemReadsAreVisibleTests(unittest.TestCase):
    """FS_READ was declared, added to ALL_CAPABILITIES, and attached to nothing.

    Half of #467 -- the other half, a declarative read-only/writable split for
    `allowed_paths`, is a separate change. A policy can now at least *see* a read
    and decide on the path, since `args` reaches it.
    """

    def _first_seen(self, source: str):
        policy = RecordingDenyAll()
        NodusRuntime(timeout_ms=None, capability_policy=policy).run_source(source)
        return policy.seen[0] if policy.seen else None

    def test_read_file_is_visible(self):
        self.assertEqual(
            self._first_seen('fn main() { let _ = read_file("nope.txt") }'),
            ("read_file", FS_READ),
        )

    def test_list_dir_is_visible(self):
        self.assertEqual(
            self._first_seen('fn main() { let _ = list_dir(".") }'),
            ("list_dir", FS_READ),
        )

    def test_the_policy_is_told_which_path(self):
        """A policy must be able to decide on *what*, not merely *whether*."""
        seen = []

        class PathWatching(CapabilityPolicy):
            def check(self, request):
                seen.append(request.args)
                return CapabilityDecision.deny("no")

        NodusRuntime(timeout_ms=None, capability_policy=PathWatching()).run_source(
            'fn main() { let _ = read_file("secrets.txt") }'
        )
        self.assertEqual(seen, [("secrets.txt",)])

    def test_path_string_helpers_stay_ungoverned(self):
        """`path_join` touches no filesystem; gating it would be theatre."""
        for name in ("path_join", "path_basename", "path_dirname", "path_ext",
                     "path_stem", "path_relative", "path_absolute"):
            self.assertNotIn(name, BUILTIN_CAPABILITIES)


class NoPolicyMeansNoChangeTests(unittest.TestCase):
    """This is additive: a runtime with no policy behaves exactly as before."""

    def test_memory_round_trips_without_a_policy(self):
        result = NodusRuntime(timeout_ms=None).run_source("""
fn main() {
    memory_put("k", "v")
    print("got \\(memory_get("k"))")
}
""")
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("got v", result["stdout"])


if __name__ == "__main__":
    unittest.main()
