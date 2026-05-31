"""Tests for the HandlerContract infrastructure (Docs-as-Contracts)."""

import io
import sys
import os
import unittest
from contextlib import redirect_stdout, redirect_stderr

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

import nodus  # noqa: E402
from nodus.runtime.module_loader import ModuleLoader  # noqa: E402
from nodus_schema import HandlerContract, VALID_EFFECTS  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers (mirrors test_tool_registry.py convention)
# ---------------------------------------------------------------------------

def _run(src: str):
    vm = nodus.VM([], {}, code_locs=[], source_path="test.nd")
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        loader = ModuleLoader(project_root=None, vm=vm)
        loader.load_module_from_source(src, module_name="test.nd")
    return out.getvalue().splitlines(), err.getvalue()


def _run_vm(src: str):
    vm = nodus.VM([], {}, code_locs=[], source_path="test.nd")
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        loader = ModuleLoader(project_root=None, vm=vm)
        loader.load_module_from_source(src, module_name="test.nd")
    return vm, out.getvalue().splitlines(), err.getvalue()


# ---------------------------------------------------------------------------
# HandlerContract.validate() — structural checks
# ---------------------------------------------------------------------------

class TestHandlerContractValidate(unittest.TestCase):

    def test_minimal_valid_contract(self):
        c = HandlerContract(name="myapp.action", description="does a thing")
        self.assertEqual(c.validate(), [])

    def test_full_valid_contract(self):
        c = HandlerContract(
            name="myapp.action",
            description="does a thing",
            input_schema={"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
            returns_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
            effects=["network"],
            capabilities_required=["net.outbound"],
            version="2.0.0",
            tags=["http", "external"],
        )
        self.assertEqual(c.validate(), [])

    def test_empty_name_rejected(self):
        c = HandlerContract(name="", description="d")
        errors = c.validate()
        self.assertTrue(any("name" in e for e in errors))

    def test_name_without_dot_rejected(self):
        c = HandlerContract(name="nodot", description="d")
        errors = c.validate()
        self.assertTrue(any("dotted" in e for e in errors))

    def test_empty_description_rejected(self):
        c = HandlerContract(name="a.b", description="")
        errors = c.validate()
        self.assertTrue(any("description" in e for e in errors))

    def test_whitespace_description_rejected(self):
        c = HandlerContract(name="a.b", description="   ")
        errors = c.validate()
        self.assertTrue(any("description" in e for e in errors))

    def test_default_effects_is_pure(self):
        c = HandlerContract(name="a.b", description="d")
        self.assertEqual(c.effects, ["pure"])
        self.assertEqual(c.validate(), [])

    def test_each_valid_effect_accepted(self):
        for fx in VALID_EFFECTS:
            c = HandlerContract(name="a.b", description="d", effects=[fx])
            self.assertEqual(c.validate(), [], msg=f"effect {fx!r} should be valid")

    def test_unknown_effect_rejected(self):
        c = HandlerContract(name="a.b", description="d", effects=["teleportation"])
        errors = c.validate()
        self.assertTrue(any("teleportation" in e for e in errors))

    def test_pure_combined_with_other_rejected(self):
        c = HandlerContract(name="a.b", description="d", effects=["pure", "network"])
        errors = c.validate()
        self.assertTrue(any("pure" in e for e in errors))

    def test_multiple_non_pure_effects_accepted(self):
        c = HandlerContract(
            name="a.b", description="d",
            effects=["network", "writes_state"],
        )
        self.assertEqual(c.validate(), [])

    def test_empty_effects_list_invalid(self):
        c = HandlerContract(name="a.b", description="d", effects=[])
        errors = c.validate()
        self.assertTrue(any("effects" in e for e in errors))


# ---------------------------------------------------------------------------
# VALID_EFFECTS vocabulary
# ---------------------------------------------------------------------------

class TestValidEffects(unittest.TestCase):

    def test_expected_effects_present(self):
        expected = {"pure", "reads_state", "writes_state", "network", "filesystem", "spawns_task"}
        self.assertEqual(set(VALID_EFFECTS), expected)

    def test_is_frozenset(self):
        self.assertIsInstance(VALID_EFFECTS, frozenset)


# ---------------------------------------------------------------------------
# tool.register() — effects and returns_schema wiring (Nodus runtime tests)
# ---------------------------------------------------------------------------

class TestToolRegisterContracts(unittest.TestCase):
    """Integration: tool.register() stores and enforces contract fields."""

    def test_register_with_effects_stored(self):
        vm, _, _ = _run_vm(
            'import "std:tool" as tool\n'
            'tool.register({name: "test.act", handler: fn(a){ return {} }, description: "h", effects: ["network"]})\n'
        )
        entry = vm.tool_registry.get("test.act")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["effects"], ["network"])

    def test_register_defaults_effects_to_pure(self):
        vm, _, _ = _run_vm(
            'import "std:tool" as tool\n'
            'tool.register({name: "test.pure", handler: fn(a){ return {} }, description: "h"})\n'
        )
        entry = vm.tool_registry.get("test.pure")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["effects"], ["pure"])

    def test_register_multiple_non_pure_effects_stored(self):
        vm, _, _ = _run_vm(
            'import "std:tool" as tool\n'
            'tool.register({name: "test.multi", handler: fn(a){ return {} }, description: "h", effects: ["network", "writes_state"]})\n'
        )
        entry = vm.tool_registry.get("test.multi")
        self.assertIsNotNone(entry)
        self.assertIn("network", entry["effects"])
        self.assertIn("writes_state", entry["effects"])

    def test_register_unknown_effect_returns_invalid_metadata_error(self):
        lines, _ = _run(
            'import "std:tool" as tool\n'
            'let r = tool.register({name: "test.bad", handler: fn(a){ return {} }, description: "h", effects: ["magic"]})\n'
            'print(r.payload["category"])\n'
        )
        self.assertEqual(lines[0], "invalid_metadata")

    def test_register_pure_with_network_returns_invalid_metadata_error(self):
        lines, _ = _run(
            'import "std:tool" as tool\n'
            'let r = tool.register({name: "test.conflict", handler: fn(a){ return {} }, description: "h", effects: ["pure", "network"]})\n'
            'print(r.payload["category"])\n'
        )
        self.assertEqual(lines[0], "invalid_metadata")

    def test_returns_schema_stored_normalized(self):
        vm, _, _ = _run_vm(
            'import "std:tool" as tool\n'
            'tool.register({name: "test.strict", handler: fn(a){ return {ok: true} }, description: "h", returns_schema: {ok: "bool"}})\n'
        )
        entry = vm.tool_registry.get("test.strict")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["returns_schema"].get("type"), "object")

    def test_returns_schema_valid_return_passes(self):
        lines, _ = _run(
            'import "std:tool" as tool\n'
            'tool.register({name: "test.valid", handler: fn(a){ return {ok: true} }, description: "h", returns_schema: {ok: "bool"}})\n'
            'let r = tool.invoke("test.valid", {})\n'
            'print(type(r))\n'
        )
        self.assertEqual(lines[0], "record")

    def test_returns_schema_violation_gives_contract_violation_error(self):
        lines, _ = _run(
            'import "std:tool" as tool\n'
            'tool.register({name: "test.badret", handler: fn(a){ return "wrong" }, description: "h", returns_schema: {result: "string"}})\n'
            'let r = tool.invoke("test.badret", {})\n'
            'print(r.payload["category"])\n'
        )
        self.assertEqual(lines[0], "contract_violation")


if __name__ == "__main__":
    unittest.main()
