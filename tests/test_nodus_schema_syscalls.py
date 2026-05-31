import sys
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus_schema.syscalls import (  # noqa: E402
    SyscallSpec,
    parse_syscall_name,
    resolve_version,
    validate_input,
    validate_output,
)


class SyscallNameTests(unittest.TestCase):
    def test_parse_valid_syscall_name(self):
        version, action = parse_syscall_name("sys.v1.memory.read")
        self.assertEqual(version, "v1")
        self.assertEqual(action, "memory.read")

    def test_parse_rejects_missing_prefix(self):
        with self.assertRaises(ValueError):
            parse_syscall_name("memory.read")

    def test_parse_rejects_missing_action(self):
        with self.assertRaises(ValueError):
            parse_syscall_name("sys.v1.")


class VersionResolutionTests(unittest.TestCase):
    def test_resolve_exact_version(self):
        resolved = resolve_version("v1", {"v1", "v2"})
        self.assertEqual(resolved, "v1")

    def test_resolve_unknown_without_fallback(self):
        resolved = resolve_version("v9", {"v1", "v2"}, fallback=False)
        self.assertIsNone(resolved)

    def test_resolve_unknown_with_fallback(self):
        resolved = resolve_version("v9", {"v1", "v2"}, fallback=True)
        self.assertEqual(resolved, "v1")


class ValidationTests(unittest.TestCase):
    def test_validate_input_missing_required_field(self):
        errors = validate_input(
            {
                "required": ["query"],
                "properties": {"query": {"type": "string"}},
            },
            {},
        )
        self.assertEqual(errors, ["Missing required field: 'query'"])

    def test_validate_input_type_mismatch(self):
        errors = validate_input(
            {
                "required": ["limit"],
                "properties": {"limit": {"type": "integer"}},
            },
            {"limit": "3"},
        )
        self.assertEqual(errors, ["Field 'limit': expected type 'integer', got 'str'"])

    def test_validate_output_uses_same_rules(self):
        errors = validate_output(
            {
                "required": ["ok"],
                "properties": {"ok": {"type": "boolean"}},
            },
            {"ok": 1},
        )
        self.assertEqual(errors, ["Field 'ok': expected type 'boolean', got 'int'"])


class SyscallSpecTests(unittest.TestCase):
    def test_spec_to_dict_and_deprecation_message(self):
        spec = SyscallSpec(
            name="memory.read",
            version="v1",
            capability="memory.read",
            description="Read memory",
            deprecated=True,
            deprecated_since="v2",
            replacement="sys.v2.memory.read",
        )
        payload = spec.to_dict()
        self.assertEqual(payload["full_name"], "sys.v1.memory.read")
        self.assertTrue(payload["deprecated"])
        self.assertEqual(
            spec.deprecation_message(),
            "Syscall 'sys.v1.memory.read' is deprecated since v2 use 'sys.v2.memory.read' instead.",
        )


if __name__ == "__main__":
    unittest.main()
