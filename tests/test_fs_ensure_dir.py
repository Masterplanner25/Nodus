"""`fs.ensure_dir` reports failure, and no stdlib wrapper drops an err record (#845).

`ensure_dir` was written in Nodus as

    fn ensure_dir(path) {
        mkdir(path)      // result discarded
        return path
    }

so every failure was reported as success. With a *file* at the target path it
returned the path, created nothing, and the next write into it failed with
"parent directory does not exist" — at a call site with no obvious connection to
the one that lied.

**The obvious repair is wrong**, which is why the second half of this file
exists. Propagating `mkdir`'s error breaks the function: `fs_mkdir` uses
`exist_ok=False` and therefore fails on an *existing directory* too, and a
function named `ensure_dir` that refuses when the directory is already there is
not usable. Telling the two apart in Nodus would need an `is_dir` predicate
`std:fs` does not have, and would ask the filesystem twice with a window in
between. `os.makedirs(exist_ok=True)` is that distinction, made once by the OS.

So the idempotency test below is not a nicety — it is the case that rules out
the repair a reader reaches for first.
"""

from __future__ import annotations

import ast
import glob
import os
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.frontend.ast.ast_nodes import Call, ExprStmt, Var  # noqa: E402
from nodus.frontend.lexer import tokenize  # noqa: E402
from nodus.frontend.parser import Parser  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402

_STDLIB = _REPO_ROOT / "src" / "nodus" / "stdlib"
_BUILTINS = _REPO_ROOT / "src" / "nodus" / "builtins"


def _run(source: str, jail: str):
    return NodusRuntime(allowed_paths=[jail]).run_source(
        'import "std:fs" as fs\nfn main() {\n' + source + "\n}\nmain()"
    )


def _err(result) -> dict:
    return result.get("error") or {}


class EnsureDirTests(unittest.TestCase):
    def setUp(self):
        self.jail = tempfile.mkdtemp()
        self.outside = tempfile.mkdtemp()
        self._cwd = os.getcwd()
        os.chdir(self.jail)
        self.addCleanup(os.chdir, self._cwd)
        (Path(self.jail) / "afile").write_text("x", encoding="utf-8")

    # closes: #845
    def test_a_path_that_is_a_file_is_refused(self):
        result = _run('    let r = fs.ensure_dir("afile")\n'
                      '    if (type(r) == "error") { print("err:" + r.kind) }\n'
                      '    else { print("reported success") }', self.jail)
        self.assertTrue(result.get("ok"), _err(result))
        self.assertEqual("err:io_error", (result.get("stdout") or "").strip())
        self.assertTrue(
            (Path(self.jail) / "afile").is_file(),
            "the file was replaced rather than the call being refused",
        )

    # closes: #845
    def test_the_refusal_says_what_is_wrong(self):
        result = _run('    let r = fs.ensure_dir("afile")\n    print(r.message)', self.jail)
        self.assertIn("not a directory", (result.get("stdout") or ""))

    def test_a_new_directory_is_created_and_the_path_returned(self):
        result = _run('    print(str(fs.ensure_dir("fresh")))', self.jail)
        self.assertTrue(result.get("ok"), _err(result))
        self.assertEqual("fresh", (result.get("stdout") or "").strip())
        self.assertTrue((Path(self.jail) / "fresh").is_dir())

    def test_calling_it_twice_succeeds(self):
        """The case that rules out simply propagating `mkdir`'s error.

        `fs_mkdir` is `exist_ok=False`, so the naive repair makes the second
        call fail — which defeats the only reason the function exists.
        """
        result = _run('    fs.ensure_dir("twice")\n'
                      '    let r = fs.ensure_dir("twice")\n'
                      '    if (type(r) == "error") { print("second call failed: " + r.message) }\n'
                      '    else { print("idempotent") }', self.jail)
        self.assertEqual("idempotent", (result.get("stdout") or "").strip())

    def test_missing_parents_are_created(self):
        result = _run('    print(str(fs.ensure_dir("a/b/c")))', self.jail)
        self.assertTrue(result.get("ok"), _err(result))
        self.assertTrue((Path(self.jail) / "a" / "b" / "c").is_dir())

    def test_a_wrong_typed_argument_throws(self):
        """Argument validation throws; it does not return a record.

        The contract `docs/policy/error-surfaces.md` §2.1 states, and the reason
        it distinguishes the two: which one you get decides whether the caller
        writes `type(r) == "error"` or `try`/`catch`.
        """
        result = _run("    let r = fs.ensure_dir(5i)\n    print(str(r))", self.jail)
        self.assertFalse(result.get("ok"))
        self.assertEqual("type", _err(result).get("kind"))

    def test_it_is_confined_by_the_sandbox(self):
        target = os.path.join(self.outside, "escaped").replace("\\", "/")
        result = _run(f'    let r = fs.ensure_dir("{target}")\n    print(str(r))', self.jail)
        self.assertFalse(result.get("ok"))
        self.assertEqual("sandbox", _err(result).get("kind"))
        self.assertFalse(os.path.isdir(os.path.join(self.outside, "escaped")))


class NoStdlibWrapperDropsAnErrRecord(unittest.TestCase):
    """The shape, not the instance: a discarded err record anywhere in `stdlib/`.

    Derived rather than listed. A Python builtin that can reach `vm.make_err`
    returns err records; a stdlib `fn` whose body is `return <such a call>`
    returns them too, which is the delegation pattern nearly every `stdlib/*.nd`
    function uses. Calling either as a *statement* throws the record away.

    Its limit, stated because a scan that quietly covers less than it claims is
    worse than none: the transitive step is one level deep, and a wrapper that
    returns an error through a conditional or a loop is not recognised. What it
    does cover is the shape that actually occurred.
    """

    @staticmethod
    def _err_returning_builtins() -> set[str]:
        exposed_to_impl: dict[str, str] = {}
        impls: dict[str, ast.FunctionDef] = {}
        for path in glob.glob(str(_BUILTINS / "*.py")):
            tree = ast.parse(Path(path).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    impls[node.name] = node
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "add"
                        and len(node.args) >= 3
                        and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)
                        and isinstance(node.args[-1], ast.Name)):
                    exposed_to_impl[node.args[0].value] = node.args[-1].id
        names = set()
        for exposed, impl in exposed_to_impl.items():
            fn = impls.get(impl)
            if fn is None:
                continue
            for sub in ast.walk(fn):
                if (isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Attribute)
                        and sub.func.attr == "make_err"):
                    names.add(exposed)
                    break
        return names

    @staticmethod
    def _callee_name(call) -> str | None:
        callee = getattr(call, "func", None) or getattr(call, "callee", None)
        if callee is None:
            return None
        return getattr(callee, "name", None) or (
            getattr(callee, "ident", None) if isinstance(callee, Var) else None
        )

    @classmethod
    def _walk(cls, node, out):
        if isinstance(node, (list, tuple)):
            for item in node:
                cls._walk(item, out)
            return
        if not hasattr(node, "__dict__"):
            return
        if isinstance(node, ExprStmt) and isinstance(getattr(node, "expr", None), Call):
            out.append(cls._callee_name(node.expr))
        for value in vars(node).values():
            cls._walk(value, out)

    def test_the_scan_finds_err_returning_builtins(self):
        """A set that came back empty would make the next test vacuous."""
        found = self._err_returning_builtins()
        self.assertGreater(len(found), 15, "the registry or make_err pattern moved")
        self.assertIn("fs_mkdir", found)

    def test_no_stdlib_function_discards_an_err_record(self):
        err_returning = self._err_returning_builtins()
        offenders: list[str] = []
        for path in sorted(glob.glob(str(_STDLIB / "*.nd"))):
            try:
                tree = Parser(tokenize(Path(path).read_text(encoding="utf-8"))).parse()
            except Exception:  # a .nd the parser cannot read is another test's problem
                continue
            local = set()
            for node in tree if isinstance(tree, list) else []:
                # `FnDef.body` is a `Block`, whose statements are `.stmts`.
                block = getattr(node, "body", None)
                stmts = getattr(block, "stmts", None) or []
                name = getattr(node, "name", None)
                if name and len(stmts) == 1 and type(stmts[0]).__name__ == "Return":
                    inner = getattr(stmts[0], "expr", None)
                    if isinstance(inner, Call) and self._callee_name(inner) in err_returning:
                        local.add(name)
            discarded: list[str | None] = []
            self._walk(tree, discarded)
            for called in discarded:
                if called in err_returning or called in local:
                    offenders.append(f"{os.path.basename(path)}: {called}(...)")
        self.assertEqual(
            [], offenders,
            "these call a function that can return an err record and throw the "
            "result away, so a failure is reported as success",
        )


if __name__ == "__main__":
    unittest.main()
