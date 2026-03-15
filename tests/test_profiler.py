import io
import json
import os
import tempfile
import time
import unittest
from contextlib import redirect_stdout

import nodus as lang
from nodus.runtime.profiler import Profiler


class ProfilerTests(unittest.TestCase):
    def test_profiler_records_opcodes(self):
        profiler = Profiler()
        profiler.start()
        profiler.record_opcode("LOAD_CONST")
        profiler.record_opcode("LOAD_CONST")
        profiler.record_opcode("ADD")
        profiler.stop()
        self.assertEqual(profiler.opcode_counts.get("LOAD_CONST"), 2)
        self.assertEqual(profiler.opcode_counts.get("ADD"), 1)

    def test_profiler_counts_function_calls(self):
        profiler = Profiler()
        profiler.start()
        profiler.record_function_call("main")
        profiler.record_function_call("main")
        profiler.record_function_call("process")
        profiler.stop()
        self.assertEqual(profiler.function_calls.get("main"), 2)
        self.assertEqual(profiler.function_calls.get("process"), 1)

    def test_profiler_records_time(self):
        profiler = Profiler()
        profiler.start()
        profiler.enter_function("main")
        time.sleep(0.001)
        profiler.exit_function("main")
        profiler.stop()
        report = profiler.report()
        self.assertGreaterEqual(report.get("total_time_ms", 0.0), 0.0)
        functions = report.get("functions", [])
        main_entry = next((item for item in functions if item.get("name") == "main"), None)
        self.assertIsNotNone(main_entry)
        self.assertGreaterEqual(main_entry.get("time_ms", 0.0), 0.0)

    def test_cli_profile_command(self):
        code = """
fn add(a, b) {
    return a + b
}

add(1, 2)
"""
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "profile.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write(code)

            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "profile", script])
            self.assertEqual(exit_code, 0)
            output = buf.getvalue()
            self.assertIn("Nodus Profiling Report", output)

            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "profile", script, "--json"])
            self.assertEqual(exit_code, 0)
            payload = json.loads(buf.getvalue().strip())
            self.assertIn("runtime_ms", payload)
            self.assertIn("functions", payload)
            self.assertIn("opcodes", payload)


if __name__ == "__main__":
    unittest.main()
