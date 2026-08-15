"""`NodusRuntime` must apply a call-depth cap by default (#350).

`configure_vm_limits` installs `MAX_STACK_DEPTH`, and `embedding.py` then
overwrote it unconditionally with `self.max_frames` — `None` by default, which
means *no cap*. The docstring promised the opposite. With the default
`max_steps` a runaway recursion still died on the step limit, so the hole only
showed in the configuration `EMBEDDING.md` recommends for long-lived hosts,
`max_steps=None, timeout_ms=None`: no step limit, no deadline, and no frame cap.
VM frames are heap-allocated, so Python's own recursion limit never fires and
the process grows until it is killed.

Per the security-boundary rule in CLAUDE.md, both contexts are covered: the CLI
already capped correctly and is tested here to keep the two from drifting again.

The recursion cases run in **subprocesses with timeouts** on purpose. If the cap
regresses, the run does not raise — it grows without bound, and an in-process
test would hang CI instead of failing it.
"""

import json
import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.support.config import MAX_STACK_DEPTH  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402

_NODUS_PY = str(_REPO_ROOT / "nodus.py")
_RUNAWAY = "fn recurse(n) { return recurse(n + 1i) }\nrecurse(0i)\n"


def _child_env() -> dict:
    env = dict(os.environ)
    src = str(_REPO_ROOT / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src + (os.pathsep + existing if existing else "")
    return env


def run_embedded_out_of_process(source: str, **runtime_kwargs) -> dict:
    """Run `source` under NodusRuntime in a child process and return its result.

    Bounded by a timeout so a regressed cap fails the test instead of hanging it.
    """
    program = textwrap.dedent("""
        import json, sys
        from nodus.runtime.embedding import NodusRuntime
        kwargs = json.loads(sys.argv[1])
        source = sys.argv[2]
        rt = NodusRuntime(**kwargs)
        result = rt.run_source(source)
        print("__RESULT__" + json.dumps({
            "ok": result["ok"],
            "messages": [e["message"] for e in result["errors"]],
            "max_frames": rt._last_vm.max_frames,
        }))
    """)
    proc = subprocess.run(
        [sys.executable, "-c", program, json.dumps(runtime_kwargs), source],
        capture_output=True, text=True, timeout=30, env=_child_env(),
    )
    for line in proc.stdout.splitlines():
        if line.startswith("__RESULT__"):
            return json.loads(line[len("__RESULT__"):])
    raise AssertionError(
        f"child produced no result (rc={proc.returncode})\n"
        f"stdout={proc.stdout[-2000:]!r}\nstderr={proc.stderr[-2000:]!r}"
    )


# closes: #350
class EmbeddedDefaultFrameCapTests(unittest.TestCase):
    def test_default_runtime_installs_max_stack_depth(self):
        rt = NodusRuntime()
        rt.run_source("print(1)")
        self.assertEqual(MAX_STACK_DEPTH, rt._last_vm.max_frames)

    def test_runaway_recursion_raises_under_the_recommended_server_config(self):
        # max_steps=None, timeout_ms=None is what EMBEDDING.md recommends for
        # long-lived hosts, and was the one configuration with no guard at all.
        result = run_embedded_out_of_process(
            _RUNAWAY, timeout_ms=None, max_steps=None
        )
        self.assertFalse(result["ok"])
        self.assertIn("Call stack overflow", result["messages"])
        self.assertEqual(MAX_STACK_DEPTH, result["max_frames"])

    def test_explicit_cap_still_overrides_the_default(self):
        result = run_embedded_out_of_process(
            _RUNAWAY, timeout_ms=None, max_steps=None, max_frames=200
        )
        self.assertFalse(result["ok"])
        self.assertIn("Call stack overflow", result["messages"])
        self.assertEqual(200, result["max_frames"])

    def test_a_large_explicit_cap_allows_deeper_recursion_than_the_default(self):
        # Proves the default is a real cap being applied, not a hardcoded ceiling:
        # 20,001 frames is twice MAX_STACK_DEPTH and completes when asked for.
        result = run_embedded_out_of_process(
            "fn f(n) { if (n > 20000i) { return n } return f(n + 1i) }\nprint(f(0i))\n",
            timeout_ms=None, max_steps=None, max_frames=10_000_000,
        )
        self.assertTrue(result["ok"], result["messages"])

    def test_default_cap_is_below_that_depth(self):
        result = run_embedded_out_of_process(
            "fn f(n) { if (n > 20000i) { return n } return f(n + 1i) }\nprint(f(0i))\n",
            timeout_ms=None, max_steps=None,
        )
        self.assertFalse(result["ok"])
        self.assertIn("Call stack overflow", result["messages"])

    def test_per_call_override_is_honored(self):
        rt = NodusRuntime(timeout_ms=None, max_steps=None)
        result = rt.run_source(_RUNAWAY, max_frames=150)
        self.assertFalse(result["ok"])
        self.assertIn("Call stack overflow",
                      [e["message"] for e in result["errors"]])
        self.assertEqual(150, rt._last_vm.max_frames)

    def test_a_later_default_run_is_not_left_with_the_override(self):
        rt = NodusRuntime(timeout_ms=None, max_steps=None)
        rt.run_source("print(1)", max_frames=150)
        rt.run_source("print(2)")
        self.assertEqual(MAX_STACK_DEPTH, rt._last_vm.max_frames)


# closes: #350
class CliFrameCapTests(unittest.TestCase):
    """The CLI already capped correctly; asserted so the two cannot drift."""

    def test_nodus_run_reports_call_stack_overflow(self):
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".nd", delete=False,
                                         encoding="utf-8") as f:
            f.write(_RUNAWAY)
            path = f.name
        try:
            proc = subprocess.run(
                [sys.executable, _NODUS_PY, "run", path],
                capture_output=True, text=True, timeout=60, env=_child_env(),
            )
        finally:
            Path(path).unlink()
        self.assertNotEqual(0, proc.returncode)
        self.assertIn("Call stack overflow", proc.stderr)

    def test_runner_path_applies_max_stack_depth(self):
        from nodus.tooling.runner import run_source as runner_run_source
        result, vm = runner_run_source(_RUNAWAY, filename="inline.nd",
                                       max_steps=None, timeout_ms=None)
        self.assertFalse(result["ok"])
        self.assertEqual("sandbox", result["error"]["type"])
        self.assertEqual(MAX_STACK_DEPTH, vm.max_frames)


if __name__ == "__main__":
    unittest.main()
