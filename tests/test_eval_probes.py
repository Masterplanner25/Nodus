"""The three `.nd` eval probes run in the suite, not only at a release (#815).

`tests/eval/quirk_probe.nd`, `language_exerciser.nd` and
`framework_capabilities.nd` are Tier 1 language smoke tests: between them they
exercise closures, recursion, control flow, the numeric tower, strings and
interpolation, lists, maps, records and methods, JSON round-trip, coroutines and
channels, and every documented quirk. Each ends by printing a sentinel.

Nothing ran them. `grep` for their names finds `.claude/commands/release-prep.md`
and `docs/evals/EVAL_PREPUBLISH.md` and nothing else, so a language
regression they would catch stayed invisible until somebody cut a release --
which is #811's complaint about the *other* release-only harness in this same
directory, `release_claims_probe.py`.

The difference, and why this one is cheap where #811's is a real trade-off:
those probes need a built wheel and a clean venv outside the repo, because they
validate an *installed* package. These three validate the *language*, so dev
source is the right target and the root `nodus.py` shim already loads it. Three
subprocesses, about a second each, almost all of it Python startup -- they run
under the default 200 ms VM budget today.

Two things this file deliberately does not do by hand:

* **The sentinel is read out of the probe, not restated here.** Each script
  declares `// SUCCESS CONTRACT: prints "X"` in its header; the runner parses
  that line. A hardcoded copy would be a second enumeration of one fact, which
  is the shape this project keeps filing issues about -- and it would let the
  script's contract and the test's expectation drift apart silently.
* **It proves it can fail.** `HarnessFalsifiabilityTests` runs a probe built to
  fail through the same helper and asserts it is reported red. #815 is open
  precisely because `quirk_probe.nd` has sections whose assertion is a comment,
  so they cannot go red in any arrangement of the language; a test file about
  that had better not have the same property.

Note what these probes cover that `tests/` does not: `framework_capabilities.nd`
P1 calls straight off a map index (`routes["/"]()`), and P10 drives coroutines
over a channel. Neither has a Python-side equivalent.
"""

import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
NODUS_PY = REPO / "nodus.py"
EVAL_DIR = pathlib.Path(__file__).resolve().parent / "eval"

PROBES = ("quirk_probe", "language_exerciser", "framework_capabilities")

#: `nodus run` bounds the whole program at `EXECUTION_TIMEOUT_MS` (200 ms) unless
#: told otherwise, and an `import` is charged to that budget because the import
#: compiles the module during the run -- which is how `test_cross_module_closure`
#: went red on CI with nothing else wrong (#711). All three probes import stdlib
#: modules and all three fit in the default budget on this box, but a cold runner
#: pays the compiler's own lazy imports inside the window. The rule from that
#: issue is to put the limit on the harness rather than on whichever probe
#: happens to go red, so it is here and it is generous; a genuine hang is caught
#: by the subprocess timeout below, not by this.
TIME_LIMIT_SECONDS = 30
SUBPROCESS_TIMEOUT_SECONDS = 180

_CONTRACT = re.compile(r'^//\s*SUCCESS CONTRACT:.*?"([^"]+)"', re.MULTILINE)


def probe_path(name: str) -> pathlib.Path:
    return EVAL_DIR / f"{name}.nd"


def declared_sentinel(source: str) -> str:
    """The success string a probe's own header promises it prints.

    Raising rather than returning a default is the point: a probe that stops
    declaring a contract must fail the suite, not quietly become unchecked.
    """
    match = _CONTRACT.search(source)
    if match is None:
        raise AssertionError(
            "no `// SUCCESS CONTRACT: ... \"<sentinel>\"` header line found"
        )
    return match.group(1)


def run_probe(script: pathlib.Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        [
            sys.executable,
            str(NODUS_PY),
            "run",
            str(script),
            "--time-limit",
            str(TIME_LIMIT_SECONDS),
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
    )
    return proc.returncode, proc.stdout, proc.stderr


def assert_probe_passes(case: unittest.TestCase, script: pathlib.Path) -> None:
    source = script.read_text(encoding="utf-8")
    sentinel = declared_sentinel(source)
    code, out, err = run_probe(script)
    detail = f"\n--- stdout ---\n{out}\n--- stderr ---\n{err}"
    case.assertEqual(code, 0, f"{script.name} exited {code}{detail}")
    case.assertIn(
        sentinel,
        out,
        f"{script.name} did not print its declared success contract "
        f"{sentinel!r}{detail}",
    )


class EvalProbeTests(unittest.TestCase):
    """Each probe still passes against dev source."""

    def test_quirk_probe_passes(self):
        assert_probe_passes(self, probe_path("quirk_probe"))

    def test_language_exerciser_passes(self):
        assert_probe_passes(self, probe_path("language_exerciser"))

    def test_framework_capabilities_passes(self):
        assert_probe_passes(self, probe_path("framework_capabilities"))


class SuccessContractTests(unittest.TestCase):
    """The declared contract has to be real, or reading it off is worthless."""

    def test_every_probe_exists(self):
        for name in PROBES:
            with self.subTest(probe=name):
                self.assertTrue(
                    probe_path(name).is_file(),
                    f"{name}.nd is missing; if it was renamed, update PROBES",
                )

    def test_every_probe_declares_a_success_contract(self):
        for name in PROBES:
            with self.subTest(probe=name):
                declared_sentinel(probe_path(name).read_text(encoding="utf-8"))

    def test_the_declared_sentinel_is_one_the_probe_actually_prints(self):
        """A header naming a string no `print` emits would never fail, and never pass.

        This is the cheap half of the same question #815 asks about the probes'
        own commented-out traps: does the assertion have anything behind it.
        """
        for name in PROBES:
            with self.subTest(probe=name):
                source = probe_path(name).read_text(encoding="utf-8")
                sentinel = declared_sentinel(source)
                self.assertIn(
                    f'print("{sentinel}")',
                    source,
                    f"{name}.nd promises to print {sentinel!r} but no `print` "
                    f"in it emits that string",
                )

    def test_every_eval_nd_script_is_covered(self):
        """A fourth probe added to `tests/eval/` must be wired in, not just added.

        The failure this closes is the quiet one: a new probe that nothing runs
        looks exactly like the three that nothing ran.
        """
        on_disk = {path.stem for path in EVAL_DIR.glob("*.nd")}
        self.assertEqual(
            on_disk,
            set(PROBES),
            "tests/eval/*.nd and PROBES disagree; add the new probe to PROBES",
        )


class HarnessFalsifiabilityTests(unittest.TestCase):
    """The runner reports a red probe as red.

    Written because the issue this file answers (#815) is about assertions that
    could not fail. A green run of `EvalProbeTests` is evidence about the
    language only if these pass.
    """

    def _write(self, body: str) -> pathlib.Path:
        tmpdir = tempfile.mkdtemp()
        script = pathlib.Path(tmpdir) / "probe.nd"
        script.write_text(body, encoding="utf-8")
        self.addCleanup(script.unlink)
        return script

    def test_a_probe_whose_checks_fail_is_reported(self):
        script = self._write(
            '// SUCCESS CONTRACT: prints "ALL FAKE PROBES PASSED".\n'
            'let state = record {failures: 0}\n'
            'fn main() {\n'
            '    state.failures = state.failures + 1\n'
            '    if (state.failures == 0) {\n'
            '        print("ALL FAKE PROBES PASSED")\n'
            '    } else {\n'
            '        print("FAKE PROBE FAILURES")\n'
            '    }\n'
            '}\n'
            'main()\n'
        )
        with self.assertRaises(AssertionError):
            assert_probe_passes(self, script)

    def test_a_probe_that_raises_is_reported(self):
        script = self._write(
            '// SUCCESS CONTRACT: prints "ALL FAKE PROBES PASSED".\n'
            'fn main() {\n'
            '    let bad = "n=" + 5\n'
            '    print("ALL FAKE PROBES PASSED")\n'
            '}\n'
            'main()\n'
        )
        with self.assertRaises(AssertionError):
            assert_probe_passes(self, script)

    def test_a_probe_with_no_declared_contract_is_reported(self):
        script = self._write('print("hello")\n')
        with self.assertRaises(AssertionError):
            assert_probe_passes(self, script)

    def test_the_helper_passes_a_genuinely_green_probe(self):
        """The control. Without it the three above pass for any broken helper."""
        script = self._write(
            '// SUCCESS CONTRACT: prints "ALL FAKE PROBES PASSED".\n'
            'fn main() {\n'
            '    print("ALL FAKE PROBES PASSED")\n'
            '}\n'
            'main()\n'
        )
        assert_probe_passes(self, script)


if __name__ == "__main__":
    unittest.main()
