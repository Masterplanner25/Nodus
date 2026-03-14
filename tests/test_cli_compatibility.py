import io
import json
import os
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout

import nodus as lang


class CliCompatibilityTests(unittest.TestCase):
    def test_cli_run_still_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "hello.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write('print("hello")\n')
            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "run", script])
            self.assertEqual(exit_code, 0)
            self.assertIn("hello", buf.getvalue())

    def test_cli_graph_command_outputs_plan(self):
        code = """
let A = task(fn() { return 1 }, nil)
let plan = plan_graph([A])
"""
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "graph.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write(code)
            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "graph", script])
            self.assertEqual(exit_code, 0)
            payload = json.loads(buf.getvalue().strip())
            self.assertIn("graph_id", payload)
            self.assertIn("nodes", payload)

    def test_cli_test_examples_command(self):
        exit_code = lang.main(["nodus", "test-examples"])
        self.assertEqual(exit_code, 0)

    def test_cli_serve_command_starts(self):
        def run_server():
            lang.main(["nodus", "serve", "--host", "127.0.0.1", "--port", "0"])

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()
        time.sleep(0.05)
        self.assertTrue(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
