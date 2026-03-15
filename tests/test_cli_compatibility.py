import io
import json
import os
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout

import nodus as lang
from nodus.services.server import run_in_thread


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
            lang.main(["nodus", "serve", "--host", "127.0.0.1", "--port", "0", "--allow-paths", "."])

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()
        time.sleep(0.05)
        self.assertTrue(thread.is_alive())

    def test_cli_snapshot_restore_worker_auth_token(self):
        token = "cli-token"
        server, thread = run_in_thread("127.0.0.1", 0, allowed_paths=["."], auth_token=token)
        port = server.server_address[1]
        try:
            time.sleep(0.05)
            os.environ["NODUS_SERVER_TOKEN"] = token
            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "snapshot", "dummy", "--host", "127.0.0.1", "--port", str(port)])
            self.assertEqual(exit_code, 1)

            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "snapshot", "dummy", "--host", "127.0.0.1", "--port", str(port), "--auth-token", token])
            self.assertEqual(exit_code, 1)

            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "snapshots", "--host", "127.0.0.1", "--port", str(port), "--auth-token", token])
            self.assertEqual(exit_code, 0)

            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "restore", "dummy", "--host", "127.0.0.1", "--port", str(port), "--auth-token", token])
            self.assertEqual(exit_code, 1)

            os.environ["NODUS_SERVER_TOKEN"] = "wrong-token"
            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "snapshots", "--host", "127.0.0.1", "--port", str(port)])
            self.assertEqual(exit_code, 1)

            os.environ["NODUS_SERVER_TOKEN"] = token
            def run_worker():
                try:
                    lang.main(["nodus", "worker", "--host", "127.0.0.1", "--port", str(port)])
                except Exception:
                    return

            worker_thread = threading.Thread(target=run_worker, daemon=True)
            worker_thread.start()
            time.sleep(0.05)
            self.assertTrue(worker_thread.is_alive())
        finally:
            os.environ.pop("NODUS_SERVER_TOKEN", None)
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
