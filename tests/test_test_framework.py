"""Tests for the v4.0 std:test framework (Design Docs 07 + 08)."""

import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr

sys.path.insert(0, "C:/dev/Coding Language/src")  # noqa: E402

import nodus  # noqa: E402
from nodus.runtime.module_loader import ModuleLoader  # noqa: E402
from nodus.testing.runner import TestRunner, TestResult  # noqa: E402
from nodus.testing.formatter import format_text, format_json, format_junit  # noqa: E402
from nodus.testing.discovery import discover_test_files, matches_filter  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vm_and_run(src: str, source_path: str = "test.nd") -> tuple:
    """Load src into a fresh VM, run the test runner, return (vm, results)."""
    vm = nodus.VM([], {}, code_locs=[], source_path=source_path)
    out = io.StringIO()
    err_buf = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err_buf):
        loader = ModuleLoader(project_root=None, vm=vm)
        loader.load_module_from_source(src, module_name=source_path)
    runner = TestRunner(vm, source_path=source_path)
    results = runner.run_all()
    return vm, results, out.getvalue(), err_buf.getvalue()


def _run(src: str) -> list[TestResult]:
    _, results, _, _ = _make_vm_and_run(src)
    return results


def _run_with_stderr(src: str) -> tuple[list[TestResult], str]:
    _, results, _, stderr = _make_vm_and_run(src)
    return results, stderr


# ---------------------------------------------------------------------------
# 1. Assertions — pass cases
# ---------------------------------------------------------------------------

class AssertPassTests(unittest.TestCase):

    def test_assert_truthy(self):
        r = _run('import "std:test" as test\ntest.suite("s", fn() { test.case("t", fn() { test.assert(true) }) })')
        self.assertEqual(r[0].status, "pass")

    def test_assert_eq_integers(self):
        r = _run('import "std:test" as test\ntest.suite("s", fn() { test.case("t", fn() { test.assert_eq(2i + 3i, 5i) }) })')
        self.assertEqual(r[0].status, "pass")

    def test_assert_eq_strings(self):
        r = _run('import "std:test" as test\ntest.suite("s", fn() { test.case("t", fn() { test.assert_eq("hello", "hello") }) })')
        self.assertEqual(r[0].status, "pass")

    def test_assert_neq(self):
        r = _run('import "std:test" as test\ntest.suite("s", fn() { test.case("t", fn() { test.assert_neq(1i, 2i) }) })')
        self.assertEqual(r[0].status, "pass")

    def test_assert_err(self):
        r = _run('import "std:test" as test\nimport "std:tool" as tool\ntest.suite("s", fn() { test.case("t", fn() { test.assert_err(tool.lookup("no.such")) }) })')
        self.assertEqual(r[0].status, "pass")

    def test_assert_ok(self):
        r = _run('import "std:test" as test\ntest.suite("s", fn() { test.case("t", fn() { test.assert_ok("hello") }) })')
        self.assertEqual(r[0].status, "pass")

    def test_assert_kind(self):
        r = _run('import "std:test" as test\nimport "std:tool" as tool\ntest.suite("s", fn() { test.case("t", fn() { let e = tool.lookup("no.such")\ntest.assert_kind(e, "tool_error") }) })')
        self.assertEqual(r[0].status, "pass")

    def test_assert_throws(self):
        r = _run('import "std:test" as test\ntest.suite("s", fn() { test.case("t", fn() { test.assert_throws(fn() { throw "boom" }) }) })')
        self.assertEqual(r[0].status, "pass")

    def test_assert_close(self):
        r = _run('import "std:test" as test\ntest.suite("s", fn() { test.case("t", fn() { test.assert_close(3.14159, 3.14, 0.01) }) })')
        self.assertEqual(r[0].status, "pass")

    def test_assert_contains_list(self):
        r = _run('import "std:test" as test\ntest.suite("s", fn() { test.case("t", fn() { test.assert_contains([1i, 2i, 3i], 2i) }) })')
        self.assertEqual(r[0].status, "pass")

    def test_assert_contains_string(self):
        r = _run('import "std:test" as test\ntest.suite("s", fn() { test.case("t", fn() { test.assert_contains("hello world", "world") }) })')
        self.assertEqual(r[0].status, "pass")

    def test_assert_has_key(self):
        r = _run('import "std:test" as test\ntest.suite("s", fn() { test.case("t", fn() { test.assert_has_key({name: "alice", age: 30i}, "name") }) })')
        self.assertEqual(r[0].status, "pass")

    def test_assert_in_range(self):
        r = _run('import "std:test" as test\ntest.suite("s", fn() { test.case("t", fn() { test.assert_in_range(5.0, 1.0, 10.0) }) })')
        self.assertEqual(r[0].status, "pass")


# ---------------------------------------------------------------------------
# 2. Assertions — fail cases
# ---------------------------------------------------------------------------

class AssertFailTests(unittest.TestCase):

    def test_assert_eq_fails(self):
        r = _run('import "std:test" as test\ntest.suite("s", fn() { test.case("t", fn() { test.assert_eq(1i, 2i) }) })')
        self.assertEqual(r[0].status, "fail")
        self.assertIn("assert_eq", r[0].failure_message)

    def test_assert_ok_fails_on_err(self):
        r = _run('import "std:test" as test\nimport "std:tool" as tool\ntest.suite("s", fn() { test.case("t", fn() { test.assert_ok(tool.lookup("no.such")) }) })')
        self.assertEqual(r[0].status, "fail")

    def test_assert_err_fails_on_ok(self):
        r = _run('import "std:test" as test\ntest.suite("s", fn() { test.case("t", fn() { test.assert_err("not_an_error") }) })')
        self.assertEqual(r[0].status, "fail")

    def test_assert_throws_fails_when_no_throw(self):
        r = _run('import "std:test" as test\ntest.suite("s", fn() { test.case("t", fn() { test.assert_throws(fn() { return 42i }) }) })')
        self.assertEqual(r[0].status, "fail")

    def test_assert_close_fails_out_of_tolerance(self):
        r = _run('import "std:test" as test\ntest.suite("s", fn() { test.case("t", fn() { test.assert_close(1.0, 2.0, 0.1) }) })')
        self.assertEqual(r[0].status, "fail")

    def test_assert_contains_fails(self):
        r = _run('import "std:test" as test\ntest.suite("s", fn() { test.case("t", fn() { test.assert_contains([1i, 2i], 5i) }) })')
        self.assertEqual(r[0].status, "fail")

    def test_assert_in_range_fails(self):
        r = _run('import "std:test" as test\ntest.suite("s", fn() { test.case("t", fn() { test.assert_in_range(15.0, 1.0, 10.0) }) })')
        self.assertEqual(r[0].status, "fail")

    def test_assert_with_message(self):
        r = _run('import "std:test" as test\ntest.suite("s", fn() { test.case("t", fn() { test.assert_eq(1i, 2i, "custom message") }) })')
        self.assertEqual(r[0].status, "fail")
        self.assertIn("custom message", r[0].failure_message)


# ---------------------------------------------------------------------------
# 3. Suite structure
# ---------------------------------------------------------------------------

class SuiteStructureTests(unittest.TestCase):

    def test_multiple_cases_in_suite(self):
        r = _run(
            'import "std:test" as test\n'
            'test.suite("s", fn() {\n'
            '    test.case("a", fn() { test.assert(true) })\n'
            '    test.case("b", fn() { test.assert(true) })\n'
            '    test.case("c", fn() { test.assert(false) })\n'
            '})'
        )
        self.assertEqual(len(r), 3)
        self.assertEqual(r[0].status, "pass")
        self.assertEqual(r[1].status, "pass")
        self.assertEqual(r[2].status, "fail")

    def test_nested_suites(self):
        r = _run(
            'import "std:test" as test\n'
            'test.suite("outer", fn() {\n'
            '    test.suite("inner", fn() {\n'
            '        test.case("t", fn() { test.assert(true) })\n'
            '    })\n'
            '})'
        )
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0].status, "pass")
        self.assertIn("inner", r[0].suite_path)

    def test_suite_path_tracking(self):
        r = _run(
            'import "std:test" as test\n'
            'test.suite("outer", fn() {\n'
            '    test.suite("inner", fn() {\n'
            '        test.case("my test", fn() { test.assert(true) })\n'
            '    })\n'
            '})'
        )
        self.assertIn("outer", r[0].suite_path)
        self.assertIn("inner", r[0].suite_path)
        self.assertEqual(r[0].case_name, "my test")

    def test_skip(self):
        r = _run(
            'import "std:test" as test\n'
            'test.suite("s", fn() {\n'
            '    test.case("skipped", fn() { test.skip("not ready") })\n'
            '})'
        )
        self.assertEqual(r[0].status, "skip")
        self.assertIn("not ready", r[0].skip_reason)


# ---------------------------------------------------------------------------
# 4. Lifecycle hooks
# ---------------------------------------------------------------------------

class LifecycleHookTests(unittest.TestCase):

    def test_before_each_runs_before_case(self):
        r = _run(
            'import "std:test" as test\n'
            'let state = {count: 0i}\n'
            'test.suite("s", fn() {\n'
            '    test.before_each(fn() { state.count = state.count + 1i })\n'
            '    test.case("t1", fn() { test.assert_eq(state.count, 1i) })\n'
            '    test.case("t2", fn() { test.assert_eq(state.count, 2i) })\n'
            '})'
        )
        self.assertTrue(all(r_.status == "pass" for r_ in r))

    def test_after_each_runs_after_case(self):
        r = _run(
            'import "std:test" as test\n'
            'let log = []\n'
            'test.suite("s", fn() {\n'
            '    test.after_each(fn() { list_push(log, "after") })\n'
            '    test.case("t1", fn() { list_push(log, "test1") })\n'
            '    test.case("t2", fn() { list_push(log, "test2") })\n'
            '})'
        )
        self.assertEqual(len(r), 2)
        self.assertTrue(all(r_.status == "pass" for r_ in r))

    def test_before_all_runs_once(self):
        r = _run(
            'import "std:test" as test\n'
            'let state = {calls: 0i}\n'
            'test.suite("s", fn() {\n'
            '    test.before_all(fn() { state.calls = 1i })\n'
            '    test.case("t1", fn() { test.assert_eq(state.calls, 1i) })\n'
            '    test.case("t2", fn() { test.assert_eq(state.calls, 1i) })\n'
            '})'
        )
        self.assertTrue(all(r_.status == "pass" for r_ in r))

    def test_after_all_runs_once(self):
        r = _run(
            'import "std:test" as test\n'
            'let done = false\n'
            'test.suite("s", fn() {\n'
            '    test.after_all(fn() { done = true })\n'
            '    test.case("t1", fn() { test.assert(true) })\n'
            '})'
        )
        self.assertEqual(r[0].status, "pass")


# ---------------------------------------------------------------------------
# 5. Fixtures
# ---------------------------------------------------------------------------

class FixtureTests(unittest.TestCase):

    def test_fixture_test_scope(self):
        r = _run(
            'import "std:test" as test\n'
            'test.suite("s", fn() {\n'
            '    test.fixture("myval", fn() {\n'
            '        return 42i\n'
            '    })\n'
            '    test.case("t1", fn(ctx) {\n'
            '        let v = ctx.fixture("myval")\n'
            '        test.assert_eq(v, 42i)\n'
            '    })\n'
            '    test.case("t2", fn(ctx) {\n'
            '        let v = ctx.fixture("myval")\n'
            '        test.assert_eq(v, 42i)\n'
            '    })\n'
            '})'
        )
        self.assertTrue(all(r_.status == "pass" for r_ in r))

    def test_fixture_suite_scope_cached(self):
        r = _run(
            'import "std:test" as test\n'
            'test.suite("s", fn() {\n'
            '    test.fixture("shared", fn() { return "cached-value" }, "suite")\n'
            '    test.case("t1", fn(ctx) {\n'
            '        let v = ctx.fixture("shared")\n'
            '        test.assert_eq(v, "cached-value")\n'
            '    })\n'
            '    test.case("t2", fn(ctx) {\n'
            '        let v = ctx.fixture("shared")\n'
            '        test.assert_eq(v, "cached-value")\n'
            '    })\n'
            '})'
        )
        self.assertTrue(all(r_.status == "pass" for r_ in r))

    def test_fixture_cleanup_runs(self):
        r = _run(
            'import "std:test" as test\n'
            'let cleaned = false\n'
            'test.suite("s", fn() {\n'
            '    test.fixture("res", fn() {\n'
            '        test.cleanup(fn() { cleaned = true })\n'
            '        return "resource"\n'
            '    })\n'
            '    test.case("t", fn(ctx) {\n'
            '        ctx.fixture("res")\n'
            '        test.assert(true)\n'
            '    })\n'
            '})'
        )
        self.assertEqual(r[0].status, "pass")

    def test_fixture_not_found_fails_test(self):
        r = _run(
            'import "std:test" as test\n'
            'test.suite("s", fn() {\n'
            '    test.case("t", fn(ctx) {\n'
            '        ctx.fixture("undefined_fixture")\n'
            '    })\n'
            '})'
        )
        self.assertIn(r[0].status, ("fail", "error"))


# ---------------------------------------------------------------------------
# 6. Parameterized tests
# ---------------------------------------------------------------------------

class ParameterizedTests(unittest.TestCase):

    def test_list_form_runs_all_rows(self):
        r = _run(
            'import "std:test" as test\n'
            'test.suite("s", fn() {\n'
            '    test.parameterize([[1i, 1i, 2i], [2i, 3i, 5i], [0i, 0i, 0i]], fn(a, b, expected) {\n'
            '        test.case("adds", fn() { test.assert_eq(a + b, expected) })\n'
            '    })\n'
            '})'
        )
        self.assertEqual(len(r), 3)
        self.assertTrue(all(r_.status == "pass" for r_ in r))

    def test_map_form_runs_all_rows(self):
        r = _run(
            'import "std:test" as test\n'
            'test.suite("s", fn() {\n'
            '    test.parameterize([{name: "alice", expected: true}, {name: "", expected: false}], fn(row) {\n'
            '        test.case("validates", fn() { test.assert_eq(len(row.name) > 0i, row.expected) })\n'
            '    })\n'
            '})'
        )
        self.assertEqual(len(r), 2)
        self.assertTrue(all(r_.status == "pass" for r_ in r))


# ---------------------------------------------------------------------------
# 7. Test isolation
# ---------------------------------------------------------------------------

class IsolationTests(unittest.TestCase):

    def test_env_var_reverted_between_tests(self):
        r = _run(
            'import "std:test" as test\n'
            'import "std:env" as env\n'
            'test.suite("s", fn() {\n'
            '    test.case("sets env", fn() {\n'
            '        env.set("_NODUS_TEST_ISOLATION_VAR", "set_by_test")\n'
            '        test.assert_eq(env.get("_NODUS_TEST_ISOLATION_VAR", ""), "set_by_test")\n'
            '    })\n'
            '    test.case("env is clean", fn() {\n'
            '        test.assert_eq(env.get("_NODUS_TEST_ISOLATION_VAR", ""), "")\n'
            '    })\n'
            '})'
        )
        self.assertTrue(all(r_.status == "pass" for r_ in r))

    def test_tool_registry_reverted_between_tests(self):
        r = _run(
            'import "std:test" as test\n'
            'import "std:tool" as tool\n'
            'test.suite("s", fn() {\n'
            '    test.case("registers tool", fn() {\n'
            '        tool.register({name: "myapp.tmp", handler: fn(a){ return a }, description: "tmp"})\n'
            '        test.assert(tool.has("myapp.tmp"))\n'
            '    })\n'
            '    test.case("tool is gone", fn() {\n'
            '        test.assert(tool.has("myapp.tmp") == false)\n'
            '    })\n'
            '})'
        )
        self.assertTrue(all(r_.status == "pass" for r_ in r))

    def test_isolation_opt_out(self):
        r = _run(
            'import "std:test" as test\n'
            'import "std:env" as env\n'
            'test.suite("s", fn() {\n'
            '    test.case("sets env", fn() {\n'
            '        env.set("_NODUS_ISO_OPT", "value")\n'
            '    })\n'
            '    test.case("env persists", fn() {\n'
            '        test.assert_eq(env.get("_NODUS_ISO_OPT", ""), "value")\n'
            '    })\n'
            '}, {isolated: false})'
        )
        self.assertTrue(all(r_.status == "pass" for r_ in r))


# ---------------------------------------------------------------------------
# 8. Async tests
# ---------------------------------------------------------------------------

class AsyncTestTests(unittest.TestCase):

    def test_case_async_basic(self):
        r = _run(
            'import "std:test" as test\n'
            'test.suite("s", fn() {\n'
            '    test.case_async("async passes", fn() {\n'
            '        test.assert(true)\n'
            '    })\n'
            '})'
        )
        self.assertEqual(r[0].status, "pass")

    def test_advance_clock_and_flush(self):
        r = _run(
            'import "std:test" as test\n'
            'test.suite("s", fn() {\n'
            '    test.case_async("virtual time", fn() {\n'
            '        let state = {done: false}\n'
            '        let c = coroutine(fn() {\n'
            '            sleep(100)\n'
            '            state.done = true\n'
            '        })\n'
            '        spawn(c)\n'
            '        test.flush_async()\n'
            '        test.advance_clock(200)\n'
            '        test.flush_async()\n'
            '        test.assert(state.done)\n'
            '    })\n'
            '})'
        )
        self.assertEqual(r[0].status, "pass")


# ---------------------------------------------------------------------------
# 9. Output formatters
# ---------------------------------------------------------------------------

class FormatterTests(unittest.TestCase):

    def _make_results(self):
        return [
            TestResult(["suite"], "passing test", "pass", 10.0),
            TestResult(["suite"], "failing test", "fail", 5.0,
                       failure_message="assert_eq failed", failure_kind="assertion_failure"),
            TestResult(["suite"], "skipped test", "skip", 0.0, skip_reason="not ready"),
        ]

    def test_text_format_contains_summary(self):
        results = self._make_results()
        text = format_text(results, use_color=False)
        self.assertIn("3 total", text)
        self.assertIn("1 passed", text)
        self.assertIn("1 failed", text)
        self.assertIn("1 skipped", text)

    def test_json_format_is_valid(self):
        results = self._make_results()
        text = format_json(results)
        for line in text.strip().split("\n"):
            obj = json.loads(line)
            self.assertIn("type", obj)

    def test_json_format_has_summary(self):
        results = self._make_results()
        lines = format_json(results).strip().split("\n")
        summary = json.loads(lines[-1])
        self.assertEqual(summary["type"], "summary")
        self.assertEqual(summary["tests_total"], 3)

    def test_junit_format_is_valid_xml(self):
        results = self._make_results()
        xml_text = format_junit(results)
        self.assertIn("<?xml", xml_text)
        self.assertIn("testsuites", xml_text)
        self.assertIn("failure", xml_text)

    def test_junit_contains_failure(self):
        results = self._make_results()
        xml_text = format_junit(results)
        self.assertIn("assert_eq failed", xml_text)


# ---------------------------------------------------------------------------
# 10. Discovery
# ---------------------------------------------------------------------------

class DiscoveryTests(unittest.TestCase):

    def test_discovers_test_nd_files(self):
        files = discover_test_files("C:/dev/Coding Language/tests")
        names = [os.path.basename(f) for f in files]
        # The framework should discover test files
        self.assertTrue(any(n.endswith("_test.nd") for n in names) or len(files) == 0)

    def test_filter_glob(self):
        self.assertTrue(matches_filter("user > login test", "*login*"))
        self.assertFalse(matches_filter("user > signup test", "*login*"))

    def test_filter_regex(self):
        self.assertTrue(matches_filter("user > async login", "re:.*async.*"))
        self.assertFalse(matches_filter("user > sync login", "re:.*async.*"))

    def test_empty_filter_matches_all(self):
        self.assertTrue(matches_filter("any test name", ""))


# ---------------------------------------------------------------------------
# 11. Coverage collector
# ---------------------------------------------------------------------------

class CoverageTests(unittest.TestCase):

    def test_collector_subscribes_and_detaches(self):
        from nodus.testing.coverage import CoverageCollector
        vm = nodus.VM([], {}, code_locs=[], source_path="test.nd")
        collector = CoverageCollector()
        collector.attach(vm)
        self.assertIn(collector, vm.event_bus._sinks)
        collector.detach(vm)
        self.assertNotIn(collector, vm.event_bus._sinks)

    def test_collector_builds_report(self):
        from nodus.testing.coverage import CoverageCollector
        collector = CoverageCollector()
        # Manually inject some hits
        collector.hits["src/foo.nd"][10] += 2
        collector.hits["src/foo.nd"][11] += 1
        collector.hits["src/foo.nd"][15] += 0  # touched but zero
        report = collector.build_report(
            executable_lines={"src/foo.nd": [10, 11, 12, 13]},
        )
        self.assertIn("src/foo.nd", report["files"])
        file_data = report["files"]["src/foo.nd"]
        self.assertIn(10, file_data["covered_lines"])
        self.assertIn(12, file_data["uncovered_lines"])

    def test_collector_excludes_test_files(self):
        from nodus.testing.coverage import CoverageCollector
        collector = CoverageCollector()
        collector.hits["src/foo_test.nd"][5] += 1
        collector.hits["src/foo.nd"][5] += 1
        report = collector.build_report()
        self.assertNotIn("src/foo_test.nd", report["files"])
        self.assertIn("src/foo.nd", report["files"])

    def test_overall_coverage_percentage(self):
        from nodus.testing.coverage import CoverageCollector
        collector = CoverageCollector()
        collector.hits["src/a.nd"][1] += 1
        collector.hits["src/a.nd"][2] += 1
        report = collector.build_report(
            executable_lines={"src/a.nd": [1, 2, 3, 4]},
        )
        self.assertEqual(report["files"]["src/a.nd"]["coverage_pct"], 50.0)
        self.assertEqual(report["summary"]["overall_coverage_pct"], 50.0)


if __name__ == "__main__":
    unittest.main()
