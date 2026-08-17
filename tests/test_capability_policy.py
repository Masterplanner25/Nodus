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
    ApprovalChannel,
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
class TheDefaultIsDenyTests(unittest.TestCase):
    """Stage 5: capabilities are refused unless granted.

    Until this, a bare `NodusRuntime()` could shell out, open sockets and read
    the process environment. Audit 03: *"the chokepoint is built; the door is
    propped open by registering subprocess and http by default."* The door is
    shut. `nodus run` is deliberately unaffected — see
    `TheCliIsNotSandboxedByDefaultTests`.
    """

    def test_a_bare_runtime_refuses_subprocess(self):
        result, _denials = _run(SUBPROCESS_CALL)
        self.assertFalse(result.get("ok"), result)

    def test_the_message_says_how_to_grant_it(self):
        # With deny-by-default most readers never set the flag to False
        # themselves, so "allow_subprocess=False" as an explanation is useless.
        result, _ = _run(SUBPROCESS_CALL)
        self.assertTrue(
            any("allow_subprocess=True" in m for m in _errors(result)), _errors(result)
        )

    def test_granting_it_explicitly_works(self):
        result, denials = _run(SUBPROCESS_CALL, allow_subprocess=True)
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
        result, denials = _run(SUBPROCESS_CALL, allow_subprocess=True,
                               capability_policy=DenyList(NETWORK))
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

        allowed, _ = _run(SUBPROCESS_CALL, allow_subprocess=True,
                          capability_policy=OnlyEcho())
        self.assertTrue(allowed.get("ok"), allowed)

        source = 'import "std:subprocess" as sp\nlet r = sp.run(["hostname"])\nprint("ran")\n'
        refused, denials = _run(source, allow_subprocess=True,
                                capability_policy=OnlyEcho())
        self.assertFalse(refused.get("ok"), refused)
        self.assertIn("only echo is permitted", denials[0]["reason"])


# closes: #405
class TheFloorHoldsRegardlessTests(unittest.TestCase):
    """Consulted before any policy, and it can only restrict.

    Built now because all three systems in `CAPABILITY_POLICY_DESIGN.md` added a
    bypass mode under pressure and retrofitted a floor beneath it afterwards.
    Nodus has no bypass mode yet, so building the floor first is free.
    """

    FORGE = (
        'import "std:fs" as fs\n'
        'fs.write(".nodus/x.json", "forged")\n'
        'print("wrote")\n'
    )

    def _forge(self, **kwargs):
        with _Sandbox():
            os.makedirs(".nodus", exist_ok=True)
            runtime = NodusRuntime(timeout_ms=None, **kwargs)
            return runtime.run_source(self.FORGE, filename="t.nd")

    def test_a_guest_cannot_write_into_the_runtimes_own_state(self):
        # Verified before building this: with defaults, a script overwrote
        # .nodus/workflow_framework/runs/<id>.json with {"forged": true} and the
        # run reported success. That is forging durable run records.
        result = self._forge()
        self.assertFalse(result.get("ok"), result)

    def test_the_floor_beats_a_policy_that_allows_everything(self):
        class AllowEverything(CapabilityPolicy):
            def check(self, request):
                return CapabilityDecision.allow()

        result = self._forge(capability_policy=AllowEverything())
        self.assertFalse(
            result.get("ok"),
            "a permissive policy overrode the floor; the floor is not a floor",
        )

    def test_a_floor_cannot_grant_what_a_policy_refuses(self):
        # Structural: `Floor.check` returns a decision to impose or None to
        # abstain, and there is no allow to return. A floor that could grant
        # would override a refusal, which is the opposite of a floor.
        from nodus.runtime.capability import Floor

        self.assertIsNone(Floor().check(CapabilityRequest(SUBPROCESS, "t", "builtin")))

    def test_ordinary_writes_are_untouched(self):
        with _Sandbox():
            result = NodusRuntime(timeout_ms=None).run_source(
                'import "std:fs" as fs\n'
                'fs.write("ok.txt", "hi")\n'
                'print("wrote")\n',
                filename="t.nd",
            )
        self.assertTrue(result.get("ok"), result)

    def test_a_path_merely_containing_the_word_is_not_caught(self):
        from nodus.runtime.capability import NodusStateFloor

        floor = NodusStateFloor()
        innocent = CapabilityRequest("fs.write", "write_file", "builtin", ("my.nodus-notes.txt",))
        self.assertIsNone(floor.check(innocent))
        traversal = CapabilityRequest("fs.write", "write_file", "builtin", ("../.nodus/runs/x",))
        self.assertIsNotNone(floor.check(traversal))


# closes: #405
class AskNeedsSomebodyToAskTests(unittest.TestCase):
    """An unanswered question is not permission."""

    SUBPROCESS_CALL = SUBPROCESS_CALL

    class _Ask(CapabilityPolicy):
        def check(self, request):
            return CapabilityDecision.ask("needs a human")

    def _run_with(self, channel):
        with _Sandbox():
            runtime = NodusRuntime(timeout_ms=None, allow_subprocess=True,
                                   capability_policy=self._Ask())
            runtime.approval_channel = channel
            return runtime.run_source(SUBPROCESS_CALL, filename="t.nd")

    def test_ask_with_no_channel_is_denied(self):
        # Codex reaches the same answer: Prompt under AskForApproval::Never
        # becomes Forbidden, not "run anyway".
        result = self._run_with(None)
        self.assertFalse(result.get("ok"), result)
        self.assertTrue(
            any("no approval channel" in m for m in _errors(result)), _errors(result)
        )

    def test_ask_with_an_approver_proceeds(self):
        class Yes(ApprovalChannel):
            def request(self, request, reason):
                return True

        result = self._run_with(Yes())
        self.assertTrue(result.get("ok"), result)
        self.assertIn("ran", result["stdout"])

    def test_ask_with_a_refuser_is_denied(self):
        class No(ApprovalChannel):
            def request(self, request, reason):
                return False

        self.assertFalse(self._run_with(No()).get("ok"))

    def test_the_approver_is_told_what_it_is_approving(self):
        seen = []

        class Recording(ApprovalChannel):
            def request(self, request, reason):
                seen.append((request.capability, request.target, reason))
                return True

        self._run_with(Recording())
        self.assertEqual(seen[0][0], SUBPROCESS)
        self.assertEqual(seen[0][1], "subprocess_run")
        self.assertEqual(seen[0][2], "needs a human")

    def test_ask_is_not_allowed(self):
        # `.allowed` must mean permission, so `ask` is not it.
        self.assertFalse(CapabilityDecision.ask("x").allowed)
        self.assertTrue(CapabilityDecision.allow().allowed)
        self.assertFalse(CapabilityDecision.deny("x").allowed)


# closes: #405
class TheCliIsNotSandboxedByDefaultTests(unittest.TestCase):
    """`nodus run` is deliberately unaffected by deny-by-default.

    The domain this protects is *work you did not fully author* — which is the
    embedding case. A developer running a script they just wrote is not that, and
    a CLI that refused to shell out would be like `python` refusing to open
    sockets. The two paths are genuinely separate: `nodus run` builds a `VM`
    directly and never constructs a `NodusRuntime`.

    Pinned as a test because it is a design decision, not an oversight, and the
    obvious "fix" is to make them consistent.
    """

    def test_nodus_run_can_still_shell_out(self):
        import subprocess

        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "t.nd")
            with open(script, "w", encoding="utf-8") as handle:
                handle.write(
                    'import "std:subprocess" as sp\n'
                    'let r = sp.run(["echo", "hi"])\n'
                    'print("ran")\n'
                )
            env = dict(os.environ)
            env["PYTHONPATH"] = os.path.join(repo, "src")
            proc = subprocess.run(
                [sys.executable, os.path.join(repo, "nodus.py"), "run", script],
                cwd=td, env=env, capture_output=True, text=True, timeout=120,
            )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("ran", proc.stdout)

    def test_the_cli_does_not_build_a_nodus_runtime(self):
        # The separation is what makes the split possible rather than a special
        # case; if the CLI ever routed through NodusRuntime this would silently
        # sandbox every script.
        import inspect

        from nodus.cli import cli

        source = inspect.getsource(cli)
        self.assertNotIn("NodusRuntime(", source)


if __name__ == "__main__":
    unittest.main()
