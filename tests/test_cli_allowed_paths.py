import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

import nodus as lang


class CliAllowedPathsTests(unittest.TestCase):
    def test_cli_run_allow_paths_flag(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "read.nd")
            data = os.path.join(td, "data.txt")
            with open(data, "w", encoding="utf-8") as handle:
                handle.write("ok")
            data_literal = data.replace("\\", "\\\\")
            with open(script, "w", encoding="utf-8") as handle:
                handle.write(f'print(read_file("{data_literal}"))\n')
            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "run", script, "--allow-paths", td])
            self.assertEqual(exit_code, 0)
            self.assertIn("ok", buf.getvalue())

    def test_cli_run_allow_paths_env(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "read.nd")
            data = os.path.join(td, "data.txt")
            with open(data, "w", encoding="utf-8") as handle:
                handle.write("ok")
            data_literal = data.replace("\\", "\\\\")
            with open(script, "w", encoding="utf-8") as handle:
                handle.write(f'print(read_file("{data_literal}"))\n')
            buf = io.StringIO()
            os.environ["NODUS_ALLOWED_PATHS"] = td
            try:
                with redirect_stdout(buf):
                    exit_code = lang.main(["nodus", "run", script])
            finally:
                os.environ.pop("NODUS_ALLOWED_PATHS", None)
            self.assertEqual(exit_code, 0)
            self.assertIn("ok", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
