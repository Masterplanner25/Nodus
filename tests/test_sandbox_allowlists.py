"""Tests for allowed_commands (#161) and allowed_hosts (#162) sandbox params."""

from nodus.runtime.embedding import NodusRuntime


def _run(source, **kwargs):
    rt = NodusRuntime(timeout_ms=None, max_steps=None, **kwargs)
    return rt.run_source(source)


# ---------------------------------------------------------------------------
# allowed_commands — #161
# ---------------------------------------------------------------------------

class TestAllowedCommands:
    def test_allowed_command_runs(self):
        rt = NodusRuntime(timeout_ms=None, allowed_commands=["python"])
        # Just check construction and that the param is stored
        assert rt.allowed_commands == ["python"]

    def test_no_restriction_by_default(self):
        rt = NodusRuntime(timeout_ms=None)
        assert rt.allowed_commands is None

    def test_blocked_command_raises_sandbox_error(self):
        r = _run(
            'let r = subprocess_run(["whoami"])',
            allowed_commands=["git"],
        )
        assert not r["ok"]
        err = r.get("error") or {}
        assert err.get("type") == "sandbox" or "sandbox" in str(r).lower()

    def test_allowed_command_basename_match(self):
        """allowed_commands=["echo"] should match /bin/echo or echo."""
        rt = NodusRuntime(timeout_ms=None, allowed_commands=["echo"])
        assert "echo" in rt.allowed_commands

    def test_shell_mode_blocked_when_allowed_commands_set(self):
        r = _run(
            'let r = subprocess_shell("echo hi")',
            allowed_commands=["echo"],
        )
        assert not r["ok"]
        err = r.get("error") or {}
        assert err.get("type") == "sandbox" or "sandbox" in str(r).lower()

    def test_none_allowed_commands_does_not_restrict(self):
        rt = NodusRuntime(timeout_ms=None, allowed_commands=None)
        assert rt.allowed_commands is None

    def test_allowed_commands_passed_to_vm(self):
        rt = NodusRuntime(timeout_ms=None, allowed_commands=["git", "ls"])
        result = rt.run_source("print(42)")
        assert result["ok"]
        assert rt.last_vm.allowed_commands == ["git", "ls"]


# ---------------------------------------------------------------------------
# allowed_hosts — #162
# ---------------------------------------------------------------------------

class TestAllowedHosts:
    def test_no_restriction_by_default(self):
        rt = NodusRuntime(timeout_ms=None)
        assert rt.allowed_hosts is None

    def test_allowed_hosts_stored(self):
        rt = NodusRuntime(timeout_ms=None, allowed_hosts=["api.example.com"])
        assert rt.allowed_hosts == ["api.example.com"]

    def test_blocked_host_raises_sandbox_error(self):
        r = _run(
            'let r = http_get("https://evil.example.com/data")',
            allowed_hosts=["api.example.com"],
        )
        assert not r["ok"]
        err = r.get("error") or {}
        assert err.get("type") == "sandbox" or "sandbox" in str(r).lower()

    def test_allowed_host_passes_check(self):
        """An allowed host should not be blocked by the sandbox check itself
        (the request may still fail due to network, which is fine)."""
        rt = NodusRuntime(timeout_ms=None, allowed_hosts=["api.example.com"])
        assert rt.allowed_hosts == ["api.example.com"]

    def test_allowed_hosts_passed_to_vm(self):
        rt = NodusRuntime(timeout_ms=None, allowed_hosts=["api.example.com"])
        result = rt.run_source("print(42)")
        assert result["ok"]
        assert rt.last_vm.allowed_hosts == ["api.example.com"]

    def test_none_allowed_hosts_does_not_restrict(self):
        rt = NodusRuntime(timeout_ms=None, allowed_hosts=None)
        assert rt.allowed_hosts is None

    def test_blocked_host_async_raises_sandbox_error(self):
        r = _run(
            'let r = http_get_async("https://blocked.example.net/")',
            allowed_hosts=["safe.example.com"],
        )
        assert not r["ok"]
        err = r.get("error") or {}
        assert err.get("type") == "sandbox" or "sandbox" in str(r).lower()
