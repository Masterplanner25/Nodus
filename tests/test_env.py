"""3B.1: std:env namespace for environment variables."""

import io
import os
import unittest
from contextlib import redirect_stdout

import nodus as lang
from nodus.runtime.module_loader import ModuleLoader
from nodus.vm.vm import Record


def run_program(src: str, source_path: str = "main.nd"):
    vm = lang.VM([], {}, code_locs=[], source_path=source_path)
    _loader = ModuleLoader(project_root=None, vm=vm)
    buf = io.StringIO()
    with redirect_stdout(buf):
        _loader.load_module_from_source(src, module_name=source_path)
    return buf.getvalue().splitlines(), vm


def run_src(src: str):
    lines, _ = run_program(src)
    return lines


ENV_HEADER = 'import "std:env" as env\n'


class EnvGetTests(unittest.TestCase):

    def test_env_get_existing(self):
        src = ENV_HEADER + """
let path = env.get("PATH")
print("has_path:" + str(path != nil))
"""
        out = run_src(src)
        self.assertIn("has_path:true", out)

    def test_env_get_missing_returns_nil(self):
        src = ENV_HEADER + """
let v = env.get("NODUS_NONEXISTENT_XYZ123")
print("is_nil:" + str(v == nil))
"""
        out = run_src(src)
        self.assertIn("is_nil:true", out)

    def test_env_get_with_default(self):
        src = ENV_HEADER + """
let v = env.get("NODUS_NONEXISTENT_XYZ123", "fallback")
print("value:" + v)
"""
        out = run_src(src)
        self.assertIn("value:fallback", out)

    def test_env_get_returns_string(self):
        os.environ["NODUS_TEST_STRING"] = "hello_world"
        try:
            src = ENV_HEADER + """
let v = env.get("NODUS_TEST_STRING")
print("t:" + type(v))
"""
            out = run_src(src)
            self.assertIn("t:string", out)
        finally:
            del os.environ["NODUS_TEST_STRING"]


class EnvSetUnsetTests(unittest.TestCase):

    def setUp(self):
        os.environ.pop("NODUS_SET_TEST", None)

    def tearDown(self):
        os.environ.pop("NODUS_SET_TEST", None)

    def test_env_set_and_get(self):
        src = ENV_HEADER + """
env.set("NODUS_SET_TEST", "hello")
let v = env.get("NODUS_SET_TEST")
print("value:" + v)
"""
        out = run_src(src)
        self.assertIn("value:hello", out)

    def test_env_set_returns_prev_nil_when_unset(self):
        src = ENV_HEADER + """
let prev = env.set("NODUS_SET_TEST", "first")
print("prev_nil:" + str(prev == nil))
"""
        out = run_src(src)
        self.assertIn("prev_nil:true", out)

    def test_env_set_returns_prev_value_when_exists(self):
        os.environ["NODUS_SET_TEST"] = "original"
        src = ENV_HEADER + """
let prev = env.set("NODUS_SET_TEST", "new")
print("prev:" + prev)
"""
        out = run_src(src)
        self.assertIn("prev:original", out)

    def test_env_unset_removes_var(self):
        os.environ["NODUS_SET_TEST"] = "bye"
        src = ENV_HEADER + """
env.unset("NODUS_SET_TEST")
let v = env.get("NODUS_SET_TEST")
print("is_nil:" + str(v == nil))
"""
        out = run_src(src)
        self.assertIn("is_nil:true", out)

    def test_env_unset_returns_prev(self):
        os.environ["NODUS_SET_TEST"] = "value_to_remove"
        src = ENV_HEADER + """
let prev = env.unset("NODUS_SET_TEST")
print("prev:" + prev)
"""
        out = run_src(src)
        self.assertIn("prev:value_to_remove", out)

    def test_env_unset_missing_returns_nil(self):
        src = ENV_HEADER + """
let prev = env.unset("NODUS_NONEXISTENT_XYZ123")
print("nil:" + str(prev == nil))
"""
        out = run_src(src)
        self.assertIn("nil:true", out)

    def test_env_set_invalid_name_returns_err(self):
        src = ENV_HEADER + """
let r = env.set("BAD=NAME", "value")
print("type:" + type(r))
"""
        out = run_src(src)
        self.assertIn("type:error", out)

    def test_env_set_invalid_name_err_kind(self):
        src = ENV_HEADER + """
let r = env.set("BAD=NAME", "value")
print(r.kind)
"""
        out = run_src(src)
        self.assertIn("env_error", out)

    def test_env_set_invalid_name_err_category(self):
        src = ENV_HEADER + """
let r = env.set("BAD=NAME", "value")
print(r.payload["category"])
"""
        out = run_src(src)
        self.assertIn("invalid_name", out)


class EnvHasTests(unittest.TestCase):

    def test_env_has_existing(self):
        os.environ["NODUS_HAS_TEST"] = "x"
        try:
            src = ENV_HEADER + """
print("has:" + str(env.has("NODUS_HAS_TEST")))
"""
            out = run_src(src)
            self.assertIn("has:true", out)
        finally:
            del os.environ["NODUS_HAS_TEST"]

    def test_env_has_missing(self):
        src = ENV_HEADER + """
print("no_has:" + str(env.has("NODUS_NONEXISTENT_XYZ123")))
"""
        out = run_src(src)
        self.assertIn("no_has:false", out)

    def test_env_has_after_set(self):
        src = ENV_HEADER + """
env.set("NODUS_HAS_AFTER_SET", "y")
print("has:" + str(env.has("NODUS_HAS_AFTER_SET")))
"""
        try:
            out = run_src(src)
            self.assertIn("has:true", out)
        finally:
            os.environ.pop("NODUS_HAS_AFTER_SET", None)

    def test_env_has_after_unset(self):
        os.environ["NODUS_HAS_UNSET"] = "gone"
        src = ENV_HEADER + """
env.unset("NODUS_HAS_UNSET")
print("has:" + str(env.has("NODUS_HAS_UNSET")))
"""
        try:
            out = run_src(src)
            self.assertIn("has:false", out)
        finally:
            os.environ.pop("NODUS_HAS_UNSET", None)


class EnvListTests(unittest.TestCase):

    def test_env_list_returns_map(self):
        src = ENV_HEADER + """
let m = env.list()
print("t:" + type(m))
"""
        out = run_src(src)
        self.assertIn("t:map", out)

    def test_env_list_contains_path(self):
        src = ENV_HEADER + """
let m = env.list()
print("has:" + str(has_key(m, "PATH")))
"""
        out = run_src(src)
        self.assertIn("has:true", out)

    def test_env_list_keys_returns_list(self):
        src = ENV_HEADER + """
let k = env.list_keys()
print("t:" + type(k))
"""
        out = run_src(src)
        self.assertIn("t:list", out)

    def test_env_list_keys_contains_path(self):
        src = ENV_HEADER + """
let k = env.list_keys()
print("has:" + str(index_of(k, "PATH") != nil))
"""
        out = run_src(src)
        self.assertIn("has:true", out)

    def test_env_list_reflects_set(self):
        src = ENV_HEADER + """
env.set("NODUS_LIST_TEST", "abc")
let m = env.list()
print("val:" + m["NODUS_LIST_TEST"])
"""
        try:
            out = run_src(src)
            self.assertIn("val:abc", out)
        finally:
            os.environ.pop("NODUS_LIST_TEST", None)


if __name__ == "__main__":
    unittest.main()
