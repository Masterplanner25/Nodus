"""Tests for BUG-050: cyclic workflow dependency must exit with ok=False."""

import unittest

from nodus.tooling.runner import run_workflow_code
from nodus.vm.vm import VM


_CYCLIC_SRC = """
workflow cyclic {
    step a after b {
        return b + 1
    }
    step b after a {
        return a + 1
    }
}
run_workflow(cyclic)
"""

_LINEAR_SRC = """
workflow linear {
    step first {
        return 1
    }
    step second after first {
        return first + 1
    }
}
run_workflow(linear)
"""


def _run_workflow(src: str) -> dict:
    vm = VM([], {}, code_locs=[], source_path=None)
    result, _ = run_workflow_code(vm, src, max_steps=50_000, timeout_ms=5_000)
    return result


class CyclicWorkflowTests(unittest.TestCase):
    """BUG-050: cyclic dependency must produce ok=False, not silently succeed."""

    def test_cyclic_workflow_returns_ok_false(self):
        result = _run_workflow(_CYCLIC_SRC)
        self.assertFalse(result["ok"], f"expected ok=False, got: {result}")

    def test_cyclic_workflow_result_contains_error_info(self):
        result = _run_workflow(_CYCLIC_SRC)
        self.assertFalse(result["ok"])
        self.assertIn("errors", result)

    def test_linear_workflow_still_succeeds(self):
        """Regression: non-cyclic workflow must still return ok=True."""
        result = _run_workflow(_LINEAR_SRC)
        self.assertTrue(result["ok"], f"expected ok=True, got: {result}")

    def test_three_step_cycle_returns_ok_false(self):
        src = """
workflow tri {
    step a after c {
        return c
    }
    step b after a {
        return a
    }
    step c after b {
        return b
    }
}
run_workflow(tri)
"""
        result = _run_workflow(src)
        self.assertFalse(result["ok"], f"expected ok=False, got: {result}")
