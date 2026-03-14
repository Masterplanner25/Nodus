import unittest

from nodus.runtime.embedding import NodusRuntime


class EmbeddingApiTests(unittest.TestCase):
    def test_run_source_executes(self):
        rt = NodusRuntime()
        result = rt.run_source('print("hello")', filename="inline.nd")
        self.assertTrue(result["ok"])
        self.assertEqual(result["stdout"].strip(), "hello")

    def test_host_function_registration(self):
        rt = NodusRuntime()

        def add(a, b):
            return a + b

        rt.register_function("add", add)
        result = rt.run_source("print(add(2, 3))", filename="inline.nd")
        self.assertEqual(result["stdout"].strip(), "5")


if __name__ == "__main__":
    unittest.main()
