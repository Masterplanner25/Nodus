"""Every reason a coroutine can be parked is named in one place (#395, D4).

Six string literals lived in five modules and nothing related them. That is the
enumeration half of this codebase's recurring shape — one vocabulary, N
enumerations, one of them missing a member (#518's `_StateRewriter` without
`+=`, #487's four declaration-form sites where three had never heard of
`goal … over …`).

`cancel` is why it could not stay implicit. Cancelling a *parked* coroutine has
to unpark it, and an unpark that handles five of six reasons is a cancel that
silently hangs on the sixth — with no error, on whichever path is rarest. The
design record (`docs/design/v5/06-task-handle.md` D4/D5) requires the set to land
with, or before, the first verb that reads it.

The shape follows `TASK_STATUSES` / `JOIN_ON_STATES`: readable literals at the
assignment sites, one named tuple, and a test that reads the **source** and fails
when they disagree. A behavioural test cannot do this — it would have to provoke
every parking path, and the one nobody thought to provoke is exactly the one that
goes missing.
"""

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.coroutine import BLOCKED_REASON_SET, BLOCKED_REASONS  # noqa: E402

_SRC = Path(__file__).resolve().parents[1] / "src"

# `coroutine.blocked_reason = "..."` / `c.blocked_reason = "..."`, any receiver.
_ASSIGN_RE = re.compile(r"\.blocked_reason\s*=\s*[\"']([a-z_]+)[\"']")


def _assigned_reasons() -> dict[str, list[str]]:
    """Every string literal assigned to a `blocked_reason`, by file."""
    found: dict[str, list[str]] = {}
    for path in _SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for reason in _ASSIGN_RE.findall(text):
            found.setdefault(reason, []).append(str(path.relative_to(_SRC)))
    return found


# closes: #395
class VocabularyTests(unittest.TestCase):
    def test_the_set_has_no_duplicates(self):
        self.assertEqual(len(BLOCKED_REASONS), len(set(BLOCKED_REASONS)))
        self.assertEqual(set(BLOCKED_REASONS), set(BLOCKED_REASON_SET))

    def test_every_reason_assigned_in_src_is_named(self):
        """The direction that matters. A seventh parking path added without
        touching the tuple fails here rather than surfacing as a cancel that
        hangs."""
        unnamed = {
            reason: files for reason, files in _assigned_reasons().items()
            if reason not in BLOCKED_REASON_SET
        }
        self.assertEqual(
            {}, unnamed,
            "blocked_reason literal(s) not in BLOCKED_REASONS — add them to "
            "nodus/runtime/coroutine.py so anything that unparks a coroutine "
            "can be told the vocabulary grew",
        )

    def test_every_named_reason_except_task_join_is_assigned_somewhere(self):
        """The other direction: a reason nobody sets is dead vocabulary, and a
        cancel written against it is untested by construction.

        `task_join` is exempt only while `join` is unbuilt; when it lands this
        exemption goes with it.
        """
        assigned = set(_assigned_reasons())
        dead = sorted(set(BLOCKED_REASONS) - assigned - {"task_join"})
        self.assertEqual([], dead, "named blocked reason(s) nothing assigns")

    def test_the_six_pre_existing_reasons_are_present(self):
        """Pinned explicitly, because this is the set #395's D4 was written
        against and a silent shrink would be as bad as a silent growth."""
        for reason in ("channel_send", "channel_recv", "http_async",
                       "subprocess_async", "subprocess_wait_async", "agent_async"):
            self.assertIn(reason, BLOCKED_REASON_SET)


if __name__ == "__main__":
    unittest.main()
