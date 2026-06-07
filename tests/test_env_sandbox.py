"""Sandbox enforcement for the std:env module (allow_env flag).

Covers:
  - allow_env=False blocks env_get, env_set, env_unset, env_has, env_list, env_list_keys
  - Block applies both for direct builtin calls and via `import "std:env" as env`
  - allow_env=True (default) allows all env operations normally
  - CLI and embedded modes consistent
"""

import unittest

from nodus import NodusRuntime

_IMPORT = 'import "std:env" as env\n'


def _run(src, *, allow_env=True):
    rt = NodusRuntime(timeout_ms=None, allow_env=allow_env)
    return rt.run_source(src)


def _blocked(result):
    return not result["ok"] and any(
        "Blocked" in (e.get("message") or "") for e in result.get("errors", [])
    )


class EnvAllowedTests(unittest.TestCase):
    """allow_env=True (default) — all operations must work."""

    def test_env_has_returns_bool(self):
        r = _run(_IMPORT + 'print(env.has("PATH"))')
        self.assertTrue(r["ok"])
        self.assertIn(r["stdout"].strip(), ("true", "false"))

    def test_env_get_returns_value_or_default(self):
        r = _run(_IMPORT + 'print(env.get("__NODUS_TEST_ABSENT__", "default_val"))')
        self.assertTrue(r["ok"])
        self.assertEqual(r["stdout"].strip(), "default_val")

    def test_env_set_and_get(self):
        r = _run(_IMPORT + 'env.set("__NODUS_TEST_KEY__", "hello")\nprint(env.get("__NODUS_TEST_KEY__", ""))')
        self.assertTrue(r["ok"])
        self.assertEqual(r["stdout"].strip(), "hello")

    def test_env_list_keys_is_list(self):
        r = _run(_IMPORT + 'let keys = env.list_keys()\nprint(len(keys) > 0i)')
        self.assertTrue(r["ok"])
        self.assertEqual(r["stdout"].strip(), "true")


class EnvBlockedTests(unittest.TestCase):
    """allow_env=False — all env operations must be blocked."""

    def test_direct_env_has_blocked(self):
        r = _run('env_has("PATH")', allow_env=False)
        self.assertTrue(_blocked(r), f"Expected sandbox block, got: {r}")

    def test_direct_env_get_blocked(self):
        r = _run('env_get("PATH", "x")', allow_env=False)
        self.assertTrue(_blocked(r), f"Expected sandbox block, got: {r}")

    def test_direct_env_set_blocked(self):
        r = _run('env_set("X", "y")', allow_env=False)
        self.assertTrue(_blocked(r), f"Expected sandbox block, got: {r}")

    def test_direct_env_list_blocked(self):
        r = _run('env_list()', allow_env=False)
        self.assertTrue(_blocked(r), f"Expected sandbox block, got: {r}")

    def test_module_env_has_blocked(self):
        r = _run(_IMPORT + 'env.has("PATH")', allow_env=False)
        self.assertTrue(_blocked(r), f"Expected sandbox block via module, got: {r}")

    def test_module_env_get_blocked(self):
        r = _run(_IMPORT + 'env.get("PATH", "x")', allow_env=False)
        self.assertTrue(_blocked(r), f"Expected sandbox block via module, got: {r}")

    def test_module_env_set_blocked(self):
        r = _run(_IMPORT + 'env.set("X", "y")', allow_env=False)
        self.assertTrue(_blocked(r), f"Expected sandbox block via module, got: {r}")

    def test_module_env_list_blocked(self):
        r = _run(_IMPORT + 'env.list()', allow_env=False)
        self.assertTrue(_blocked(r), f"Expected sandbox block via module, got: {r}")

    def test_module_env_list_keys_blocked(self):
        r = _run(_IMPORT + 'env.list_keys()', allow_env=False)
        self.assertTrue(_blocked(r), f"Expected sandbox block via module, got: {r}")

    def test_block_does_not_affect_other_builtins(self):
        r = _run('print("hello")', allow_env=False)
        self.assertTrue(r["ok"])
        self.assertEqual(r["stdout"].strip(), "hello")

    def test_allow_env_false_error_message(self):
        r = _run('env_has("X")', allow_env=False)
        errors = r.get("errors", [])
        self.assertTrue(any("allow_env=False" in (e.get("message") or "") for e in errors))
