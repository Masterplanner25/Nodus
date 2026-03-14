import unittest

from nodus.tooling.runner import disassemble_source


class DisassemblySerializationTests(unittest.TestCase):
    def test_disassembly_structured_output(self):
        result = disassemble_source("print(1)", filename="inline.nd")
        self.assertTrue(result["ok"])
        self.assertIn("dis_pretty", result)
        self.assertIn("dis", result)
        self.assertIsInstance(result["dis_pretty"], list)
        self.assertIsInstance(result["dis"], list)
        self.assertTrue(result["dis"])
        opcodes = {entry["opcode"] for entry in result["dis"]}
        self.assertIn("CALL", opcodes)
        self.assertTrue(any("line" in entry and "column" in entry for entry in result["dis"]))


if __name__ == "__main__":
    unittest.main()
