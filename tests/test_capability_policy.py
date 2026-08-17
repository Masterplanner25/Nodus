"""Capability policy at the two host chokepoints (#405).

All three external architecture audits identified using this boundary as the
highest-leverage change available. This is stages 1–2 of the staging in
`docs/governance/CAPABILITY_POLICY_DESIGN.md`: a policy consulted at both
chokepoints, denials recorded on the event bus, and capability metadata on
`register_function`. The three-valued cascade, attenuation and deny-by-default
are deliberately not here.

Two things these tests exist to pin:

1. **Both chokepoints, not one.** The design document stages builtins fourth,
   after host functions. Measured, that ordering covers nothing anyone cares
   about: `subprocess_run`, `http_get` and `env_get` are *builtins*.
2. **Authority is not shed by crossing a boundary.** The first working version of
   this failed exactly one case — `import "std:subprocess"` runs on a child VM,
   which did not inherit the policy, so the documented way to call subprocess
   bypassed the jail entirely.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus.runtime.capability import (  # noqa: E402
    ALL_CAPABILITIES,
    BUILTIN_CAPABILITIES,
    ENV,
    NETWORK,
    SUBPROCESS,
    CapabilityDecision,
    CapabilityPolicy,
    CapabilityRequest,
    DenyList,
)
from nodus.runtime.embedding import NodusRuntime  # noqa: E402


class _Sandbox:
    def __enter__(self):
        self._cwd = os.getcwd()
        self._td = tempfile.TemporaryDirectory()
        os.chdir(self._td.__enter__())
        return self

    def __exit__(self, *exc):
        os.chdir(self._cwd)
        return self._td.__exit__(*exc)


def _run(source, **kwargs):
    with _Sandbox():
        runtime = NodusRuntime(timeout_ms=None, **kwargs)
        result = runtime.run_source(source, filename="t.nd")
        events = [
            e.data for e in runtime._last_vm.event_bus.events()
            if e.type == "capability_denied"
        ]
        return result, events


def _errors(result):
    return [e.get("message") for e in (result.get("errors") or [])]


SUBPROCESS_CALL = 'import "std:subprocess" as sp\nlet r = sp.run(["echo", "hi"])\nprint("ran")\n'


# closes: #405
class NoPolicyChangesNothingTests(unittest.TestCase):
    """The default must be indistinguishable from before, or this is not additive."""

    def test_a_bare_runtime_still_runs_subprocess(self):
        result, denials = _run(SUBPROCESS_CALL)
        self.assertTrue(result.get("ok"), result)
        self.assertIn("ran", result["stdout"])
        self.assertEqual(denials, [])

    def test_a_host_function_without_a_declared_capability_is_permitted(self):
        with _Sandbox():
            runtime = NodusRuntime(timeout_ms=None, capability_policy=DenyList(NETWORK))
            runtime.register_function("safe", lambda: "fine", arity=0)
            result = runtime.run_source("print(safe())", filename="t.nd")
        self.assertTrue(result.get("ok"), result)
        self.assertIn("fine", result["stdout"])


# closes: #405
class TheBuiltinChokepointIsCoveredTests(unittest.TestCase):
    """Covering only host functions would miss every capability that matters."""

    def test_denying_subprocess_blocks_the_stdlib_module_path(self):
        # `import "std:subprocess"` is the documented way to call it, and it runs
        # on a child VM. A policy that did not cross that boundary would be
        # bypassed by the only call anyone makes.
        result, denials = _run(SUBPROCESS_CALL, capability_policy=DenyList(SUBPROCESS))
        self.assertFalse(result.get("ok"), result)
        self.assertTrue(any("subprocess" in m for m in _errors(result)), _errors(result))
        self.assertEqual(len(denials), 1)
        self.assertEqual(denials[0]["capability"], SUBPROCESS)
        self.assertEqual(denials[0]["kind"], "builtin")
        self.assertEqual(denials[0]["target"], "subprocess_run")

    def test_denial_is_per_capability_not_all_or_nothing(self):
        # Denying network must leave subprocess working — the pre-existing
        # mechanism is three coarse booleans fixed at construction.
        result, denials = _run(SUBPROCESS_CALL, capability_policy=DenyList(NETWORK))
        self.assertTrue(result.get("ok"), result)
        self.assertIn("ran", result["stdout"])
        self.assertEqual(denials, [])

    def test_denying_env_blocks_env_reads(self):
        source = 'import "std:env" as env\nlet v = env.get("PATH")\nprint("read")\n'
        result, denials = _run(source, capability_policy=DenyList(ENV))
        self.assertFalse(result.get("ok"), result)
        self.assertEqual(denials[0]["capability"], ENV)

    def test_builtins_carrying_no_authority_are_never_consulted(self):
        # Both a design and a performance property: `len` and `push` do not pay
        # a policy lookup, and the capability surface stays enumerable.
        for name in ("len", "push", "str", "print"):
            with self.subTest(builtin=name):
                self.assertNotIn(name, BUILTIN_CAPABILITIES)

    def test_every_declared_capability_is_a_known_one(self):
        unknown = set(BUILTIN_CAPABILITIES.values()) - ALL_CAPABILITIES
        self.assertEqual(unknown, set())


# closes: #405
class TheHostFunctionChokepointIsCoveredTests(unittest.TestCase):
    def test_a_declared_capability_is_enforced(self):
        with _Sandbox():
            runtime = NodusRuntime(timeout_ms=None, capability_policy=DenyList(NETWORK))
            runtime.register_function("fetch", lambda u: "body", arity=1, requires=NETWORK)
            result = runtime.run_source('print(fetch("http://x"))', filename="t.nd")
            denials = [
                e.data for e in runtime._last_vm.event_bus.events()
                if e.type == "capability_denied"
            ]
        self.assertFalse(result.get("ok"), result)
        self.assertEqual(denials[0]["kind"], "host_function")
        self.assertEqual(denials[0]["target"], "fetch")

    def test_an_unknown_capability_is_rejected_at_registration(self):
        # A typo must not silently grant what the caller believed they restricted.
        runtime = NodusRuntime(timeout_ms=None)
        with self.assertRaises(ValueError) as ctx:
            runtime.register_function("x", lambda: 1, arity=0, requires="netwrok")
        self.assertIn("netwrok", str(ctx.exception))

    def test_denylist_rejects_an_unknown_capability(self):
        with self.assertRaises(ValueError):
            DenyList("nonsense")


# closes: #405
class DenialsAreRecordedTests(unittest.TestCase):
    """A denial that is only raised cannot be audited."""

    def test_the_pre_existing_construction_flag_now_emits_an_event(self):
        # `allow_subprocess=False` is the oldest capability mechanism here and
        # emitted nothing structured until #405 — only a generic runtime_error.
        result, denials = _run(SUBPROCESS_CALL, allow_subprocess=False)
        self.assertFalse(result.get("ok"), result)
        self.assertEqual(len(denials), 1)
        self.assertEqual(denials[0]["capability"], SUBPROCESS)

    def test_the_event_carries_enough_to_act_on(self):
        _result, denials = _run(SUBPROCESS_CALL, capability_policy=DenyList(SUBPROCESS))
        for key in ("capability", "target", "kind", "reason"):
            self.assertIn(key, denials[0])

    def test_an_exploding_event_bus_does_not_break_the_run(self):
        # An audit sink must never be the thing that breaks the run it audits.
        from nodus.runtime.capability import emit_denied

        class Boom:
            def emit_event(self, *a, **k):
                raise RuntimeError("sink is down")

        emit_denied(Boom(), CapabilityRequest(SUBPROCESS, "t", "builtin"), "no")


# closes: #405
class PolicySeesTheCallNotJustTheCapabilityTests(unittest.TestCase):
    """`http_get("https://internal/…")` is a different request from a public one."""

    def test_the_request_carries_target_kind_and_args(self):
        seen = []

        class Recording(CapabilityPolicy):
            def check(self, request):
                seen.append(request)
                return CapabilityDecision.allow()

        _run(SUBPROCESS_CALL, capability_policy=Recording())
        self.assertTrue(seen, "policy was never consulted")
        request = seen[0]
        self.assertEqual(request.capability, SUBPROCESS)
        self.assertEqual(request.target, "subprocess_run")
        self.assertEqual(request.kind, "builtin")
        self.assertTrue(request.args, "policy cannot decide on *what* without args")

    def test_a_policy_can_allow_one_call_and_refuse_another(self):
        class OnlyEcho(CapabilityPolicy):
            def check(self, request):
                argv = request.args[0] if request.args else None
                if isinstance(argv, list) and argv and argv[0] == "echo":
                    return CapabilityDecision.allow()
                return CapabilityDecision.deny("only echo is permitted")

        allowed, _ = _run(SUBPROCESS_CALL, capability_policy=OnlyEcho())
        self.assertTrue(allowed.get("ok"), allowed)

        source = 'import "std:subprocess" as sp\nlet r = sp.run(["hostname"])\nprint("ran")\n'
        refused, denials = _run(source, capability_policy=OnlyEcho())
        self.assertFalse(refused.get("ok"), refused)
        self.assertIn("only echo is permitted", denials[0]["reason"])


if __name__ == "__main__":
    unittest.main()
