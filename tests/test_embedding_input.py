import unittest

from nodus.runtime.embedding import NodusRuntime
from nodus.runtime.errors import NodusRuntimeError, NodusSandboxError


class EmbeddingInputTests(unittest.TestCase):
    def test_input_blocked_by_default(self):
        runtime = NodusRuntime()
        with self.assertRaises(NodusSandboxError) as ctx:
            runtime.run_source('input("x")', filename="inline.nd")
        self.assertEqual(ctx.exception.error_type, "SandboxError")
        self.assertIn("input()", str(ctx.exception))

    def test_input_allowed_when_enabled(self):
        runtime = NodusRuntime(allow_input=True)
        runtime.register_function("host_input", lambda: "ok", arity=0)
        result = runtime.run_source('print(host_input())', filename="inline.nd")
        self.assertTrue(result["ok"])
        self.assertEqual(result["stdout"], "ok\n")


if __name__ == "__main__":
    unittest.main()
