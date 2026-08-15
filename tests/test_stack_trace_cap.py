"""Rendered stack traces are capped at 20 frames, on every path (#49).

The cap was implemented once, in `diagnostics.format_error`, and the issue was
closed on that evidence. The CLI renders through `errors.format_error_payload`
instead, which had no cap — so `nodus run` on a runaway recursion wrote **1.5 MB
of stderr across 10,003 lines** while the embedded path wrote 23. It got worse
after the fix, not better, because stack entries gained absolute paths (#342) and
every one of the 10,000 lines grew.

Both formatters now call `diagnostics.format_stack_section`, and the test that
matters is `test_both_formatters_render_the_same_section`: a cap added to one
renderer and not the other is exactly how this survived being "fixed". The same
split has bitten this repo before — the .nd formatter writer-vs-checker case in
CLAUDE.md, and the direct-builtin vs module-wrapper paths in #105.

The end-to-end test asserts the **rendered line count**, not just that the error
fires. Any test that only checked the message was blind to this bug.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.runtime.diagnostics import (  # noqa: E402
    MAX_TRACE_FRAMES,
    LangRuntimeError,
    format_error,
    format_stack_section,
)
from nodus.runtime.errors import format_error_payload  # noqa: E402

_NODUS_PY = str(_REPO_ROOT / "nodus.py")
_RUNAWAY = "fn recurse(n) { return recurse(n + 1i) }\nprint(recurse(0i))\n"


def _frames(n: int) -> list[str]:
    return ["at recurse (deep.nd:1:36)"] + [
        "called from recurse (deep.nd:1:36)" for _ in range(n - 1)
    ]


class StackSectionTests(unittest.TestCase):
    def test_short_stacks_are_rendered_whole(self):
        section = format_stack_section(_frames(3))
        self.assertEqual(3, section.count("deep.nd"))
        self.assertNotIn("more frames", section)

    def test_long_stacks_are_capped_with_a_count(self):
        section = format_stack_section(_frames(10_001))
        self.assertEqual(MAX_TRACE_FRAMES, section.count("deep.nd"))
        self.assertIn(f"... ({10_001 - MAX_TRACE_FRAMES} more frames)", section)

    def test_exactly_the_cap_is_not_elided(self):
        section = format_stack_section(_frames(MAX_TRACE_FRAMES))
        self.assertNotIn("more frames", section)

    def test_empty_stack_renders_nothing(self):
        self.assertEqual("", format_stack_section([]))
        self.assertEqual("", format_stack_section(None))


# closes: #49
class BothFormattersAgreeTests(unittest.TestCase):
    """The regression guard: one cap, not one cap per renderer."""

    def test_both_formatters_render_the_same_section(self):
        frames = _frames(10_001)

        err = LangRuntimeError("sandbox", "Call stack overflow")
        err.stack = frames
        from_diagnostics = format_error(err)

        from_payload = format_error_payload({
            "type": "sandbox",
            "message": "Call stack overflow",
            "stack": frames,
        })

        def section(text: str) -> str:
            head, sep, tail = text.partition("\nStack trace:\n")
            self.assertTrue(sep, f"no stack section rendered in {text[:200]!r}")
            return tail

        self.assertEqual(section(from_diagnostics), section(from_payload))

    def test_the_cli_payload_formatter_caps_at_all(self):
        # The half that was missing. Asserted on its own so a regression names
        # the renderer that broke rather than only the comparison.
        text = format_error_payload({
            "type": "sandbox",
            "message": "Call stack overflow",
            "stack": _frames(10_001),
        })
        self.assertEqual(MAX_TRACE_FRAMES, text.count("deep.nd"))
        self.assertIn("more frames", text)


# closes: #49
class CliOutputSizeTests(unittest.TestCase):
    def test_overflow_trace_is_not_a_megabyte_of_stderr(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".nd", delete=False,
                                         encoding="utf-8") as f:
            f.write(_RUNAWAY)
            path = f.name
        try:
            # --time-limit for headroom: the CLI's default deadline is 200ms and
            # building 10,000 frames takes longer, so without it the run dies
            # with "Execution timed out" and never reaches the overflow — which
            # is what makes this bug look fixed when it is not.
            proc = subprocess.run(
                [sys.executable, _NODUS_PY, "run", "--time-limit", "30", path],
                capture_output=True, text=True, timeout=120,
            )
        finally:
            Path(path).unlink()

        self.assertIn("Call stack overflow", proc.stderr)
        lines = proc.stderr.splitlines()
        # 1 error line + "Stack trace:" + 20 frames + 1 elision line = 23.
        self.assertLessEqual(len(lines), MAX_TRACE_FRAMES + 5,
                             f"{len(lines)} lines of stderr:\n{proc.stderr[:2000]}")
        self.assertLess(len(proc.stderr), 100_000,
                        f"{len(proc.stderr)} bytes of stderr (was ~1.5 MB)")
        self.assertIn("more frames", proc.stderr)


# closes: #49
class PayloadKeepsEveryFrameTests(unittest.TestCase):
    """Only the rendered text is capped; embedders still get the full list."""

    def test_embedded_error_stack_is_not_truncated(self):
        from nodus.runtime.embedding import NodusRuntime

        result = NodusRuntime(timeout_ms=None, max_steps=None).run_source(_RUNAWAY)
        self.assertFalse(result["ok"])
        stack = result["errors"][0]["stack"]
        self.assertIsNotNone(stack)
        self.assertGreater(len(stack), MAX_TRACE_FRAMES,
                           "the payload should keep every frame; only rendering caps")


if __name__ == "__main__":
    unittest.main()
