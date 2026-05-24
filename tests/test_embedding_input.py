import unittest

from nodus.runtime.embedding import NodusRuntime


class EmbeddingInputTests(unittest.TestCase):
    def test_input_blocked_by_default(self):
        runtime = NodusRuntime()
        result = runtime.run_source('input("x")', filename="inline.nd")
        self.assertFalse(result["ok"])
        err = result.get("error") or {}
        self.assertIn(err.get("type", ""), {"SandboxError", "sandbox"})
        self.assertIn("input()", err.get("message", ""))

    def test_input_allowed_when_enabled(self):
        runtime = NodusRuntime(allow_input=True)
        runtime.register_function("host_input", lambda: "ok", arity=0)
        result = runtime.run_source('print(host_input())', filename="inline.nd")
        self.assertTrue(result["ok"])
        self.assertEqual(result["stdout"], "ok\n")


if __name__ == "__main__":
    unittest.main()
