"""Doc 15: cyclic workflow returns err record, not plain dict."""

import io
import task_graph
import unittest
from contextlib import redirect_stderr, redirect_stdout

import nodus as lang
from nodus.runtime.module_loader import ModuleLoader
from nodus.vm.vm import Record


def run_program(src: str, source_path: str = "test.nd"):
    _loader = ModuleLoader(project_root=None)
    code, functions, code_locs = _loader.compile_only(src, module_name=source_path)
    vm = lang.VM(code, functions, code_locs=code_locs, source_path=source_path)
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    with redirect_stdout(out_buf), redirect_stderr(err_buf):
        vm.run()
    return vm, out_buf.getvalue().splitlines(), err_buf.getvalue()


class CyclicWorkflowErrRecordTests(unittest.TestCase):

    def _cyclic_result(self, src: str):
        vm, _out, _err = run_program(src)
        result = vm.globals.get("result")
        if hasattr(result, "value"):
            result = result.value
        return result

    def test_cyclic_workflow_returns_err_record(self):
        src = """
workflow cyclic {
    step a after b { return b + 1 }
    step b after a { return a + 1 }
}
let result = run_workflow(cyclic)
"""
        result = self._cyclic_result(src)
        self.assertIsInstance(result, Record)
        self.assertEqual(result.kind, "error")

    def test_cyclic_workflow_err_kind_is_workflow_error(self):
        src = """
workflow cyclic {
    step a after b { return b + 1 }
    step b after a { return a + 1 }
}
let result = run_workflow(cyclic)
"""
        result = self._cyclic_result(src)
        self.assertEqual(result.fields["kind"], "workflow_error")

    def test_cyclic_workflow_err_message_contains_cycle(self):
        src = """
workflow cyclic {
    step a after b { return b + 1 }
    step b after a { return a + 1 }
}
let result = run_workflow(cyclic)
"""
        result = self._cyclic_result(src)
        msg = result.fields["message"]
        self.assertIn("cycle", msg.lower())

    def test_cyclic_workflow_payload_category(self):
        src = """
workflow cyclic {
    step a after b { return b + 1 }
    step b after a { return a + 1 }
}
let result = run_workflow(cyclic)
"""
        result = self._cyclic_result(src)
        payload = result.fields["payload"]
        self.assertIsNotNone(payload)
        self.assertEqual(payload["category"], "cyclic_workflow")

    def test_cyclic_workflow_payload_includes_cycle_steps(self):
        src = """
workflow cyclic {
    step a after b { return b + 1 }
    step b after a { return a + 1 }
}
let result = run_workflow(cyclic)
"""
        result = self._cyclic_result(src)
        cycle = result.fields["payload"]["cycle"]
        self.assertIsInstance(cycle, list)
        self.assertTrue(len(cycle) >= 2)
        self.assertTrue(all(name in ("a", "b") for name in cycle))

    def test_cyclic_workflow_payload_workflow_name(self):
        src = """
workflow cyclic {
    step a after b { return b + 1 }
    step b after a { return a + 1 }
}
let result = run_workflow(cyclic)
"""
        result = self._cyclic_result(src)
        self.assertEqual(result.fields["payload"]["workflow_name"], "cyclic")

    def test_cyclic_workflow_err_has_location_fields(self):
        """The CALL_BUILTIN wrapper augments err records with path/line/column/stack/origin."""
        src = """
workflow cyclic {
    step a after b { return b + 1 }
    step b after a { return a + 1 }
}
let result = run_workflow(cyclic)
"""
        result = self._cyclic_result(src)
        self.assertIn("path", result.fields)
        self.assertIn("line", result.fields)
        self.assertIn("column", result.fields)
        self.assertIn("stack", result.fields)
        self.assertIn("origin", result.fields)

    def test_cyclic_workflow_origin_is_stdlib(self):
        src = """
workflow cyclic {
    step a after b { return b + 1 }
    step b after a { return a + 1 }
}
let result = run_workflow(cyclic)
"""
        result = self._cyclic_result(src)
        self.assertEqual(result.fields["origin"], "stdlib")

    def test_three_step_cycle_returns_err_record(self):
        src = """
workflow tri {
    step a after c { return c }
    step b after a { return a }
    step c after b { return b }
}
let result = run_workflow(tri)
"""
        result = self._cyclic_result(src)
        self.assertIsInstance(result, Record)
        self.assertEqual(result.kind, "error")
        self.assertEqual(result.fields["kind"], "workflow_error")
        cycle = result.fields["payload"]["cycle"]
        self.assertTrue(len(cycle) >= 3)

    def test_three_step_cycle_message_mentions_steps(self):
        src = """
workflow tri {
    step a after c { return c }
    step b after a { return a }
    step c after b { return b }
}
let result = run_workflow(tri)
"""
        result = self._cyclic_result(src)
        msg = result.fields["message"]
        # At least one of the step names should appear in the cycle message
        self.assertTrue(
            any(name in msg for name in ("a", "b", "c")),
            f"Expected step name in message: {msg!r}",
        )

    def test_nodus_script_can_check_err_kind(self):
        """Nodus script can inspect the err record kind field via dot notation."""
        src = """
workflow cyclic {
    step a after b { return b + 1 }
    step b after a { return a + 1 }
}
let result = run_workflow(cyclic)
print(result.kind)
"""
        _vm, out, _err = run_program(src)
        self.assertIn("workflow_error", out)

    def test_nodus_script_can_check_err_category(self):
        src = """
workflow cyclic {
    step a after b { return b + 1 }
    step b after a { return a + 1 }
}
let result = run_workflow(cyclic)
print(result.payload["category"])
"""
        _vm, out, _err = run_program(src)
        self.assertIn("cyclic_workflow", out)

    def test_linear_workflow_returns_dict_not_err(self):
        """Regression: a non-cyclic workflow must not return err."""
        src = """
workflow linear {
    step a { return 1 }
    step b after a { return a + 1 }
}
let result = run_workflow(linear)
print(result["steps"]["b"])
"""
        _vm, out, _err = run_program(src)
        self.assertEqual(out, ["2.0"])

    def test_cyclic_workflow_cli_mode(self):
        """run_workflow_code returns ok=False for cyclic workflows."""
        import tempfile
        import os
        from nodus.tooling.runner import run_workflow_code
        src = """
workflow cyclic {
    step a after b { return b + 1 }
    step b after a { return a + 1 }
}
"""
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "cyclic.nd")
            with open(path, "w", encoding="utf-8") as f:
                f.write(src)
            vm = lang.VM([], {}, code_locs=[], source_path=path)
            result, _vm = run_workflow_code(vm, src, filename=path)
            self.assertFalse(result["ok"])
            self.assertIn("errors", result)

    def test_cyclic_workflow_api_endpoint(self):
        """HTTP /workflow/run returns ok=False + error for cyclic workflows."""
        import http.client
        import json
        import time
        from nodus.services.server import run_in_thread

        server, _thread = run_in_thread("127.0.0.1", 0, allowed_paths=["."])
        port = server.server_address[1]
        time.sleep(0.05)
        try:
            code = """
workflow cyclic {
    step a after b { return b + 1 }
    step b after a { return a + 1 }
}
"""
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            body = json.dumps({"code": code, "filename": "inline.nd"})
            conn.request("POST", "/workflow/run", body=body,
                         headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            data = json.loads(resp.read().decode("utf-8"))
            conn.close()
            self.assertEqual(resp.status, 200)
            self.assertFalse(data["ok"])
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
