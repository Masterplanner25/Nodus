"""Tests for Task 6.1: Memory API stabilization."""
import unittest

from nodus.tooling.runner import run_source


def _exec(src: str) -> dict:
    result, _vm = run_source(src, filename="<test>")
    return result


def _out(src: str) -> str:
    return _exec(src).get("stdout", "").strip()


class MemoryPutGetTests(unittest.TestCase):
    def test_put_and_get_roundtrip(self):
        result = _exec('memory_put("k", 42)\nlet v = memory_get("k")\nprint(v)\n')
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(result["stdout"].strip(), "42.0")

    def test_get_missing_key_returns_null(self):
        self.assertEqual(_out('let v = memory_get("no_such_key_xyz")\nprint(v)\n'), "nil")

    def test_put_returns_stored_value(self):
        self.assertEqual(_out('let v = memory_put("x", 7)\nprint(v)\n'), "7.0")


class MemoryDeleteTests(unittest.TestCase):
    def test_delete_existing_key(self):
        self.assertEqual(_out('memory_put("d", 1)\nlet r = memory_delete("d")\nprint(r)\n'), "true")

    def test_delete_missing_key_is_noop(self):
        self.assertEqual(_out('let r = memory_delete("no_such_xyz")\nprint(r)\n'), "false")

    def test_get_after_delete_returns_null(self):
        self.assertEqual(_out('memory_put("z", 99)\nmemory_delete("z")\nlet v = memory_get("z")\nprint(v)\n'), "nil")


class MemoryHasTests(unittest.TestCase):
    def test_has_existing_key_returns_true(self):
        self.assertEqual(_out('memory_put("h", 1)\nlet r = memory_has("h")\nprint(r)\n'), "true")

    def test_has_missing_key_returns_false(self):
        self.assertEqual(_out('let r = memory_has("no_such_key_abc")\nprint(r)\n'), "false")

    def test_has_after_delete_returns_false(self):
        self.assertEqual(_out('memory_put("hd", 1)\nmemory_delete("hd")\nlet r = memory_has("hd")\nprint(r)\n'), "false")

    def test_has_does_not_require_non_null_value(self):
        """memory_has must return true even if nil is stored under the key.

        The old std:memory has() used (value != nil), which was incorrect.
        """
        self.assertEqual(_out('memory_put("nil_key", nil)\nlet r = memory_has("nil_key")\nprint(r)\n'), "true")


class MemoryKeyValidationTests(unittest.TestCase):
    def _assert_type_error(self, src: str) -> None:
        result = _exec(src)
        self.assertFalse(result.get("ok"), f"Expected failure for: {src!r}")
        self.assertEqual((result.get("error") or {}).get("kind"), "type")

    def test_non_string_key_raises_type_error(self):
        self._assert_type_error('memory_put(42, "v")\n')

    def test_non_string_key_get_raises(self):
        self._assert_type_error('memory_get(nil)\n')

    def test_non_string_key_has_raises(self):
        self._assert_type_error('memory_has(99)\n')

    def test_non_string_key_delete_raises(self):
        self._assert_type_error('memory_delete(true)\n')


class StdMemoryModuleTests(unittest.TestCase):
    """Test the std:memory module interface (memory.X() dot-call form)."""

    def test_std_memory_put_and_get(self):
        self.assertEqual(_out('import "std:memory" as memory\nmemory.put("sm", 77)\nprint(memory.get("sm"))\n'), "77.0")

    def test_std_memory_has_true(self):
        self.assertEqual(_out('import "std:memory" as memory\nmemory.put("sh", 1)\nprint(memory.has("sh"))\n'), "true")

    def test_std_memory_has_false(self):
        self.assertEqual(_out('import "std:memory" as memory\nprint(memory.has("no_such_xyz_std"))\n'), "false")

    def test_std_memory_delete(self):
        self.assertEqual(_out('import "std:memory" as memory\nmemory.put("sd", 5)\nmemory.delete("sd")\nprint(memory.get("sd"))\n'), "nil")

    def test_std_memory_get_missing_returns_null(self):
        self.assertEqual(_out('import "std:memory" as memory\nprint(memory.get("no_such_xyz_std2"))\n'), "nil")
