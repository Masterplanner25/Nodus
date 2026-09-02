"""`std:runtime.capabilities()` — what this program may do right now (#87).

The issue asked for four things under "runtime self-knowledge". Three were already
shipped as `std:runtime` (`tasks`, `scheduler`, and memory via `std:memory`). This
is the fourth: the capability surface existed only in Python, so a Nodus program
could not ask whether it may reach the network before trying.

**The fifth item, `runtime.workflows()`, is deliberately not here.** The workflow
store and `.nodus/graphs/` are process-global and CWD-relative, so a builtin
listing every run would hand a guest every other tenant's records — #584 exactly,
where the copy that could not answer reached into the shared directory and
returned *something*. `_GRAPH_REGISTRY` and `_GRAPH_VMS` still have no per-runtime
knob; that is a scoping decision, not a missing function.

`test_it_reports_what_the_chokepoint_would_decide` is the one that matters. Asking
*"may I?"* and *"do it or refuse"* are one question, so they share
`VM.capability_decision`. Two implementations would drift, and the drift would be
a program told it may do something the runtime then refuses.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus import NodusRuntime  # noqa: E402
from nodus.runtime.capability import (  # noqa: E402
    ALL_CAPABILITIES,
    BUILTIN_CAPABILITIES,
    CapabilityDecision,
    CapabilityPolicy,
    DenyList,
)

REPORT = (
    'import "std:runtime" as rt\n'
    'fn main() { let c = rt.capabilities(); print("\\(c)") }\n'
)


def capabilities(**runtime_kwargs) -> dict:
    result = NodusRuntime(**runtime_kwargs).run_source(REPORT)
    assert result["ok"], result.get("error")
    text = result["stdout"].strip()
    # The printed map is Nodus's rendering; parse the pairs rather than eval it.
    body = text.strip("{}")
    pairs = {}
    for chunk in body.split(", "):
        key, _, value = chunk.partition(": ")
        pairs[key.strip('"')] = value.strip('"')
    return pairs


class ItReportsEveryCapabilityTests(unittest.TestCase):
    # closes: #87
    def test_every_capability_is_named(self):
        """A missing key would read as "no such capability" rather than "denied",
        so the map is total over the vocabulary."""
        self.assertEqual(set(ALL_CAPABILITIES), set(capabilities()))

    # closes: #87
    def test_every_answer_is_one_of_three(self):
        for capability, answer in capabilities().items():
            with self.subTest(capability=capability):
                self.assertIn(answer, {"allow", "deny", "ask"})


class ItReflectsTheRegistrationGatesTests(unittest.TestCase):
    """`allow_subprocess=False` and friends replace builtins with refusing stubs
    *before* any policy is consulted, so a withheld group is denied whatever the
    policy says."""

    # closes: #87
    def test_deny_by_default_is_visible(self):
        report = capabilities()
        for capability in ("subprocess", "network", "env"):
            with self.subTest(capability=capability):
                self.assertEqual("deny", report[capability])

    # closes: #87
    def test_granting_a_flag_changes_the_answer(self):
        self.assertEqual("allow", capabilities(allow_network=True)["network"])
        self.assertEqual("deny", capabilities(allow_network=True)["subprocess"])

    # closes: #87
    def test_an_ungated_capability_is_allowed_by_default(self):
        report = capabilities()
        self.assertEqual("allow", report["fs.read"])
        self.assertEqual("allow", report["tool.invoke"])


class ItReflectsThePolicyTests(unittest.TestCase):
    # closes: #87
    def test_a_denylist_shows_deny(self):
        report = capabilities(capability_policy=DenyList("fs.read"))
        self.assertEqual("deny", report["fs.read"])
        self.assertEqual("allow", report["tool.invoke"], "only the named one is denied")

    # closes: #87
    def test_ask_is_reported_as_ask_not_as_deny(self):
        """`ask` with no approval channel *is* refused at the chokepoint, and is
        still reported as `ask`: the channel is the host's to supply and may be
        there by the time the call happens. Collapsing it to `deny` would tell a
        program a capability is unavailable when it is merely gated on a human.
        """
        class Asker(CapabilityPolicy):
            def check(self, request):
                if request.capability == "tool.invoke":
                    return CapabilityDecision(outcome="ask", reason="needs a human")
                return CapabilityDecision.allow()

        report = capabilities(capability_policy=Asker())
        self.assertEqual("ask", report["tool.invoke"])
        self.assertEqual("allow", report["fs.read"])


class OneQuestionOneAnswerTests(unittest.TestCase):
    # closes: #87
    def test_it_reports_what_the_chokepoint_would_decide(self):
        """The report and the enforcement share `VM.capability_decision`.

        Asserted on the source because behaviour cannot see the difference until
        the two drift -- and by then a program has been told it may do something
        the runtime refuses, which is the worse half of being wrong.
        """
        source = (
            Path_of("src/nodus/vm/vm.py")
        )
        self.assertIn("def capability_decision(", source)
        # Both callers reach the decision through it, rather than each consulting
        # the floor and the policy themselves.
        self.assertEqual(
            2, source.count("self.capability_decision("),
            "check_capability and builtin_runtime_capabilities must be the only "
            "callers, and both must go through it",
        )

    # closes: #87
    def test_asking_grants_nothing(self):
        """Self-referential, so it belongs in the ungated introspection group --
        a capability report that itself required a capability would be unusable
        by the program that needs it most."""
        source = Path_of("src/nodus/runtime/capability.py")
        marker = '"introspection of the running program"'
        start = source.index(marker)
        group = source[start:source.index("),", start)]
        self.assertIn('"runtime_capabilities"', group)

    # closes: #87
    def test_a_withheld_group_is_detected_by_its_marker(self):
        """Not by sniffing the stub's `__name__`, which would break silently the
        first time someone renames it."""
        source = Path_of("src/nodus/builtins/registry.py")
        self.assertIn("nodus_blocked_capability", source)

    # closes: #87
    def test_every_capability_has_a_representative_builtin(self):
        """The 'no builtin dispatches this' branch is a guard, not dead code --
        but today it is unreachable, and that is worth knowing: if a capability
        is added with nothing behind it, this fails and names it."""
        covered = set(BUILTIN_CAPABILITIES.values())
        self.assertEqual(set(), set(ALL_CAPABILITIES) - covered)


def Path_of(relative: str) -> str:
    from pathlib import Path

    return (Path(__file__).resolve().parents[1] / relative).read_text(encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
