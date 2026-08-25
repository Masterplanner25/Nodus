"""Contracts that embedders depend on, pinned so a refactor breaks here first.

Every case in this file came from a downstream report (aindy-runtime,
`docs/runtime/NODUS_HANDOFF_v5.0.0.md` in that repo) describing something it
relies on that nothing in *this* repo asserted. Three kinds appear:

1. **Surfaces that were only reachable by scraping our source.** The gated-builtin
   names had no data export, so a downstream confinement test regexed
   `BuiltinRegistry.register_all`. The 5.0.0 refactor moved those names into the
   `else:` branch; the regex began capturing flag names out of `_denied_reason`
   and reporting them as *leaked builtins*. Discovery broke quietly on our side
   and loudly on theirs.

2. **Properties we were asked to keep.** `NodusRuntime.__init__` taking no
   `**kwargs` and its confinement flags being keyword-only are load-bearing for
   an embedder: with a catch-all, a renamed flag is silently swallowed and the
   guest runs unconfined with every mock-based test still green. Nothing here
   protected either property. Now something does.

3. **A refusal treated as a security boundary.** `register_function` refusing to
   override a builtin is what lets a host install a fail-loud guard under a name
   like `syscall`. If overrides ever became permitted, a guest could redefine the
   guarded name and walk past it. It was documented in a docstring and never
   asserted.

Following `CLAUDE.md`'s rule for this codebase: where a behaviour test would pass
on whichever path already works, assert on the *source* instead.
"""

import inspect
import unittest

from nodus.builtins.registry import BuiltinRegistry
from nodus.runtime.capability import (
    BUILTIN_CAPABILITIES,
    ENV,
    GATED_BUILTIN_NAMES,
    GATED_BUILTINS,
    NETWORK,
    SUBPROCESS,
)
from nodus.runtime.embedding import NodusRuntime


class TestGatedBuiltinData(unittest.TestCase):
    """`GATED_BUILTINS` is the enumerable gated surface, and it is authoritative."""

    def test_groups_cover_the_three_capability_flags(self):
        self.assertEqual(
            set(GATED_BUILTINS), {"allow_env", "allow_network", "allow_subprocess"}
        )
        for flag, group in GATED_BUILTINS.items():
            self.assertEqual(group.flag, flag, "group key must match its flag")
            self.assertTrue(group.names, f"{flag} gates nothing")

    def test_capability_labels_are_the_published_ones(self):
        self.assertEqual(GATED_BUILTINS["allow_env"].capability, ENV)
        self.assertEqual(GATED_BUILTINS["allow_network"].capability, NETWORK)
        self.assertEqual(GATED_BUILTINS["allow_subprocess"].capability, SUBPROCESS)

    def test_the_gated_surface_has_not_silently_changed_size(self):
        """31 builtins: 7 subprocess / 18 network / 6 env.

        Downstream asserts this count directly. It is allowed to change — but not
        by accident, and not without whoever changes it seeing this test.
        """
        self.assertEqual(len(GATED_BUILTINS["allow_subprocess"].names), 7)
        self.assertEqual(len(GATED_BUILTINS["allow_network"].names), 18)
        self.assertEqual(len(GATED_BUILTINS["allow_env"].names), 6)
        self.assertEqual(len(GATED_BUILTIN_NAMES), 31)

    def test_no_name_is_gated_by_two_flags(self):
        seen: dict[str, str] = {}
        for flag, group in GATED_BUILTINS.items():
            for name in group.names:
                self.assertNotIn(
                    name, seen, f"{name} gated by both {seen.get(name)} and {flag}"
                )
                seen[name] = flag

    # closes: #441
    def test_registry_reads_the_data_rather_than_its_own_literals(self):
        """Assert on the source: the gate lists must live in exactly one place.

        A behaviour-only test passes just as well against a registry carrying its
        own duplicate copy of the names — which is what shipped through 5.0.0, and
        which is how `BUILTIN_CAPABILITIES` and the gate list drifted apart by one
        entry without anything noticing.
        """
        src = inspect.getsource(BuiltinRegistry.register_all)
        for name in GATED_BUILTIN_NAMES:
            self.assertNotIn(
                f'"{name}"',
                src,
                f"register_all still hardcodes {name!r}; it must read GATED_BUILTINS",
            )

    def test_policy_gated_builtins_are_also_registration_gated(self):
        """The two lists overlap, with exactly one documented exception.

        `BUILTIN_CAPABILITIES` says what consults the policy at call time;
        `GATED_BUILTINS` says what is never registered when the flag is False.
        `subprocess_shell_quote` is registration-gated but not policy-gated: it is
        string manipulation and runs nothing. Any *other* divergence is a real
        drift — a new `http_*` builtin added to one list and not the other.
        """
        for name, capability in BUILTIN_CAPABILITIES.items():
            if capability not in (SUBPROCESS, NETWORK, ENV):
                # Only three capabilities have a registration-time flag. fs.read
                # and fs.write are path-jailed; tool.invoke, syscall, agent.call
                # and the memory pair (#473) are policy-only — there is no
                # `allow_tools=` switch, and adding one is not implied by making
                # them visible to a policy.
                continue
            self.assertIn(
                name,
                GATED_BUILTIN_NAMES,
                f"{name} consults the policy but is never registration-gated",
            )

        extra = GATED_BUILTIN_NAMES - set(BUILTIN_CAPABILITIES)
        self.assertEqual(
            extra,
            {"subprocess_shell_quote"},
            "registration-gated builtins that do not consult the policy changed",
        )


class TestDenialContract(unittest.TestCase):
    """What a refusal promises. The prose is not the promise; these fields are."""

    def _deny(self, source: str) -> dict:
        rt = NodusRuntime(
            timeout_ms=None,
            allow_subprocess=False,
            allow_network=False,
            allow_env=False,
        )
        try:
            result = rt.run_source(source, filename="t.nd")
        finally:
            rt.shutdown()
        self.assertFalse(result.get("ok"), f"expected a refusal, got: {result!r}")
        return result["error"]

    # closes: #444
    def test_denial_names_the_flag_that_grants_it(self):
        """Downstream matched on the sentence and 5.0.0 rephrased it.

        Four of their confinement tests went red on wording while the guest was
        fully confined. The flag name is the part worth promising — it is what
        makes the error actionable — so it is what this asserts. The wording
        around it is free to change.
        """
        for source, flag in (
            ('subprocess_run(["echo", "hi"])', "allow_subprocess"),
            ('http_get("https://example.com")', "allow_network"),
            ('env_get("PATH")', "allow_env"),
        ):
            with self.subTest(flag=flag):
                self.assertIn(flag, self._deny(source)["message"])

    def test_denial_kind_is_sandbox(self):
        """The other half of the promised contract: `kind`, so an embedder can
        classify a refusal without parsing prose."""
        for source in (
            'subprocess_run(["echo", "hi"])',
            'http_get("https://example.com")',
            'env_get("PATH")',
        ):
            with self.subTest(source=source):
                self.assertEqual(self._deny(source)["kind"], "sandbox")

    def _builtins_with(self, **flags) -> dict:
        rt = NodusRuntime(timeout_ms=None, **flags)
        try:
            rt.run_source("let x = 1i", filename="t.nd")
            vm = rt.active_vm()
            self.assertIsNotNone(vm)
            return dict(vm.builtins)
        finally:
            rt.shutdown()

    def test_every_gated_builtin_is_present_but_blocked_when_denied(self):
        """Present, not absent — a missing name would raise "unknown function",
        which reads as a typo rather than a refusal."""
        builtins = self._builtins_with(
            allow_subprocess=False, allow_network=False, allow_env=False
        )
        for name in GATED_BUILTIN_NAMES:
            self.assertIn(name, builtins, f"{name} not registered as a blocked stub")

    def test_granting_the_flags_registers_the_real_builtins(self):
        """The gate is the flag, not a permanent removal."""
        builtins = self._builtins_with(
            allow_subprocess=True, allow_network=True, allow_env=True
        )
        for name in ("subprocess_run", "http_get", "env_get"):
            self.assertIn(name, builtins)


class TestConstructorShape(unittest.TestCase):
    """Properties an embedder asked us to keep. Nothing protected them before."""

    def test_init_accepts_no_var_keyword(self):
        """No `**kwargs`, so a renamed confinement flag fails closed.

        With a catch-all, `NodusRuntime(allow_subprocess=False)` against a runtime
        that had renamed the flag would be silently swallowed and the guest would
        run unconfined — with every mock-based test on the embedder's side still
        green. Without one it raises TypeError at construction.
        """
        params = inspect.signature(NodusRuntime.__init__).parameters
        var_kw = [p.name for p in params.values() if p.kind is p.VAR_KEYWORD]
        self.assertEqual(var_kw, [], "NodusRuntime.__init__ must not take **kwargs")

    def test_confinement_flags_are_keyword_only(self):
        """Positional acceptance would let an argument reorder change which
        boundary is denied, silently."""
        params = inspect.signature(NodusRuntime.__init__).parameters
        for flag in ("allow_subprocess", "allow_network", "allow_env"):
            self.assertIn(flag, params, f"{flag} is no longer a constructor argument")
            self.assertIs(
                params[flag].kind,
                inspect.Parameter.KEYWORD_ONLY,
                f"{flag} must stay keyword-only",
            )

    def test_confinement_flags_still_default_to_denied(self):
        """The 5.0.0 breaking change, pinned. A default flipping back to True is
        the one regression that would be invisible to a passing suite."""
        params = inspect.signature(NodusRuntime.__init__).parameters
        for flag in ("allow_subprocess", "allow_network", "allow_env"):
            self.assertIs(params[flag].default, False, f"{flag} must default to False")


class TestBuiltinOverrideRefusal(unittest.TestCase):
    """A refusal that is a security boundary downstream, not a convenience check.

    Because a builtin cannot be aliased, a host can install a guard under a name
    the guest might otherwise reach and know the guard is the only thing there. If
    overrides became permitted, a guest could redefine the guarded name and walk
    past it.
    """

    # closes: #443
    def test_register_function_refuses_to_override_a_builtin(self):
        rt = NodusRuntime()
        with self.assertRaises(ValueError) as ctx:
            rt.register_function("syscall", lambda *a: None, arity=1)
        self.assertIn("Cannot override built-in function", str(ctx.exception))
        self.assertIn("syscall", str(ctx.exception))
        rt.shutdown()

    def test_refusal_covers_the_capability_bearing_builtins(self):
        rt = NodusRuntime()
        for name in ("subprocess_run", "http_get", "env_get", "print"):
            with self.assertRaises(ValueError, msg=f"{name} was overridable"):
                rt.register_function(name, lambda *a: None, arity=1)
        rt.shutdown()

    def test_a_non_builtin_name_still_registers(self):
        """The refusal must be about builtins, not about registration generally."""
        rt = NodusRuntime()
        rt.register_function("definitely_not_a_builtin", lambda x: x, arity=1)
        rt.shutdown()


class TestActiveVmAccessor(unittest.TestCase):
    """`active_vm()` is supported; `_get_active_vm()` is retained for pinners."""

    def test_active_vm_is_none_before_the_first_run(self):
        rt = NodusRuntime()
        self.assertIsNone(rt.active_vm())
        rt.shutdown()

    # closes: #442
    def test_active_vm_returns_the_vm_after_a_run(self):
        rt = NodusRuntime()
        rt.run_source("let x = 1i")
        self.assertIsNotNone(rt.active_vm())
        rt.shutdown()

    def test_private_alias_is_retained_and_agrees(self):
        """Downstream pins `_get_active_vm` with a test. Renaming it would break
        them for no gain, so it stays and must not diverge."""
        rt = NodusRuntime()
        rt.run_source("let x = 1i")
        self.assertIs(rt.active_vm(), rt._get_active_vm())
        rt.shutdown()

    def test_active_vm_is_none_after_reset(self):
        rt = NodusRuntime()
        rt.run_source("let x = 1i")
        rt.reset()
        self.assertIsNone(rt.active_vm())
        rt.shutdown()


if __name__ == "__main__":
    unittest.main()
