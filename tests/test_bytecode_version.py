import unittest

from nodus.runtime.errors import BytecodeVersionError
from nodus.vm.vm import VM


class BytecodeVersionTests(unittest.TestCase):
    def test_bytecode_version_mismatch(self):
        with self.assertRaises(BytecodeVersionError):
            VM({"bytecode_version": 999, "instructions": []}, {}, code_locs=[])


if __name__ == "__main__":
    unittest.main()
