"""#907: `nodus run` shows output as the program writes it.

It used to collect the program's stdout in a buffer (`capture_output`, which
enforces `--output-limit`) and print it when the program ended. So:

- a long-running program showed no progress at all;
- a killed run lost everything it had printed;
- stdout landed after stderr, so an error appeared before lines printed earlier.

Every test here runs a real `nodus run` in a subprocess, because each defect
was about what a separate process sees, and an in-process capture would hide
all three.
"""

import io
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))  # noqa: E402

from nodus.runtime.diagnostics import RuntimeLimitExceeded  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.tooling.sandbox import StreamingLimitedWriter  # noqa: E402

_SLOW = """
fn work() {
    print("first")
    sleep(1500i)
    print("second")
}
spawn(work)
run_loop()
"""


def _script(tmp: str, source: str) -> str:
    path = os.path.join(tmp, "prog.nd")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(textwrap.dedent(source))
    return path


def _popen(tmp: str, path: str, *flags: str, merge: bool = False) -> subprocess.Popen:
    env = dict(os.environ, PYTHONPATH=str(REPO / "src"))
    return subprocess.Popen(
        [sys.executable, str(REPO / "nodus.py"), "run", "--time-limit", "60", *flags, path],
        cwd=tmp, env=env, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT if merge else subprocess.PIPE, text=True)


class OutputArrivesAsItIsWrittenTests(unittest.TestCase):

    # closes: #907
    def test_a_line_arrives_while_the_program_is_still_running(self):
        """The program sleeps 1.5 s between its two lines, so a streamed first
        line arrives well before the process exits. Collected, both arrive
        together at exit. Measured as a time gap, not with `poll()`: a process
        whose output has just been flushed at exit can still report itself
        running for a moment, which let a `poll()` version pass unfixed."""
        with tempfile.TemporaryDirectory() as tmp:
            proc = _popen(tmp, _script(tmp, _SLOW))
            try:
                first = proc.stdout.readline()
                first_at = time.monotonic()
                rest, _err = proc.communicate(timeout=60)
                exited_at = time.monotonic()
            finally:
                if proc.poll() is None:
                    proc.kill()
        self.assertEqual("first\n", first)
        self.assertEqual("second\n", rest)
        self.assertGreater(exited_at - first_at, 1.0,
                           "the first line came only when the program exited")

    def test_a_killed_run_keeps_what_it_printed(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = _popen(tmp, _script(tmp, _SLOW))
            try:
                first = proc.stdout.readline()
                proc.kill()
                rest, _err = proc.communicate(timeout=60)
            finally:
                if proc.poll() is None:
                    proc.kill()
        self.assertEqual("first\n", first)
        self.assertNotIn("second", rest)

    def test_stdout_and_stderr_keep_their_order_on_one_pipe(self):
        """A pipe makes Python block-buffer stdout until exit, while stderr is
        written at once -- the second half of the ordering defect, which
        streaming without flushing would have kept."""
        source = """
            print("before")
            spawn(fn() { throw "boom" })
            run_loop()
            print("after")
            """
        with tempfile.TemporaryDirectory() as tmp:
            proc = _popen(tmp, _script(tmp, source), merge=True)
            out, _ = proc.communicate(timeout=60)
        before, error, after = out.index("before"), out.index("boom"), out.index("after")
        self.assertLess(before, error, out)
        self.assertLess(error, after, out)

    def test_nothing_is_printed_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = _popen(tmp, _script(tmp, 'print("once")\n'))
            out, err = proc.communicate(timeout=60)
        self.assertEqual("once\n", out)
        self.assertEqual("", err)


class TheLimitStillHoldsTests(unittest.TestCase):

    def test_output_limit_stops_the_program_and_keeps_what_fit(self):
        source = """
            let i = 0i
            while (i < 100i) {
                print("line \\(i)")
                i += 1i
            }
            """
        with tempfile.TemporaryDirectory() as tmp:
            proc = _popen(tmp, _script(tmp, source), "--output-limit", "30")
            out, err = proc.communicate(timeout=60)
        self.assertNotEqual(0, proc.returncode)
        self.assertIn("stdout limit exceeded", err)
        self.assertTrue(out.startswith("line 0\nline 1\n"), out)
        self.assertLessEqual(len(out), 30)
        self.assertNotIn("line 99", out)


class WhatDoesNotStreamTests(unittest.TestCase):

    def test_the_embedded_runtime_still_returns_stdout_as_a_value(self):
        result = NodusRuntime(timeout_ms=None, max_steps=None).run_source('print("collected")\n')
        self.assertEqual("collected\n", result["stdout"])

    def test_dump_bytecode_prints_its_disassembly_before_the_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = _popen(tmp, _script(tmp, 'print("program output")\n'), "--dump-bytecode")
            out, err = proc.communicate(timeout=60)
        self.assertEqual(0, proc.returncode, err)
        self.assertIn("program output", out)
        self.assertGreater(out.index("program output"), 0)
        self.assertTrue(out.rstrip().endswith("program output"), out[-300:])


class TheWriterTests(unittest.TestCase):

    def test_text_a_console_cannot_encode_falls_back_to_utf8_bytes(self):
        class Cp1252Console(io.TextIOWrapper):
            pass

        raw = io.BytesIO()
        console = Cp1252Console(raw, encoding="cp1252", errors="strict", write_through=True)
        writer = StreamingLimitedWriter(console)
        writer.write("ok ✓\n")
        self.assertEqual("ok ✓\n".encode("utf-8"), raw.getvalue())

    def test_the_count_is_the_limit_not_the_last_write(self):
        sink = io.StringIO()
        writer = StreamingLimitedWriter(sink, max_chars=5)
        writer.write("abc")
        with self.assertRaises(RuntimeLimitExceeded):
            writer.write("def")
        self.assertEqual("abc", sink.getvalue())
        self.assertEqual("", writer.getvalue())


if __name__ == "__main__":
    unittest.main()
