"""An index chain resolves, and a function reached through one is callable.

Two questions that go together because they are the same expression shape with
different things on the end of it:

* `data["users"][1]["name"]` -- indexing through mixed containers, where each
  link may be a map, a list or a record, and the accessor changes with it
  (`[...]` for maps and lists, `.field` for records).
* `ops["add"](4, 5)` -- calling **directly** off an index, rather than binding
  the function to a name first.

Neither had a test. The second is the more interesting gap: the two artifacts
that demonstrate it disagree. `tests/eval/language_exerciser.nd` extracts first
and carries a comment saying to (*"Functions stored in maps -- extract before
calling"*), while `tests/eval/framework_capabilities.nd` P1 calls straight off
the index (`routes["/"]()`). Both are release probes, both pass, and a reader
could take the exerciser's comment as a language limitation. It is not one --
the direct form works, including with arguments and through a nested chain, and
this file pins that so the question has an answer in the suite rather than in
two examples pointing different ways.

Dispatch tables are not incidental here: mapping a name to a handler is how the
framework probes build a router, an event bus, a plugin registry and a rule
engine, which is most of what `framework_capabilities.nd` demonstrates the
language can host.
"""

import io
import unittest
from contextlib import redirect_stdout

import nodus as lang
from nodus.runtime.module_loader import ModuleLoader


def run_program(src: str, source_path: str | None = None) -> list[str]:
    """Run through the loader, not `compile_only` + a bare `VM`.

    The two differ where it matters here: `compile_only` produces a chunk with no
    import resolution behind it, so `import "std:json"` compiles and then fails at
    run time with `Undefined variable: json`. `load_module_from_source` is the
    path a real module takes. Same helper as `tests/test_nodus.py`.
    """
    vm = lang.VM([], {}, code_locs=[], source_path=source_path)
    _loader = ModuleLoader(project_root=None, vm=vm)
    buf = io.StringIO()
    with redirect_stdout(buf):
        _loader.load_module_from_source(
            src, module_name=source_path or "<memory>", base_dir=None
        )
    return buf.getvalue().splitlines()


class IndexChainTests(unittest.TestCase):
    def test_map_then_list_then_map(self):
        src = """
let data = {"users": [{"name": "alice"}, {"name": "bob"}]}
print(data["users"][1]["name"])
"""
        self.assertEqual(run_program(src), ["bob"])

    def test_a_chain_may_end_on_a_record_field(self):
        """The accessor changes mid-chain: `[...]` for containers, `.f` for records."""
        src = """
let data = {"rows": [record {v: 7}]}
print(data["rows"][0].v)
"""
        self.assertEqual(run_program(src), ["7.0"])

    def test_a_chain_may_start_on_a_record_field(self):
        src = """
let r = record {m: {"xs": [10, 20]}}
print(r.m["xs"][1])
"""
        self.assertEqual(run_program(src), ["20.0"])

    def test_a_chain_is_assignable_through_its_last_link(self):
        src = """
let data = {"users": [{"name": "alice"}]}
data["users"][0]["name"] = "carol"
print(data["users"][0]["name"])
"""
        self.assertEqual(run_program(src), ["carol"])

    def test_a_chain_survives_json_round_trip(self):
        """Three levels down and through a list index, the shape the probe uses."""
        src = """
import "std:json" as json
let obj = {"a": {"b": {"c": [1, 2, 3]}}}
let back = json.parse(json.stringify(obj))
print(back["a"]["b"]["c"][2])
"""
        self.assertEqual(run_program(src), ["3.0"])


class DispatchTableTests(unittest.TestCase):
    def test_a_function_is_callable_directly_off_a_map_index(self):
        """`ops["add"](4, 5)` -- no intermediate binding, with arguments."""
        src = """
fn add(a, b) { return a + b }
fn sub(a, b) { return a - b }
let ops = {"add": add, "sub": sub}
print(ops["add"](4, 5))
print(ops["sub"](10, 3))
"""
        self.assertEqual(run_program(src), ["9.0", "7.0"])

    def test_the_extract_first_form_agrees_with_the_direct_form(self):
        """Both spellings, one answer -- the two release probes use one each."""
        src = """
fn add(a, b) { return a + b }
let ops = {"add": add}
let f = ops["add"]
print(f(4, 5))
print(ops["add"](4, 5))
"""
        self.assertEqual(run_program(src), ["9.0", "9.0"])

    def test_a_function_literal_stored_in_a_map_is_callable_off_the_index(self):
        src = """
let routes = {}
routes["/"] = fn() { return "home" }
routes["/about"] = fn() { return "about" }
print(routes["/"]())
print(routes["/about"]())
"""
        self.assertEqual(run_program(src), ["home", "about"])

    def test_a_function_is_callable_off_a_list_index(self):
        src = """
let fns = [fn(x) { return x * 2 }]
print(fns[0](21))
"""
        self.assertEqual(run_program(src), ["42.0"])

    def test_a_function_is_callable_off_a_nested_chain(self):
        src = """
let reg = {"math": {"double": fn(x) { return x * 2 }}}
print(reg["math"]["double"](21))
"""
        self.assertEqual(run_program(src), ["42.0"])

    def test_dispatch_selects_between_handlers_at_runtime(self):
        """The point of a dispatch table: the key is a value, not a literal."""
        src = """
fn add(a, b) { return a + b }
fn sub(a, b) { return a - b }
let ops = {"add": add, "sub": sub}
let names = ["add", "sub"]
let i = 0
while (i < len(names)) {
    print(ops[names[i]](10, 4))
    i = i + 1
}
"""
        self.assertEqual(run_program(src), ["14.0", "6.0"])


if __name__ == "__main__":
    unittest.main()
