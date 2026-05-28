"""Tests for the v4.0 tool registry (Design Doc 06)."""

import io
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr

sys.path.insert(0, "C:/dev/Coding Language/src")  # noqa: E402

import nodus  # noqa: E402
from nodus.runtime.module_loader import ModuleLoader  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(src: str, *, capture_stderr: bool = False):
    """Execute Nodus source and return (stdout_lines, stderr_lines)."""
    vm = nodus.VM([], {}, code_locs=[], source_path="test.nd")
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        loader = ModuleLoader(project_root=None, vm=vm)
        loader.load_module_from_source(src, module_name="test.nd")
    return out.getvalue().splitlines(), err.getvalue()


def _run_vm(src: str):
    """Execute Nodus source, return (vm, stdout_lines, stderr_lines)."""
    vm = nodus.VM([], {}, code_locs=[], source_path="test.nd")
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        loader = ModuleLoader(project_root=None, vm=vm)
        loader.load_module_from_source(src, module_name="test.nd")
    return vm, out.getvalue().splitlines(), err.getvalue()


def _run_val(src: str):
    """Run a source snippet that prints one line; return that line."""
    lines, _ = _run(src)
    return lines[0] if lines else ""


def _is_error_record(value) -> bool:
    from nodus.vm.vm import Record
    return isinstance(value, Record) and value.kind == "error"


# ---------------------------------------------------------------------------
# 1. Registration (Nodus-side)
# ---------------------------------------------------------------------------

class RegistrationTests(unittest.TestCase):

    def test_minimal_registration(self):
        lines, _ = _run(
            'import "std:tool" as tool\n'
            'let t = tool.register({name: "myapp.greet", handler: fn(a){ return a }, description: "Greet"})\n'
            'print(t.name)'
        )
        self.assertEqual(lines[0], "myapp.greet")

    def test_registered_tool_visible_in_has(self):
        lines, _ = _run(
            'import "std:tool" as tool\n'
            'tool.register({name: "myapp.greet", handler: fn(a){ return a }, description: "Greet"})\n'
            'print(tool.has("myapp.greet"))'
        )
        self.assertEqual(lines[0], "true")

    def test_has_returns_false_for_unknown(self):
        lines, _ = _run(
            'import "std:tool" as tool\n'
            'print(tool.has("does.not.exist"))'
        )
        self.assertEqual(lines[0], "false")

    def test_full_metadata_registration(self):
        lines, _ = _run(
            'import "std:tool" as tool\n'
            'let t = tool.register({\n'
            '    name: "mcp.call_tool",\n'
            '    handler: fn(a){ return a },\n'
            '    description: "Call a tool",\n'
            '    version: "0.1.0",\n'
            '    tags: ["mcp", "protocol"],\n'
            '    deprecated: false,\n'
            '    metadata: {protocol: "mcp"}\n'
            '})\n'
            'print(t.version)'
        )
        self.assertEqual(lines[0], "0.1.0")

    def test_registration_conflict_returns_err(self):
        lines, _ = _run(
            'import "std:tool" as tool\n'
            'tool.register({name: "myapp.foo", handler: fn(a){ return a }, description: "First"})\n'
            'let r = tool.register({name: "myapp.foo", handler: fn(a){ return a }, description: "Second"})\n'
            'print(type(r))\n'
            'print(r.payload["category"])'
        )
        self.assertEqual(lines[0], "error")
        self.assertEqual(lines[1], "registration_conflict")

    def test_invalid_metadata_missing_handler(self):
        lines, _ = _run(
            'import "std:tool" as tool\n'
            'let r = tool.register({name: "myapp.foo", description: "No handler"})\n'
            'print(type(r))\n'
            'print(r.payload["category"])'
        )
        self.assertEqual(lines[0], "error")
        self.assertEqual(lines[1], "invalid_metadata")

    def test_invalid_metadata_missing_description(self):
        lines, _ = _run(
            'import "std:tool" as tool\n'
            'let r = tool.register({name: "myapp.foo", handler: fn(a){ return a }})\n'
            'print(type(r))'
        )
        self.assertEqual(lines[0], "error")

    def test_invalid_name_no_dot(self):
        lines, _ = _run(
            'import "std:tool" as tool\n'
            'let r = tool.register({name: "nodot", handler: fn(a){ return a }, description: "Bad"})\n'
            'print(r.payload["category"])'
        )
        self.assertEqual(lines[0], "invalid_name")

    def test_schema_simple_form_normalized(self):
        lines, _ = _run(
            'import "std:tool" as tool\n'
            'tool.register({\n'
            '    name: "myapp.greet",\n'
            '    handler: fn(a){ return a },\n'
            '    description: "Greet",\n'
            '    schema: {name: "string", count: "int"}\n'
            '})\n'
            'let m = tool.lookup("myapp.greet")\n'
            'print(m.schema["type"])'
        )
        self.assertEqual(lines[0], "object")

    def test_schema_full_json_schema_passthrough(self):
        lines, _ = _run(
            'import "std:tool" as tool\n'
            'tool.register({\n'
            '    name: "myapp.greet",\n'
            '    handler: fn(a){ return a.name },\n'
            '    description: "Greet",\n'
            '    schema: {type: "object", properties: {name: {type: "string"}}, required: ["name"]}\n'
            '})\n'
            'let m = tool.lookup("myapp.greet")\n'
            'print(m.schema["type"])'
        )
        self.assertEqual(lines[0], "object")


# ---------------------------------------------------------------------------
# 2. Lookup
# ---------------------------------------------------------------------------

class LookupTests(unittest.TestCase):

    def test_lookup_returns_metadata(self):
        lines, _ = _run(
            'import "std:tool" as tool\n'
            'tool.register({name: "myapp.greet", handler: fn(a){ return a }, description: "Say hello"})\n'
            'let m = tool.lookup("myapp.greet")\n'
            'print(m.description)'
        )
        self.assertEqual(lines[0], "Say hello")

    def test_lookup_unknown_returns_err(self):
        lines, _ = _run(
            'import "std:tool" as tool\n'
            'let r = tool.lookup("no.such.tool")\n'
            'print(type(r))\n'
            'print(r.payload["category"])'
        )
        self.assertEqual(lines[0], "error")
        self.assertEqual(lines[1], "tool_not_found")


# ---------------------------------------------------------------------------
# 3. Invocation
# ---------------------------------------------------------------------------

class InvocationTests(unittest.TestCase):

    def test_invoke_calls_handler_returns_result(self):
        lines, _ = _run(
            'import "std:tool" as tool\n'
            'tool.register({name: "myapp.add", handler: fn(a){ return a.x + a.y }, description: "Add"})\n'
            'let r = tool.invoke("myapp.add", {x: 3i, y: 4i})\n'
            'print(r)'
        )
        self.assertEqual(lines[0], "7")

    def test_invoke_unknown_tool_returns_err(self):
        lines, _ = _run(
            'import "std:tool" as tool\n'
            'let r = tool.invoke("no.such.tool", {})\n'
            'print(type(r))\n'
            'print(r.payload["category"])'
        )
        self.assertEqual(lines[0], "error")
        self.assertEqual(lines[1], "tool_not_found")

    def test_invoke_schema_mismatch_returns_err(self):
        lines, _ = _run(
            'import "std:tool" as tool\n'
            'tool.register({\n'
            '    name: "myapp.greet",\n'
            '    handler: fn(a){ return a.name },\n'
            '    description: "Greet",\n'
            '    schema: {name: "string"}\n'
            '})\n'
            'let r = tool.invoke("myapp.greet", {})\n'
            'print(r.payload["category"])'
        )
        self.assertEqual(lines[0], "schema_mismatch")

    def test_invoke_valid_args_passes_schema(self):
        lines, _ = _run(
            'import "std:tool" as tool\n'
            'tool.register({\n'
            '    name: "myapp.greet",\n'
            '    handler: fn(a){ return "hi " + a.name },\n'
            '    description: "Greet",\n'
            '    schema: {name: "string"}\n'
            '})\n'
            'let r = tool.invoke("myapp.greet", {name: "world"})\n'
            'print(r)'
        )
        self.assertEqual(lines[0], "hi world")


# ---------------------------------------------------------------------------
# 4. Unregistration
# ---------------------------------------------------------------------------

class UnregistrationTests(unittest.TestCase):

    def test_unregister_returns_metadata(self):
        lines, _ = _run(
            'import "std:tool" as tool\n'
            'tool.register({name: "myapp.foo", handler: fn(a){ return a }, description: "Foo"})\n'
            'let removed = tool.unregister("myapp.foo")\n'
            'print(removed.name)'
        )
        self.assertEqual(lines[0], "myapp.foo")

    def test_unregister_removes_from_registry(self):
        lines, _ = _run(
            'import "std:tool" as tool\n'
            'tool.register({name: "myapp.foo", handler: fn(a){ return a }, description: "Foo"})\n'
            'tool.unregister("myapp.foo")\n'
            'print(tool.has("myapp.foo"))'
        )
        self.assertEqual(lines[0], "false")

    def test_unregister_non_existent_returns_err(self):
        lines, _ = _run(
            'import "std:tool" as tool\n'
            'let r = tool.unregister("no.such.tool")\n'
            'print(type(r))\n'
            'print(r.payload["category"])'
        )
        self.assertEqual(lines[0], "error")
        self.assertEqual(lines[1], "tool_not_found")

    def test_re_register_after_unregister(self):
        lines, _ = _run(
            'import "std:tool" as tool\n'
            'tool.register({name: "myapp.foo", handler: fn(a){ return "v1" }, description: "V1"})\n'
            'tool.unregister("myapp.foo")\n'
            'tool.register({name: "myapp.foo", handler: fn(a){ return "v2" }, description: "V2"})\n'
            'print(tool.invoke("myapp.foo", {}))'
        )
        self.assertEqual(lines[0], "v2")


# ---------------------------------------------------------------------------
# 5. list_tools
# ---------------------------------------------------------------------------

class ListToolsTests(unittest.TestCase):

    def test_list_all_tools(self):
        lines, _ = _run(
            'import "std:tool" as tool\n'
            'tool.register({name: "myapp.a", handler: fn(x){ return x }, description: "A"})\n'
            'tool.register({name: "myapp.b", handler: fn(x){ return x }, description: "B"})\n'
            'let lst = tool.list_tools()\n'
            'print(len(lst))'
        )
        self.assertEqual(lines[0], "2")

    def test_list_filter_by_namespace(self):
        lines, _ = _run(
            'import "std:tool" as tool\n'
            'tool.register({name: "mcp.call", handler: fn(x){ return x }, description: "MCP"})\n'
            'tool.register({name: "a2a.send", handler: fn(x){ return x }, description: "A2A"})\n'
            'let lst = tool.list_tools({namespace: "mcp"})\n'
            'print(len(lst))\n'
            'print(lst[0].name)'
        )
        self.assertEqual(lines[0], "1")
        self.assertEqual(lines[1], "mcp.call")

    def test_list_filter_by_tag(self):
        lines, _ = _run(
            'import "std:tool" as tool\n'
            'tool.register({name: "mcp.call", handler: fn(x){ return x }, description: "MCP", tags: ["protocol"]})\n'
            'tool.register({name: "a2a.send", handler: fn(x){ return x }, description: "A2A", tags: ["protocol"]})\n'
            'tool.register({name: "myapp.foo", handler: fn(x){ return x }, description: "Foo", tags: ["app"]})\n'
            'let lst = tool.list_tools({tag: "protocol"})\n'
            'print(len(lst))'
        )
        self.assertEqual(lines[0], "2")

    def test_list_filter_by_deprecated(self):
        lines, _ = _run(
            'import "std:tool" as tool\n'
            'tool.register({name: "myapp.old", handler: fn(x){ return x }, description: "Old", deprecated: true})\n'
            'tool.register({name: "myapp.new", handler: fn(x){ return x }, description: "New", deprecated: false})\n'
            'let active = tool.list_tools({deprecated: false})\n'
            'print(len(active))'
        )
        self.assertEqual(lines[0], "1")


# ---------------------------------------------------------------------------
# 6. Deprecated tool warning
# ---------------------------------------------------------------------------

class DeprecatedToolTests(unittest.TestCase):

    def test_deprecated_tool_still_works(self):
        lines, _ = _run(
            'import "std:tool" as tool\n'
            'tool.register({name: "myapp.old", handler: fn(a){ return "result" }, description: "Old", deprecated: true})\n'
            'print(tool.invoke("myapp.old", {}))'
        )
        self.assertEqual(lines[0], "result")

    def test_deprecated_emits_warning_once(self):
        vm = nodus.VM([], {}, code_locs=[], source_path="test.nd")
        err_out = io.StringIO()
        with redirect_stderr(err_out):
            loader = ModuleLoader(project_root=None, vm=vm)
            loader.load_module_from_source(
                'import "std:tool" as tool\n'
                'tool.register({name: "myapp.old", handler: fn(a){ return "r" }, description: "Old", deprecated: true})\n'
                'tool.invoke("myapp.old", {})\n'
                'tool.invoke("myapp.old", {})\n'
                'tool.invoke("myapp.old", {})',
                module_name="test.nd",
            )
        stderr = err_out.getvalue()
        self.assertEqual(stderr.count("deprecated"), 1)

    def test_non_deprecated_tool_no_warning(self):
        vm = nodus.VM([], {}, code_locs=[], source_path="test.nd")
        err_out = io.StringIO()
        with redirect_stderr(err_out):
            loader = ModuleLoader(project_root=None, vm=vm)
            loader.load_module_from_source(
                'import "std:tool" as tool\n'
                'tool.register({name: "myapp.fresh", handler: fn(a){ return "r" }, description: "Fresh"})\n'
                'tool.invoke("myapp.fresh", {})',
                module_name="test.nd",
            )
        self.assertNotIn("deprecated", err_out.getvalue())


# ---------------------------------------------------------------------------
# 7. Host-side (Python embedding) API
# ---------------------------------------------------------------------------

class HostSideTests(unittest.TestCase):

    def test_python_registered_tool_visible_in_nodus(self):
        rt = NodusRuntime()
        rt.tool_registry.register({
            "name": "python.double",
            "handler": lambda args: (args.get("x") or 0) * 2,
            "description": "Double a number",
        })
        result = rt.run_source(
            'import "std:tool" as tool\n'
            'print(tool.has("python.double"))'
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["stdout"].strip(), "true")

    def test_python_handler_invocable_from_nodus(self):
        rt = NodusRuntime()
        rt.tool_registry.register({
            "name": "python.double",
            "handler": lambda args: (args.get("x") or 0) * 2,
            "description": "Double",
        })
        result = rt.run_source(
            'import "std:tool" as tool\n'
            'print(tool.invoke("python.double", {x: 7}))'
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["stdout"].strip(), "14")

    def test_python_tool_persists_across_runs(self):
        rt = NodusRuntime()
        rt.tool_registry.register({
            "name": "python.echo",
            "handler": lambda args: args.get("msg", ""),
            "description": "Echo",
        })
        r1 = rt.run_source(
            'import "std:tool" as tool\n'
            'print(tool.has("python.echo"))'
        )
        r2 = rt.run_source(
            'import "std:tool" as tool\n'
            'print(tool.has("python.echo"))'
        )
        self.assertEqual(r1["stdout"].strip(), "true")
        self.assertEqual(r2["stdout"].strip(), "true")

    def test_nodus_tool_visible_via_host_list_tools(self):
        rt = NodusRuntime()
        rt.run_source(
            'import "std:tool" as tool\n'
            'tool.register({name: "nodus.helper", handler: fn(a){ return a }, description: "Help"})'
        )
        tools = rt.tool_registry.list_tools()
        names = [t["name"] for t in tools]
        self.assertIn("nodus.helper", names)

    def test_host_invoke_nodus_tool(self):
        rt = NodusRuntime()
        rt.run_source(
            'import "std:tool" as tool\n'
            'tool.register({name: "nodus.double", handler: fn(a){ return a.x * 2 }, description: "Double"})'
        )
        result = rt.tool_registry.invoke("nodus.double", {"x": 5})
        self.assertEqual(result, 10)

    def test_host_unregister_python_tool(self):
        rt = NodusRuntime()
        rt.tool_registry.register({
            "name": "python.temp",
            "handler": lambda a: "temp",
            "description": "Temp",
        })
        removed = rt.tool_registry.unregister("python.temp")
        self.assertEqual(removed["name"], "python.temp")
        self.assertFalse(rt.tool_registry.has("python.temp"))

    def test_host_lookup_python_tool(self):
        rt = NodusRuntime()
        rt.tool_registry.register({
            "name": "python.info",
            "handler": lambda a: "ok",
            "description": "Info tool",
        })
        meta = rt.tool_registry.lookup("python.info")
        self.assertIsNotNone(meta)
        self.assertEqual(meta["description"], "Info tool")

    def test_host_register_conflict_raises(self):
        rt = NodusRuntime()
        rt.tool_registry.register({
            "name": "python.foo",
            "handler": lambda a: "v1",
            "description": "V1",
        })
        with self.assertRaises(ValueError):
            rt.tool_registry.register({
                "name": "python.foo",
                "handler": lambda a: "v2",
                "description": "V2",
            })

    def test_value_translation_list(self):
        rt = NodusRuntime()
        rt.tool_registry.register({
            "name": "python.listfn",
            "handler": lambda args: [1, 2, 3],
            "description": "Returns list",
        })
        result = rt.run_source(
            'import "std:tool" as tool\n'
            'let r = tool.invoke("python.listfn", {})\n'
            'print(len(r))'
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["stdout"].strip(), "3")


if __name__ == "__main__":
    unittest.main()
