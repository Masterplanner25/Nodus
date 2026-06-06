"""UX hint improvements: #123, #127, #129, #130, #128, #131."""

import io
import sys
import unittest

from nodus.cli.cli import main as _cli_main
from nodus.runtime.embedding import NodusRuntime


def _err(src):
    rt = NodusRuntime(allowed_paths=None)
    r = rt.run_source(src, filename="t.nd")
    return (r.get("errors") or [{}])[0].get("message", "")


def _out(src):
    rt = NodusRuntime(allowed_paths=None)
    r = rt.run_source(src, filename="t.nd")
    return r["stdout"].strip()


class AwaitHintTests(unittest.TestCase):
    """BUG-130: await/async give a targeted 'not a keyword' message."""

    def test_await_gives_hint(self):
        msg = _err("let x = await foo()")
        self.assertIn("await", msg)
        self.assertIn("not a keyword", msg)

    def test_async_gives_hint(self):
        msg = _err("let x = async foo()")
        self.assertIn("async", msg)
        self.assertIn("not a keyword", msg)

    def test_await_message_mentions_async_builtins(self):
        msg = _err("let x = await foo()")
        self.assertIn("http_get_async", msg)


class MapIterationHintTests(unittest.TestCase):
    """BUG-129: for k in map gives a hint about keys(m)."""

    def test_map_iteration_gives_hint(self):
        msg = _err('let m = {"a": 1i}\nfor k in m { print(k) }')
        self.assertIn("keys(m)", msg)
        self.assertIn("values(m)", msg)

    def test_list_iteration_still_works(self):
        out = _out("for x in [1i, 2i, 3i] { print(x) }")
        self.assertEqual(out, "1\n2\n3")


class BareImportHintTests(unittest.TestCase):
    """BUG-127: bare import without 'as' gives a helpful alias hint."""

    def test_bare_import_gives_hint_on_alias_access(self):
        msg = _err('import "std:json"\nlet x = json.parse("{}")')
        self.assertIn("std:json", msg)
        self.assertIn("as json", msg)

    def test_bare_import_exports_work_directly(self):
        out = _out('import "std:json"\nprint(type(parse("{}")))')
        self.assertEqual(out, "map")

    def test_aliased_import_works_normally(self):
        out = _out('import "std:json" as j\nprint(j.parse("1"))')
        self.assertEqual(out, "1.0")


class StartsWithEndsWithTests(unittest.TestCase):
    """BUG-123: std:strings starts_with and ends_with."""

    def test_starts_with_true(self):
        out = _out('import "std:strings" as s\nprint(s.starts_with("hello world", "hello"))')
        self.assertEqual(out, "true")

    def test_starts_with_false(self):
        out = _out('import "std:strings" as s\nprint(s.starts_with("hello world", "world"))')
        self.assertEqual(out, "false")

    def test_ends_with_true(self):
        out = _out('import "std:strings" as s\nprint(s.ends_with("file.json", ".json"))')
        self.assertEqual(out, "true")

    def test_ends_with_false(self):
        out = _out('import "std:strings" as s\nprint(s.ends_with("file.json", ".txt"))')
        self.assertEqual(out, "false")

    def test_starts_with_empty_prefix(self):
        out = _out('import "std:strings" as s\nprint(s.starts_with("hi", ""))')
        self.assertEqual(out, "true")

    def test_ends_with_longer_suffix_returns_false(self):
        out = _out('import "std:strings" as s\nprint(s.ends_with("hi", "hello"))')
        self.assertEqual(out, "false")

    def test_str_startswith_builtin_direct(self):
        out = _out('print(str_startswith("nodus", "no"))')
        self.assertEqual(out, "true")

    def test_str_endswith_builtin_direct(self):
        out = _out('print(str_endswith("nodus", "us"))')
        self.assertEqual(out, "true")


class PushAliasTests(unittest.TestCase):
    """BUG-128: push() should work as a top-level builtin alias for list_push."""

    def test_push_appends_item(self):
        out = _out("let xs = []\nxs = push(xs, 1i)\nprint(xs[0])")
        self.assertEqual(out, "1")

    def test_push_and_list_push_same_behavior(self):
        out1 = _out("let xs = []\nxs = push(xs, 42i)\nprint(xs[0])")
        out2 = _out("let xs = []\nxs = list_push(xs, 42i)\nprint(xs[0])")
        self.assertEqual(out1, out2)

    def test_push_multiple_items(self):
        out = _out("let xs = []\nxs = push(xs, 1i)\nxs = push(xs, 2i)\nprint(len(xs))")
        self.assertEqual(out, "2")


class StabilityOutputTests(unittest.TestCase):
    """BUG-131: stability output must not contain em-dashes (mojibake on Windows cp1252)."""

    def _stability_output(self):
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            _cli_main(["nodus", "stability"])
        finally:
            sys.stdout = old
        return buf.getvalue()

    def test_stability_has_no_em_dash(self):
        self.assertNotIn("—", self._stability_output())

    def test_stable_line_uses_ascii_separator(self):
        out = self._stability_output()
        stable_line = next(line for line in out.splitlines() if line.startswith("STABLE"))
        self.assertIn("--", stable_line)


if __name__ == "__main__":
    unittest.main()
