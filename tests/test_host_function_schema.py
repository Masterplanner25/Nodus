"""`register_function(schema=...)`: the host surface gets a real contract (#493).

A tool declared in Nodus had its arguments and return shape checked. A function
registered from the host had **arity and nothing else**, so wrong types passed
straight through into Python — on the surface that runs outside the VM and the
sandbox, where a bad value stops being a Nodus value and becomes whatever Python
does with it. The reported case succeeded with a plausible-looking result:

    write_file(42, {"not": "a string"})  ->  "wrote 42 (1 bytes)"

`len()` of the map returned 1, so nothing looked wrong.

Both surfaces now resolve to one validator in `runtime/schema_contract.py`, and
`test_both_surfaces_share_one_validator` is what fails if a second copy appears —
which is the failure mode this codebase keeps finding, and the reason the
existing helpers were *moved* rather than reimplemented.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402


def _write_file(path, contents):
    return f"wrote {path} ({len(contents)} bytes)"


def _counted(path, contents):
    return {"bytes": len(contents)}


def _lies(path, contents):
    return "not a map"


CONTRACT = {"path": "string", "contents": "string"}


class HostFunctionSchemaTests(unittest.TestCase):
    def _run(self, register, source):
        runtime = NodusRuntime(timeout_ms=None)
        register(runtime)
        return runtime.run_source(source)

    # closes: #493
    def test_wrong_argument_types_are_refused(self):
        """The reported repro. Must fail rather than produce a plausible result."""
        result = self._run(
            lambda rt: rt.register_function(
                "host_write", _write_file, arity=2, schema=CONTRACT
            ),
            'fn main() { print(host_write(42i, {"not": "a string"})) }',
        )
        self.assertFalse(result["ok"])
        self.assertIn(
            "Host function 'host_write': schema validation failed: "
            "argument 'path' must be a string",
            (result.get("error") or {}).get("message", ""),
        )
        # and the call did not happen
        self.assertNotIn("wrote", result.get("stdout") or "")

    def test_correct_argument_types_still_call_through(self):
        result = self._run(
            lambda rt: rt.register_function(
                "host_write", _write_file, arity=2, schema=CONTRACT
            ),
            'fn main() { print(host_write("ok.txt", "hello")) }',
        )
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("wrote ok.txt (5 bytes)", result.get("stdout") or "")

    def test_no_schema_keeps_the_previous_behaviour(self):
        """Additive: a registration without a schema is unchanged.

        This is what makes the feature safe to ship in a minor — every existing
        embedder's registrations keep working exactly as before.
        """
        result = self._run(
            lambda rt: rt.register_function("host_write", _write_file, arity=2),
            'fn main() { print(host_write(42i, {"a": 1i})) }',
        )
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("wrote 42", result.get("stdout") or "")

    def test_a_conforming_return_passes(self):
        result = self._run(
            lambda rt: rt.register_function(
                "counted", _counted, arity=2,
                schema=CONTRACT, returns_schema={"bytes": "int"},
            ),
            'fn main() { print(counted("a.txt", "hello")) }',
        )
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn('"bytes": 5', result.get("stdout") or "")

    def test_a_non_conforming_return_is_refused(self):
        result = self._run(
            lambda rt: rt.register_function(
                "lies", _lies, arity=2,
                schema=CONTRACT, returns_schema={"bytes": "int"},
            ),
            'fn main() { print(lies("a.txt", "hello")) }',
        )
        self.assertFalse(result["ok"])
        self.assertIn(
            "Host function 'lies': contract violation: expected a map return value",
            (result.get("error") or {}).get("message", ""),
        )


class RegistrationTimeRefusalTests(unittest.TestCase):
    """Refused at registration, not on first call.

    A declaration nobody validated is the declared-but-not-enforced shape, and an
    embedder who misspells a type should hear about it at startup rather than the
    first time a guest happens to reach that function.
    """

    def _register(self, **kwargs):
        NodusRuntime(timeout_ms=None).register_function("x", _write_file, **kwargs)

    def test_a_schema_that_does_not_cover_every_argument_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            self._register(arity=2, schema={"path": "string"})
        self.assertIn("but arity is 2", str(caught.exception))

    def test_an_unknown_type_name_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            self._register(arity=2, schema={"path": "strng", "contents": "string"})
        self.assertIn("unknown type 'strng'", str(caught.exception))

    def test_a_variadic_arity_with_a_schema_is_refused(self):
        """Positional binding needs a fixed arity to mean anything."""
        with self.assertRaises(ValueError) as caught:
            self._register(arity=(1, 2), schema={"path": "string"})
        self.assertIn("fixed arity", str(caught.exception))


class OneValidatorTests(unittest.TestCase):
    def test_both_surfaces_share_one_validator(self):
        """Source assertion: the same function object, not an equivalent copy.

        A behavioural test cannot catch a divergence here — two copies agree
        until someone edits one. `std:tool` keeps its former private names as
        aliases, so this compares identity rather than behaviour.
        """
        from nodus.builtins import tool_module
        from nodus.runtime import schema_contract

        self.assertIs(tool_module._normalize_schema, schema_contract.normalize_runtime_schema)
        self.assertIs(tool_module._validate_args, schema_contract.validate_args)
        self.assertIs(tool_module._validate_return, schema_contract.validate_return)

    def test_both_surfaces_word_a_type_failure_identically(self):
        """The messages are the contract embedders read; they must not drift."""
        from nodus.runtime.schema_contract import normalize_runtime_schema, validate_args

        schema, err = normalize_runtime_schema({"path": "string"})
        self.assertIsNone(err)
        self.assertEqual(
            validate_args({"path": 42}, schema),
            "argument 'path' must be a string",
        )


if __name__ == "__main__":
    unittest.main()
