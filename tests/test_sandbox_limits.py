import unittest

from nodus.tooling.runner import run_source


class SandboxLimitTests(unittest.TestCase):
    def test_step_limit(self):
        result, _vm = run_source("while (true) { }", filename="inline.nd", max_steps=50)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["type"], "sandbox")
        self.assertEqual(result["errors"][0]["type"], "SandboxError")

    def test_stdout_limit(self):
        result, _vm = run_source('print("hello")', filename="inline.nd", max_stdout_chars=1)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["type"], "sandbox")
        self.assertEqual(result["errors"][0]["type"], "SandboxError")


if __name__ == "__main__":
    unittest.main()
