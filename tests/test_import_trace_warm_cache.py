"""`--trace-imports` must describe the import graph on every run (#348).

`ModuleLoader._build_metadata` returns early when the on-disk bytecode cache
hits, and `resolve_import` — the only place the trace is emitted — sits after
that return. So the flag printed **nothing at all** once `.nodus/` was warm,
which is every run after the first: it worked only on the run you are least
likely to be debugging.

Distinct from #51, which was the in-memory cache within a single run and is
fixed. This is the cross-run disk cache, so the tests run the CLI **twice** —
the bug is invisible to anything that only looks at one run, which is how it
survived long enough to be recorded as finding F27 and never filed.

The cached path reports provenance (`Resolved (from bytecode cache)`) rather
than pretending it re-resolved: someone debugging resolution needs to know
whether a path was resolved on this run or recorded on an earlier one. Nothing is
re-resolved and nothing is re-parsed — tracing must not change what a run does.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

_NODUS_PY = str(_REPO_ROOT / "nodus.py")

_TRACE_PREFIX = "[import] "
_CACHED_MARK = "Resolved (from bytecode cache)"


class ImportTraceTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def write_project(self, files: dict) -> None:
        for name, body in files.items():
            (self.project / name).write_text(body, encoding="utf-8")

    def run_traced(self) -> list[str]:
        """Run `main.nd` with --trace-imports; return the trace lines only."""
        proc = subprocess.run(
            [sys.executable, _NODUS_PY, "run", "--trace-imports", "main.nd"],
            capture_output=True, text=True, timeout=60, cwd=str(self.project),
            env={"PYTHONPATH": str(_REPO_ROOT / "src"),
                 "SYSTEMROOT": "C:\\Windows", "PATH": ""},
        )
        self.assertEqual(0, proc.returncode, f"run failed:\n{proc.stderr}")
        self.assertIn("ok", proc.stdout, f"program did not run:\n{proc.stdout}")
        return [ln for ln in proc.stderr.splitlines() if ln.startswith(_TRACE_PREFIX)]

    def cache_exists(self) -> bool:
        return (self.project / ".nodus").exists()


# closes: #348
class WarmCacheStillTracesTests(ImportTraceTestCase):
    _CHAIN = {
        "deep.nd": 'export fn deep() { return "ok" }\n',
        "helper.nd": 'import "./deep" as d\nexport fn hi() { return d.deep() }\n',
        "main.nd": 'import "./helper" as h\nprint(h.hi())\n',
    }

    def test_cold_run_traces_every_edge(self):
        # Guard: the cold path already worked and must keep working.
        self.write_project(self._CHAIN)
        lines = self.run_traced()
        self.assertTrue(any('"./helper"' in ln for ln in lines), lines)
        self.assertTrue(any('"./deep"' in ln for ln in lines), lines)

    def test_warm_run_traces_at_all(self):
        # The bug: the second run printed nothing.
        self.write_project(self._CHAIN)
        self.run_traced()
        self.assertTrue(self.cache_exists(), "first run did not write .nodus/")
        warm = self.run_traced()
        self.assertNotEqual([], warm, "warm run emitted no trace output")

    def test_warm_run_reports_the_whole_graph_including_transitive_imports(self):
        self.write_project(self._CHAIN)
        self.run_traced()
        warm = self.run_traced()
        self.assertTrue(any('"./helper"' in ln for ln in warm), warm)
        self.assertTrue(any('"./deep"' in ln for ln in warm),
                        f"transitive import missing from warm trace:\n{warm}")

    def test_warm_run_reports_the_same_edges_as_the_cold_run(self):
        self.write_project(self._CHAIN)
        cold = self.run_traced()
        warm = self.run_traced()

        def edges(lines: list[str]) -> set[str]:
            return {ln.split('"', 1)[1] for ln in lines if "Resolved" in ln and '"' in ln}

        self.assertEqual(edges(cold), edges(warm),
                         f"cold:\n{cold}\nwarm:\n{warm}")

    def test_warm_lines_say_where_the_path_came_from(self):
        self.write_project(self._CHAIN)
        self.run_traced()
        warm = self.run_traced()
        resolved = [ln for ln in warm if "Resolved" in ln]
        self.assertTrue(resolved, warm)
        for line in resolved:
            self.assertIn(_CACHED_MARK, line,
                          "a warm-cache line claims it resolved the path itself")

    def test_a_diamond_reports_the_shared_dependency_from_both_importers(self):
        self.write_project({
            "shared.nd": "export fn v() { return 1i }\n",
            "a.nd": 'import "./shared" as s\nexport fn a() { return s.v() }\n',
            "b.nd": 'import "./shared" as s\nexport fn b() { return s.v() }\n',
            "main.nd": 'import "./a" as a\nimport "./b" as b\n'
                       'if (a.a() + b.b() == 2i) { print("ok") }\n',
        })
        cold = self.run_traced()
        warm = self.run_traced()
        for name, lines in (("cold", cold), ("warm", warm)):
            shared = [ln for ln in lines if '"./shared"' in ln]
            self.assertEqual(2, len(shared),
                             f"{name}: expected one line per importer, got:\n{lines}")


# closes: #348
class TracingChangesNothingTests(ImportTraceTestCase):
    _CHAIN = WarmCacheStillTracesTests._CHAIN

    def test_no_trace_output_without_the_flag(self):
        self.write_project(self._CHAIN)
        for _ in range(2):  # cold then warm
            proc = subprocess.run(
                [sys.executable, _NODUS_PY, "run", "main.nd"],
                capture_output=True, text=True, timeout=60, cwd=str(self.project),
                env={"PYTHONPATH": str(_REPO_ROOT / "src"),
                     "SYSTEMROOT": "C:\\Windows", "PATH": ""},
            )
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertEqual("ok\n", proc.stdout)
            self.assertNotIn(_TRACE_PREFIX, proc.stderr)

    def test_the_program_result_is_identical_with_and_without_tracing(self):
        self.write_project(self._CHAIN)
        self.run_traced()  # warm the cache
        traced = subprocess.run(
            [sys.executable, _NODUS_PY, "run", "--trace-imports", "main.nd"],
            capture_output=True, text=True, timeout=60, cwd=str(self.project),
            env={"PYTHONPATH": str(_REPO_ROOT / "src"),
                 "SYSTEMROOT": "C:\\Windows", "PATH": ""},
        )
        plain = subprocess.run(
            [sys.executable, _NODUS_PY, "run", "main.nd"],
            capture_output=True, text=True, timeout=60, cwd=str(self.project),
            env={"PYTHONPATH": str(_REPO_ROOT / "src"),
                 "SYSTEMROOT": "C:\\Windows", "PATH": ""},
        )
        self.assertEqual(plain.stdout, traced.stdout)
        self.assertEqual(plain.returncode, traced.returncode)


if __name__ == "__main__":
    unittest.main()
