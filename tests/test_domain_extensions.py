"""A host can choose which domain surfaces a runtime carries (#167).

Every VM registered the whole agentic surface unconditionally — 33 builtins for
workflows, goals, graphs, tools, agents, syscalls and memory actions — whether or
not the host wanted any of it. An embedder using Nodus as a general-purpose
scripting engine carried all of it, with no way to omit it short of forking.

`NodusRuntime(extensions=[...])` selects. **`None` means all**, so nothing that
exists today changes, and that default is the opposite of `GATED_BUILTINS`' on
purpose: denying a capability protects against a *program*, while omitting a
domain narrows what the runtime is *for*. A runtime that silently lost
`run_workflow` on upgrade would be a worse failure than one carrying a surface
nobody calls.

Two decisions worth stating, because both could reasonably have gone the other
way:

- **Withheld builtins are refusing stubs, not absent names.** A stub says
  *"workflow orchestration is not granted; pass extensions=["workflow"]"*; an
  absent name says `Undefined function` and sends the reader hunting a typo. It
  also keeps the name occupied, and `register_function` refusing to shadow a
  builtin is a security boundary (#443) that only holds for names that exist.
- **An unknown extension name is refused, not ignored.** A typo that silently
  withheld the surface it meant to grant is the "accepted and ignored" third
  state #490 refused for `nodus.toml`.
"""

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus import NodusRuntime  # noqa: E402
from nodus.runtime.capability import (  # noqa: E402
    DOMAIN_BUILTIN_GROUPS,
    DOMAIN_BUILTIN_NAMES,
    GATED_BUILTIN_NAMES,
)
from nodus.runtime.diagnostics import LangRuntimeError  # noqa: E402
from nodus.vm.vm import VM  # noqa: E402


def _vm(extensions=None) -> VM:
    return VM([], {}, code_locs=[], source_path=None, extensions=extensions)


def _call(vm: VM, name: str):
    """Invoke a builtin directly and say what happened.

    Called with two arguments because that satisfies every arity in these
    groups; a withheld stub accepts anything, and a live builtin that rejects
    the argument *types* has still demonstrably been reached.
    """
    try:
        vm.builtins[name].fn({}, {})
        return "reached"
    except LangRuntimeError as err:
        return "withheld" if err.kind == "sandbox" else "reached"
    except Exception:
        return "reached"


class TheDefaultCarriesEverythingTests(unittest.TestCase):
    """The compatibility half. Every caller that exists today passes nothing."""

    # closes: #167
    def test_no_domain_builtin_is_withheld_by_default(self):
        vm = _vm()
        for name in sorted(DOMAIN_BUILTIN_NAMES):
            with self.subTest(builtin=name):
                self.assertEqual("reached", _call(vm, name))

    # closes: #167
    def test_a_workflow_runs_with_no_extensions_argument(self):
        result = NodusRuntime().run_source(
            "workflow w { step a { return 1i } }\n"
            'fn main() { run_workflow(w); print("ran") }\n'
        )
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("ran", result["stdout"])


class SelectingASubsetTests(unittest.TestCase):
    # closes: #167
    def test_an_empty_list_withholds_every_domain_builtin(self):
        vm = _vm(extensions=[])
        for name in sorted(DOMAIN_BUILTIN_NAMES):
            with self.subTest(builtin=name):
                self.assertEqual("withheld", _call(vm, name))

    # closes: #167
    def test_a_selected_group_is_granted_and_the_rest_are_not(self):
        vm = _vm(extensions=["workflow"])
        for name in DOMAIN_BUILTIN_GROUPS["workflow"].names:
            with self.subTest(granted=name):
                self.assertEqual("reached", _call(vm, name))
        for group in ("agent", "tool", "syscall", "memory"):
            for name in DOMAIN_BUILTIN_GROUPS[group].names:
                with self.subTest(withheld=name):
                    self.assertEqual("withheld", _call(vm, name))

    # closes: #167
    def test_it_works_through_the_runtime(self):
        source = (
            "workflow w { step a { return 1i } }\n"
            'fn main() { run_workflow(w); print("ran") }\n'
        )
        self.assertTrue(NodusRuntime(extensions=["workflow"]).run_source(source)["ok"])
        lean = NodusRuntime(extensions=[]).run_source(source)
        self.assertFalse(lean["ok"])
        self.assertEqual("sandbox", lean["error"]["type"])

    # closes: #167
    def test_the_general_purpose_surface_survives_a_lean_runtime(self):
        """The point of the feature. Withholding the agentic surface must leave
        a working scripting engine behind, or `extensions=[]` is useless."""
        result = NodusRuntime(extensions=[]).run_source(
            'import "std:strings" as s\n'
            "fn main() {\n"
            '    let parts = s.split("a,b,c", ",")\n'
            '    print("\\(len(parts)) parts")\n'
            "}\n"
        )
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("3 parts", result["stdout"])


class TheRefusalIsUsefulTests(unittest.TestCase):
    # closes: #167
    def test_it_says_how_to_grant_the_surface(self):
        vm = _vm(extensions=[])
        with self.assertRaises(LangRuntimeError) as caught:
            vm.builtins["run_workflow"].fn({}, {})
        message = str(caught.exception)
        self.assertIn("workflow, goal and graph orchestration", message)
        self.assertIn('extensions=["workflow"]', message)

    # closes: #167
    def test_a_withheld_builtin_is_a_stub_rather_than_an_absent_name(self):
        """`Undefined function` would send the reader looking for a typo, and an
        absent name can be shadowed — which #443 made a security boundary."""
        vm = _vm(extensions=[])
        for name in sorted(DOMAIN_BUILTIN_NAMES):
            with self.subTest(builtin=name):
                self.assertIn(name, vm.builtins)

    # closes: #167
    def test_an_unknown_extension_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            _vm(extensions=["workfow"])
        self.assertIn("workfow", str(caught.exception))
        self.assertIn("workflow", str(caught.exception), "it lists the known names")

    # closes: #167
    def test_it_is_refused_at_the_documented_entry_point_too(self):
        """`NodusRuntime`, not just the raw `VM` — which is the gap that shipped.

        Every other test here builds a `VM` directly, so nothing covered the
        path an embedder actually takes. A `NodusRuntime` does not construct a
        VM until it runs something, so a misspelled surface was accepted at
        construction and then raised a bare `ValueError` out of the first
        `run_source` — breaking that method's contract of always returning a
        result dict, and falsifying the "refused at construction" claim in both
        the docstring and the embedding guide.

        Gate 10b caught it against the built wheel. The suite could not, because
        the tested path and the documented path were different ones.
        """
        with self.assertRaises(ValueError) as caught:
            NodusRuntime(extensions=["workfow"])
        self.assertIn("workfow", str(caught.exception))
        self.assertIn("workflow", str(caught.exception))

    # closes: #167
    def test_the_valid_cases_still_construct(self):
        """The complement: the guard above must not refuse what it should pass."""
        for extensions in (None, [], ["workflow"], ["workflow", "agent"]):
            with self.subTest(extensions=extensions):
                NodusRuntime(extensions=extensions)

    # closes: #167
    def test_both_entry_points_share_one_validator(self):
        """Source assertion. They refused at *different moments* before this —
        the VM at construction, the runtime at first run — which is one question
        answered twice, drifted in timing rather than in content."""
        import inspect

        from nodus.runtime import capability, embedding
        from nodus.vm import vm as vm_module

        self.assertTrue(hasattr(capability, "validate_extensions"))
        for module in (embedding, vm_module):
            with self.subTest(module=module.__name__):
                self.assertIn(
                    "validate_extensions(extensions)", inspect.getsource(module),
                    "must delegate rather than re-implement the check",
                )


class TheGroupDataIsHonestTests(unittest.TestCase):
    """The manifest-shaped half: a group naming a builtin nobody registers, or
    a domain builtin belonging to no group, are both silent failures."""

    # closes: #167
    def test_every_named_builtin_is_actually_registered(self):
        vm = _vm()
        for name in sorted(DOMAIN_BUILTIN_NAMES):
            with self.subTest(builtin=name):
                self.assertIn(
                    name, vm.builtins,
                    "a renamed builtin would leave this group naming nothing",
                )

    # closes: #167
    def test_the_domain_and_capability_sets_are_disjoint(self):
        """Two different questions — *what is this runtime for* and *what may
        this program do* — so no builtin should be answered by both. An overlap
        would mean two mechanisms racing to withhold one name."""
        self.assertEqual(frozenset(), DOMAIN_BUILTIN_NAMES & GATED_BUILTIN_NAMES)

    # closes: #167
    def test_emit_is_deliberately_ungrouped(self):
        """It takes a name and a JSON payload and puts an event on the bus —
        observability a lean runtime still wants. `__action_emit` *is* grouped,
        because it is the lowering of an `action` statement, which only exists
        inside a flow."""
        self.assertNotIn("emit", DOMAIN_BUILTIN_NAMES)
        self.assertIn("__action_emit", DOMAIN_BUILTIN_GROUPS["workflow"].names)


class ItCostsTheVmNoAttributeTests(unittest.TestCase):
    """PyPy maps have a hard 80-instance-attribute cliff, and the VM sits just
    under it — #488 crossed it and cost ~9x for three releases (#702). The rule
    the guard leaves is "shed an attribute, do not raise the number", so a new
    constructor argument must be consumed rather than stored."""

    # closes: #167
    def test_extensions_is_not_kept_on_the_instance(self):
        self.assertNotIn("extensions", vars(_vm()))
        self.assertNotIn("extensions", vars(_vm(extensions=["workflow"])))


if __name__ == "__main__":
    unittest.main()
