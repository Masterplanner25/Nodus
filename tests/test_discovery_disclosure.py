"""What a denied guest can still discover, and why that is the decision (#756).

A `CapabilityPolicy` governs **invocation** and not **discovery**. Denying
`agent.call` stops `agent_call`; it does not stop `agent_available()` or
`agent_describe(name)`. That is deliberate, decided in #473, and recorded in
`NO_AUTHORITY_BUILTINS["discovery, not invocation"]`:

    Naming what exists is not reaching it. A denied `tool_call` is still denied
    after `tool_list` names the tool, and hiding the catalogue while leaving the
    call ungoverned would be the wrong half.

This file exists because that argument is exactly right about **authority** and
says nothing about **disclosure**, and the two are different claims. What the
discovery verbs return is not uniform:

- `agent_available()`, `tool_available()`, `tool_has()` return **names** — the
  case the rationale actually argues.
- `agent_describe()`, `tool_describe()` return the **host-authored description
  and parameter schema**.
- `syscall_list()` returns full specs including which **capability** each
  syscall requires — a partial map of the host's own authority model.

None of that is a defect. It is a boundary, and an unstated boundary is how a
host ends up surprised. So the point of this file is that the boundary is
*stated and pinned* rather than emergent: gating any of these later turns it
red, which forces the change to be a decision rather than a tidy-up.

**The mechanism that does close it is `extensions=`** (#167), and that is the
practically useful half. A capability policy refuses a call; `extensions=`
withholds the builtin, so there is nothing behind the name to describe. A host
that does not want its agent catalogue readable should not reach for a
`DenyList` at all.

#756 was filed claiming this was undecided and undocumented. It was not — the
decision, its reasoning and a totality test all predate the issue. The filing
missed `NO_AUTHORITY_BUILTINS` by searching only `BUILTIN_CAPABILITIES` and
reading the absence as "nobody classified it", which is why an empty search
result is not evidence.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus import NodusRuntime  # noqa: E402
from nodus.runtime.capability import (  # noqa: E402
    ALL_CAPABILITIES,
    BUILTIN_CAPABILITIES,
    DenyList,
    NO_AUTHORITY_BUILTINS,
)

DISCOVERY = "discovery, not invocation"

#: Everything a host might have registered, so the assertions below are about
#: content this test owns rather than whatever the built-in tools happen to say.
AGENT_DESCRIPTION = "charges customer cards via the payments vendor"


def _deny_everything() -> DenyList:
    """Every capability the vocabulary has. If a new one is added and this is
    not updated, the invocation assertions weaken silently — so it is derived."""
    return DenyList(*sorted(ALL_CAPABILITIES))


class DiscoveryTestCase(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory(prefix="nodus756-")
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def runtime(self, **kwargs) -> NodusRuntime:
        rt = NodusRuntime(**kwargs)
        rt.register_agent("billing", lambda payload: {}, description=AGENT_DESCRIPTION)
        return rt

    def run_expr(self, rt, expr):
        return rt.run_source(f"print({expr})\n")


class InvocationIsRefusedTests(DiscoveryTestCase):
    """The #473 guarantee, and the control for everything below: if these ever
    stop being refused, the discovery findings mean nothing."""

    INVOCATIONS = {
        "agent_call": 'agent_call("billing", "{}")',
        "tool_call": 'tool_call("nodus_check", "{}")',
        "syscall": 'syscall("sys.v1.memory.get", "{}")',
    }

    # closes: #756
    def test_every_invocation_verb_is_refused(self):
        rt_kwargs = {"capability_policy": _deny_everything()}
        for name, expr in self.INVOCATIONS.items():
            with self.subTest(builtin=name):
                result = self.run_expr(self.runtime(**rt_kwargs), expr)
                self.assertFalse(result["ok"], f"{name} was not refused")
                self.assertEqual("sandbox", result["error"]["kind"])


class DiscoveryStaysOpenTests(DiscoveryTestCase):
    """The decision. Red here means somebody gated a discovery verb — which may
    well be right, but it is a change to the #473 rationale and to what
    `DenyList`'s docstring promises, so it should not happen by accident."""

    # closes: #756
    def test_names_are_visible(self):
        rt = self.runtime(capability_policy=_deny_everything())
        result = self.run_expr(rt, "agent_available()")
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("billing", result["stdout"])

    # closes: #756
    def test_host_authored_description_is_visible(self):
        """The part the 'naming what exists' rationale does not cover: this is
        not a name, it is prose the host wrote."""
        rt = self.runtime(capability_policy=_deny_everything())
        result = self.run_expr(rt, 'agent_describe("billing")')
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn(AGENT_DESCRIPTION, result["stdout"])

    # closes: #756
    def test_syscall_specs_name_the_capability_they_require(self):
        """Also beyond naming: this is a partial map of the authority model
        that is refusing the guest."""
        rt = self.runtime(capability_policy=_deny_everything())
        result = self.run_expr(rt, "syscall_list()")
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("capability", result["stdout"])


class ExtensionsCloseItTests(DiscoveryTestCase):
    """The mechanism that actually withholds discovery, and the reason this is
    a documentation issue rather than a defect: the capability policy is the
    wrong tool for the job, and the right one already exists."""

    # closes: #756
    def test_withholding_the_domain_hides_the_catalogue(self):
        for extensions in ([], ["workflow"]):
            with self.subTest(extensions=extensions):
                rt = self.runtime(extensions=extensions)
                result = self.run_expr(rt, 'agent_describe("billing")')
                self.assertFalse(result["ok"])
                self.assertEqual("sandbox", result["error"]["kind"])
                self.assertNotIn(AGENT_DESCRIPTION, result.get("stdout", ""))

    # closes: #756
    def test_granting_the_domain_restores_it(self):
        """The complement, so the test above is not satisfied by a runtime that
        cannot describe an agent under any configuration."""
        rt = self.runtime(extensions=["agent"])
        result = self.run_expr(rt, 'agent_describe("billing")')
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn(AGENT_DESCRIPTION, result["stdout"])


class TheDecisionIsRecordedTests(unittest.TestCase):
    """Source assertions: behaviour alone cannot say whether the current state
    was chosen or merely happened, and that distinction is what #756 got wrong."""

    # closes: #756
    def test_the_discovery_verbs_are_classified_not_merely_absent(self):
        classified = set(NO_AUTHORITY_BUILTINS[DISCOVERY])
        for name in ("agent_available", "agent_describe", "tool_available",
                     "tool_describe", "tool_has", "tool_list", "syscall_list"):
            with self.subTest(builtin=name):
                self.assertIn(
                    name, classified,
                    "a discovery verb that is in neither BUILTIN_CAPABILITIES "
                    "nor NO_AUTHORITY_BUILTINS is unclassified, which is the "
                    "state #756 wrongly believed these were in",
                )

    # closes: #756
    def test_they_are_not_also_governed(self):
        """The two structures partition the builtins; an overlap would mean the
        classification says both things at once."""
        for name in NO_AUTHORITY_BUILTINS[DISCOVERY]:
            with self.subTest(builtin=name):
                self.assertNotIn(name, BUILTIN_CAPABILITIES)

    # closes: #756
    def test_the_bucket_carries_its_reasoning(self):
        """The rationale lives in a comment above the bucket. If the bucket is
        ever moved or rewritten without it, the next reader inherits a list with
        no argument — which is how #756 came to be filed."""
        source = (_REPO_ROOT / "src" / "nodus" / "runtime" / "capability.py").read_text(
            encoding="utf-8"
        )
        marker = source.index(f'"{DISCOVERY}"')
        preceding = source[:marker].rsplit("\n\n", 1)[-1]
        self.assertIn(
            "Naming what exists is not reaching it", preceding,
            "the reasoning must stay attached to the list it justifies",
        )


if __name__ == "__main__":
    unittest.main()
