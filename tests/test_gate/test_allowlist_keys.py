"""Tests for nodus_gate allowlist keys.

Regression guard: the allowlist used to key suppressions by line number
(``block:<path>:<line>``). Any doc edit that inserted a line above a suppressed
block left the entry pointing at the wrong place, where it matched nothing and
suppressed nothing — silently, since a stale entry is not an error. Four
consecutive doc PRs had to re-point entries, and 11 dead entries accumulated
before anyone noticed.

Suppressions are now keyed by a hash of the block's normalized source
(``blockhash:<path>:<12-hex>``), which survives edits elsewhere in the file.
The line form is still accepted so existing allowlists keep working.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, "C:/dev/Coding Language")  # noqa: E402
sys.path.insert(0, "C:/dev/Coding Language/src")  # noqa: E402

from tools.nodus_gate.markdown_parser import extract_blocks  # noqa: E402


def _write(dirpath: str, name: str, content: str) -> str:
    path = os.path.join(dirpath, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


_DOC = """# Title

Intro paragraph.

```nodus
print("hello")
```

More prose.

```nodus
print("second")
```
"""

_DOC_SHIFTED = """# Title

Intro paragraph.

A NEW PARAGRAPH.

ANOTHER NEW PARAGRAPH.

```nodus
print("hello")
```

More prose.

```nodus
print("second")
```
"""


class ContentKeyStabilityTests(unittest.TestCase):
    """The whole point: the key must not move when the block does."""

    def test_content_key_survives_lines_inserted_above(self):
        with tempfile.TemporaryDirectory() as td:
            a = _write(td, "a.md", _DOC)
            first_before = extract_blocks(a)[0]
            key_before = first_before.content_key(td)
            line_before = first_before.line_key(td)

            _write(td, "a.md", _DOC_SHIFTED)
            first_after = extract_blocks(a)[0]

            self.assertEqual(key_before, first_after.content_key(td),
                             "content key changed after unrelated edit above the block")
            self.assertNotEqual(line_before, first_after.line_key(td),
                                "line key should have moved — otherwise this test proves nothing")

    def test_content_key_changes_when_the_block_itself_changes(self):
        """A suppression must stop applying when the code it excuses is edited."""
        with tempfile.TemporaryDirectory() as td:
            a = _write(td, "a.md", _DOC)
            before = extract_blocks(a)[0].content_key(td)
            _write(td, "a.md", _DOC.replace('print("hello")', 'print("goodbye")'))
            after = extract_blocks(a)[0].content_key(td)
            self.assertNotEqual(before, after)

    def test_distinct_blocks_get_distinct_keys(self):
        with tempfile.TemporaryDirectory() as td:
            a = _write(td, "a.md", _DOC)
            blocks = extract_blocks(a)
            self.assertNotEqual(blocks[0].content_key(td), blocks[1].content_key(td))

    def test_key_is_scoped_by_path(self):
        """Identical snippets in two files are suppressed independently."""
        with tempfile.TemporaryDirectory() as td:
            a = _write(td, "a.md", _DOC)
            b = _write(td, "b.md", _DOC)
            self.assertNotEqual(extract_blocks(a)[0].content_key(td),
                                extract_blocks(b)[0].content_key(td))


class ContentKeyNormalizationTests(unittest.TestCase):

    def test_line_ending_agnostic(self):
        """A CRLF vs LF checkout must not change the key."""
        with tempfile.TemporaryDirectory() as td:
            a = _write(td, "a.md", _DOC)
            lf = extract_blocks(a)[0].content_key(td)
            _write(td, "a.md", _DOC.replace("\n", "\r\n"))
            crlf = extract_blocks(a)[0].content_key(td)
            self.assertEqual(lf, crlf)

    def test_trailing_whitespace_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            a = _write(td, "a.md", _DOC)
            clean = extract_blocks(a)[0].content_key(td)
            _write(td, "a.md", _DOC.replace('print("hello")', 'print("hello")   '))
            trailing = extract_blocks(a)[0].content_key(td)
            self.assertEqual(clean, trailing)

    def test_key_shape(self):
        with tempfile.TemporaryDirectory() as td:
            a = _write(td, "a.md", _DOC)
            key = extract_blocks(a)[0].content_key(td)
            self.assertTrue(key.startswith("blockhash:a.md:"), key)
            self.assertEqual(len(key.rsplit(":", 1)[1]), 12)


class RuntimePhaseAcceptsBothFormsTests(unittest.TestCase):
    """Existing line-number allowlists must keep working during migration."""

    _FAILING = """# T

```nodus
this is not valid nodus @@@
```
"""

    def _run(self, allow_fn):
        """collect_doc_files only scans known doc dirs, so place the fixture in
        docs/guide/ rather than at the temp root — otherwise nothing is scanned
        and every assertion below passes vacuously."""
        from tools.nodus_gate.runtime_phase import run_runtime_phase
        with tempfile.TemporaryDirectory() as td:
            guide = os.path.join(td, "docs", "guide")
            os.makedirs(guide)
            path = _write(guide, "bad.md", self._FAILING)
            allow = allow_fn(td, path)
            return run_runtime_phase(td, allowlist=allow)

    def test_unsuppressed_block_fails(self):
        self.assertGreater(len(self._run(lambda td, p: set()).findings), 0,
                           "control case must fail, or the suppression tests prove nothing")

    def test_legacy_line_key_still_suppresses(self):
        r = self._run(lambda td, p: {"block:docs/guide/bad.md:3"})
        self.assertEqual(len(r.findings), 0)

    def test_content_key_suppresses(self):
        r = self._run(lambda td, p: {extract_blocks(p)[0].content_key(td)})
        self.assertEqual(len(r.findings), 0)


if __name__ == "__main__":
    unittest.main()
