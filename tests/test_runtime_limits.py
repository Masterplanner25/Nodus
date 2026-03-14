import unittest

from nodus.tooling.runner import run_source


class RuntimeLimitTests(unittest.TestCase):
    def test_step_limit_triggered(self):
        result, _vm = run_source("while (true) { }", filename="inline.nd", max_steps=50)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["type"], "sandbox")
        self.assertEqual(result["errors"][0]["type"], "SandboxError")

    def test_time_limit_triggered(self):
        result, _vm = run_source("while (true) { }", filename="inline.nd", max_steps=None, timeout_ms=5)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["type"], "sandbox")
        self.assertEqual(result["errors"][0]["type"], "SandboxError")


if __name__ == "__main__":
    unittest.main()
