"""`SyscallSpec.capability` is enforced, not decorative (#478).

Every syscall declared one. `syscall_list()` published it to any host that
asked. `call_syscall` did name-parsing, registry lookup, schema validation and
dispatch -- and never read the field. A policy denying `memory.write` watched
`sys.v1.memory.put` succeed while the registry advertised
`"capability": "memory.write"` on the way past.

A published field named `capability` will be taken for an access-control
decision. That is the whole reason this was worth fixing rather than renaming:
the surface described itself as gated, and a host reading the registry to find
out what it was dealing with was told there was a model where there was none.
"""

import unittest

from nodus.runtime.capability import (
    ALL_CAPABILITIES,
    MEMORY_READ,
    MEMORY_WRITE,
    SYSCALL,
    CapabilityDecision,
    CapabilityPolicy,
)
from nodus.runtime.embedding import NodusRuntime
from nodus.services.syscall_runtime import SYSCALL_REGISTRY, list_syscalls, register_syscall
from nodus_lang_schema.syscalls import SyscallSpec


PUT_THEN_GET = """
fn main() {
    let w = syscall("sys.v1.memory.put", {"key": "secret", "value": "written-anyway"})
    print("put -> \\(w.status)")
    let g = syscall("sys.v1.memory.get", {"key": "secret"})
    print("get -> \\(g.status)")
}
"""


class DenyOne(CapabilityPolicy):
    """Allows everything but one capability, so the gate under test is isolated."""

    def __init__(self, denied: str):
        self.denied = denied
        self.seen: list[str] = []

    def check(self, request):
        self.seen.append(request.capability)
        if request.capability == self.denied:
            return CapabilityDecision.deny(f"{self.denied} denied by test")
        return None


class SpecCapabilityIsEnforcedTests(unittest.TestCase):
    def _run(self, denied: str):
        policy = DenyOne(denied)
        result = NodusRuntime(
            timeout_ms=None, capability_policy=policy
        ).run_source(PUT_THEN_GET)
        return result, policy

    # closes: #478
    def test_denying_memory_write_stops_the_put_syscall(self):
        result, policy = self._run(MEMORY_WRITE)
        self.assertNotIn("put -> ok", result["stdout"])
        self.assertEqual(result["error"]["kind"], "sandbox")
        self.assertIn(MEMORY_WRITE, policy.seen)

    # closes: #478
    def test_the_policy_is_asked_with_the_specs_own_capability(self):
        """Not a blanket `syscall` -- the field on the spec."""
        _result, policy = self._run("nothing-is-denied")
        self.assertEqual(
            policy.seen,
            [SYSCALL, MEMORY_WRITE, SYSCALL, MEMORY_READ],
            "each syscall must reach the policy twice: the builtin gate, then "
            "the spec's own capability",
        )

    def test_denying_syscall_wholesale_still_works(self):
        """The builtin gate (#473) and the spec gate are different intents.

        "No syscalls at all" and "no memory writes, however you spell them" are
        distinct, so both requests exist and the broader one short-circuits.
        """
        result, policy = self._run(SYSCALL)
        self.assertEqual(result["error"]["kind"], "sandbox")
        self.assertEqual(policy.seen, [SYSCALL],
                         "a refusal at the builtin gate must not reach the spec gate")

    def test_a_denial_is_a_sandbox_error_not_an_error_envelope(self):
        """`kind == "sandbox"` is the pinned denial contract (#441-#444).

        Returning `{"status": "error"}` would make a capability refusal
        indistinguishable from a handler that failed, which downstream
        confinement tests classify differently.
        """
        result, _policy = self._run(MEMORY_WRITE)
        self.assertEqual(result["error"]["kind"], "sandbox")
        self.assertIn("Blocked:", result["error"]["message"])

    def test_no_policy_means_syscalls_work_as_before(self):
        result = NodusRuntime(timeout_ms=None).run_source(PUT_THEN_GET)
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("put -> ok", result["stdout"])
        self.assertIn("get -> ok", result["stdout"])


class RegistrationRefusesAnUnenforceableCapabilityTests(unittest.TestCase):
    """Declared-or-refused, at the point of declaration.

    Accepting a capability the policy layer cannot name, then skipping it at
    dispatch, would be this same defect one layer along.
    """

    def tearDown(self):
        SYSCALL_REGISTRY.pop("sys.v1.probe.thing", None)

    # closes: #478
    def test_an_unknown_capability_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            register_syscall(
                SyscallSpec(name="probe.thing", version="v1",
                            capability="billing.charge"),
                lambda payload, vm=None: {},
            )
        message = str(caught.exception)
        self.assertIn("billing.charge", message)
        self.assertIn("known:", message)
        self.assertNotIn("sys.v1.probe.thing", SYSCALL_REGISTRY)

    # closes: #478
    def test_a_missing_capability_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            register_syscall(
                SyscallSpec(name="probe.thing", version="v1"),
                lambda payload, vm=None: {},
            )
        self.assertIn("declares no capability", str(caught.exception))

    def test_a_known_capability_registers(self):
        register_syscall(
            SyscallSpec(name="probe.thing", version="v1", capability=MEMORY_READ),
            lambda payload, vm=None: {},
        )
        self.assertIn("sys.v1.probe.thing", SYSCALL_REGISTRY)


class PublishedSpecsAreEnforceableTests(unittest.TestCase):
    """What `syscall_list()` advertises must be a thing a policy can act on."""

    # closes: #478
    def test_every_published_capability_is_a_declared_one(self):
        for spec in list_syscalls():
            self.assertIn(
                spec["capability"],
                ALL_CAPABILITIES,
                f"{spec['full_name']} advertises {spec['capability']!r}, which "
                f"no policy can name",
            )

    def test_every_registered_syscall_declares_one(self):
        for full_name, entry in SYSCALL_REGISTRY.items():
            self.assertTrue(
                entry["spec"].capability,
                f"{full_name} declares no capability",
            )


if __name__ == "__main__":
    unittest.main()
