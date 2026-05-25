"""v3.0.1 Commit 2 tests — Embedding API plumbing.

Covers:
- BUG-E03: NodusRuntime.run_source host_globals actually reaches the script (#55)
- BUG-E04: Python exceptions from host-registered functions propagate to caller (#56)
"""

import unittest

from nodus import NodusRuntime


class HostGlobalsTests(unittest.TestCase):
    """BUG-E03: host_globals parameter is forwarded to the Nodus VM."""

    def test_host_globals_string_accessible(self):
        rt = NodusRuntime()
        result = rt.run_source('print(greeting)', host_globals={"greeting": "hello"})
        self.assertTrue(result["ok"])
        self.assertIn("hello", result["stdout"])

    def test_host_globals_int_accessible(self):
        rt = NodusRuntime()
        result = rt.run_source('print(x)', host_globals={"x": 5})
        self.assertTrue(result["ok"])
        self.assertIn("5", result["stdout"])

    def test_host_globals_float_accessible(self):
        rt = NodusRuntime()
        result = rt.run_source('print(ratio)', host_globals={"ratio": 3.14})
        self.assertTrue(result["ok"])
        self.assertIn("3.14", result["stdout"])

    def test_host_globals_list_accessible(self):
        rt = NodusRuntime()
        result = rt.run_source('print(type(items))', host_globals={"items": [1, 2, 3]})
        self.assertTrue(result["ok"])
        self.assertIn("list", result["stdout"])

    def test_host_globals_map_accessible(self):
        rt = NodusRuntime()
        result = rt.run_source('print(cfg["key"])', host_globals={"cfg": {"key": "val"}})
        self.assertTrue(result["ok"])
        self.assertIn("val", result["stdout"])

    def test_host_globals_used_in_expression(self):
        rt = NodusRuntime()
        result = rt.run_source('print(x + 10)', host_globals={"x": 5.0})
        self.assertTrue(result["ok"])
        self.assertIn("15", result["stdout"])

    def test_host_globals_multiple_vars(self):
        rt = NodusRuntime()
        result = rt.run_source('print(a + b)', host_globals={"a": 3.0, "b": 4.0})
        self.assertTrue(result["ok"])
        self.assertIn("7", result["stdout"])

    def test_host_globals_undefined_var_still_errors(self):
        rt = NodusRuntime()
        result = rt.run_source('print(undefined_var)', host_globals={"x": 1})
        self.assertFalse(result["ok"])

    def test_initial_globals_accessible(self):
        rt = NodusRuntime()
        result = rt.run_source('print(val)', initial_globals={"val": "from_initial"})
        self.assertTrue(result["ok"])
        self.assertIn("from_initial", result["stdout"])

    def test_nodus_side_error_still_returns_err_dict(self):
        """Nodus runtime errors (not from host functions) must still return error dict."""
        rt = NodusRuntime()
        result = rt.run_source('1 / 0')
        self.assertFalse(result["ok"])
        self.assertIn("error", result)


class HostExceptionPropagationTests(unittest.TestCase):
    """BUG-E04: Python exceptions from host-registered functions propagate to caller."""

    def test_value_error_propagates(self):
        rt = NodusRuntime()

        def bad():
            raise ValueError("host value error")

        rt.register_function("bad", bad, arity=0)
        with self.assertRaises(ValueError) as ctx:
            rt.run_source("bad()")
        self.assertIn("host value error", str(ctx.exception))

    def test_key_error_propagates(self):
        rt = NodusRuntime()

        def lookup():
            raise KeyError("missing_key")

        rt.register_function("lookup", lookup, arity=0)
        with self.assertRaises(KeyError):
            rt.run_source("lookup()")

    def test_custom_exception_propagates(self):
        class AppError(Exception):
            pass

        rt = NodusRuntime()

        def explode():
            raise AppError("custom app error")

        rt.register_function("explode", explode, arity=0)
        with self.assertRaises(AppError) as ctx:
            rt.run_source("explode()")
        self.assertIn("custom app error", str(ctx.exception))

    def test_nodus_error_not_confused_with_host_error(self):
        """A Nodus-side division-by-zero should NOT propagate as a Python exception."""
        rt = NodusRuntime()
        result = rt.run_source("1 / 0")
        self.assertIsInstance(result, dict)
        self.assertFalse(result["ok"])

    def test_host_function_success_still_works(self):
        rt = NodusRuntime()

        def add_one(n):
            return n + 1

        rt.register_function("add_one", add_one, arity=1)
        result = rt.run_source("print(add_one(4.0))")
        self.assertTrue(result["ok"])
        self.assertIn("5", result["stdout"])


if __name__ == "__main__":
    unittest.main()
