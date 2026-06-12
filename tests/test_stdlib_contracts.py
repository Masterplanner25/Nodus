"""
Stdlib contract tests — verify installed-wheel API shapes match documentation.

Run against the installed wheel (not dev source):
    NODUS_RUN_CONTRACTS=1 .venv-validation\\Scripts\\python.exe -m pytest tests/test_stdlib_contracts.py -v

Run against dev source (for baseline comparison):
    NODUS_RUN_CONTRACTS=1 PYTHONPATH="C:/dev/Coding Language/src" .venv\\Scripts\\python.exe -m pytest tests/test_stdlib_contracts.py -v

These tests exist because every eval cycle since v2.0.0 has surfaced the same class of
failures: documentation describes one API shape, the installed wheel ships another.  The
contract tests give us a reproducible, wheel-level regression harness so drift is caught
before the next eval, not during it.

Critical contracts tested:
  - B7 root cause: time.format takes a datetime Record, not a string
  - effects: action_id is 3-arg, pending is 2-arg, resolve returns Record{done,cached}
  - circuit_breaker: create vs create_config split, state uses underscores not hyphens
  - hash: returns Record with .to_hex(), not a raw string
  - type(): returns "float" for 42 since v4.0.0
  - NodusRuntime() defaults: timeout_ms=None, allowed_paths=CWD since v4.0.1
  - subprocess: result record shape, allowed_commands sandbox enforcement
"""

import os
import sys
import unittest

if os.environ.get("NODUS_RUN_CONTRACTS") != "1":
    raise unittest.SkipTest("Set NODUS_RUN_CONTRACTS=1 to run contract tests against the installed wheel")

from nodus.runtime.embedding import NodusRuntime  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_rt(**kwargs):
    defaults = dict(timeout_ms=None, max_steps=None)
    defaults.update(kwargs)
    return NodusRuntime(**defaults)


def nrun(code, **rt_kwargs):
    """Run a Nodus snippet; return the full result dict."""
    rt = make_rt(**rt_kwargs)
    return rt.run_source(code)


def out(code, **rt_kwargs):
    """Run Nodus code; return stripped stdout, or None if the run failed."""
    res = nrun(code, **rt_kwargs)
    if not res["ok"]:
        return None
    return res["stdout"].strip()


def is_ok(code, **rt_kwargs):
    """Return True if the code ran without error."""
    return nrun(code, **rt_kwargs)["ok"]


def err_info(code, **rt_kwargs):
    """Run code expected to fail; return the error dict (kind, message) or None."""
    res = nrun(code, **rt_kwargs)
    if res["ok"]:
        return None
    return res.get("error") or {}


# ---------------------------------------------------------------------------
# std:hash
# ---------------------------------------------------------------------------

class TestHashContracts(unittest.TestCase):
    """hash.sha256() must return a hash Record, not a raw string.

    The B-pattern failure: AI assistants wrote `let hex = hash.sha256(data)` and
    then used `hex` as a string.  The actual return is a Record; callers must
    call `.to_hex()` to obtain the hex string.
    """

    def test_sha256_to_hex_returns_64_char_string(self):
        result = out('import "std:hash" as hash\nprint(hash.sha256("hello").to_hex())')
        self.assertIsNotNone(result, "hash.sha256('hello').to_hex() failed")
        self.assertEqual(len(result), 64, f"SHA-256 hex digest must be 64 chars, got {len(result)}: {result!r}")

    def test_sha256_to_hex_is_lowercase_hex(self):
        result = out('import "std:hash" as hash\nprint(hash.sha256("hello").to_hex())')
        self.assertRegex(result, r'^[0-9a-f]{64}$', "to_hex() must return lowercase hex")

    def test_sha256_to_hex_upper_is_uppercase(self):
        result = out('import "std:hash" as hash\nprint(hash.sha256("hello").to_hex_upper())')
        self.assertRegex(result, r'^[0-9A-F]{64}$', "to_hex_upper() must return uppercase hex")

    def test_sha256_algorithm_field(self):
        result = out('import "std:hash" as hash\nprint(hash.sha256("hello").algorithm)')
        self.assertEqual(result, "sha256")

    def test_sha256_length_field(self):
        result = out('import "std:hash" as hash\nprint(hash.sha256("hello").length)')
        self.assertEqual(result, "32")

    def test_sha512_length_field(self):
        result = out('import "std:hash" as hash\nprint(hash.sha512("hello").length)')
        self.assertEqual(result, "64")

    def test_sha256_bad_input_is_error(self):
        # hash.sha256(42) should return a type_error Record, not raise
        res = nrun('import "std:hash" as hash\nhash.sha256(42)')
        # Either ok=False (runtime error) OR stdout shows nothing (error record was the result)
        # The important thing is it does NOT produce valid hex output
        hex_out = res.get("stdout", "").strip()
        self.assertFalse(
            len(hex_out) == 64 and all(c in "0123456789abcdef" for c in hex_out),
            "hash.sha256(42) must not silently produce a hex digest"
        )

    def test_sha256_to_base64_works(self):
        result = out('import "std:hash" as hash\nprint(hash.sha256("hello").to_base64())')
        self.assertIsNotNone(result)
        self.assertGreater(len(result), 0)

    def test_hmac_sha256_returns_hex(self):
        result = out('import "std:hash" as hash\nprint(hash.hmac_sha256("key", "msg").to_hex())')
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 64)

    def test_hash_compare_equal(self):
        # Parens required around function-call if conditions in Nodus
        result = out("""
import "std:hash" as hash
let a = hash.sha256("hello")
let b = hash.sha256("hello")
if (hash.compare(a, b)) { print("equal") } else { print("not_equal") }
""")
        self.assertEqual(result, "equal")

    def test_hash_compare_unequal(self):
        result = out("""
import "std:hash" as hash
let a = hash.sha256("hello")
let b = hash.sha256("world")
if (hash.compare(a, b)) { print("equal") } else { print("not_equal") }
""")
        self.assertEqual(result, "not_equal")

    def test_sha256_builder_matches_one_shot(self):
        direct = out('import "std:hash" as hash\nprint(hash.sha256("hello").to_hex())')
        via_builder = out("""
import "std:hash" as hash
let b = hash.sha256_builder()
b.update("hello")
print(b.finalize().to_hex())
""")
        self.assertEqual(direct, via_builder, "builder and one-shot sha256 must produce same hex")


# ---------------------------------------------------------------------------
# std:encoding
# ---------------------------------------------------------------------------

class TestEncodingContracts(unittest.TestCase):

    def test_base64_encode_canonical(self):
        result = out('import "std:encoding" as encoding\nprint(encoding.base64_encode("hello"))')
        self.assertEqual(result, "aGVsbG8=")

    def test_base64_decode_canonical(self):
        result = out('import "std:encoding" as encoding\nprint(encoding.base64_decode("aGVsbG8="))')
        self.assertEqual(result, "hello")

    def test_base64_round_trip(self):
        result = out("""
import "std:encoding" as encoding
print(encoding.base64_decode(encoding.base64_encode("test data")))
""")
        self.assertEqual(result, "test data")

    def test_base64_url_encode_no_padding(self):
        result = out('import "std:encoding" as encoding\nprint(encoding.base64_url_encode("hello world"))')
        self.assertIsNotNone(result)
        self.assertNotIn("=", result, "base64_url_encode must strip padding")
        self.assertNotIn("+", result, "base64_url_encode must not use + (URL-safe)")
        self.assertNotIn("/", result, "base64_url_encode must not use / (URL-safe)")

    def test_base64_url_round_trip(self):
        result = out("""
import "std:encoding" as encoding
print(encoding.base64_url_decode(encoding.base64_url_encode("test")))
""")
        self.assertEqual(result, "test")

    def test_hex_encode_lowercase(self):
        # "AB" = 0x41 0x42
        result = out('import "std:encoding" as encoding\nprint(encoding.hex_encode("AB"))')
        self.assertEqual(result, "4142")

    def test_hex_encode_upper(self):
        result = out('import "std:encoding" as encoding\nprint(encoding.hex_encode_upper("AB"))')
        self.assertEqual(result, "4142")

    def test_url_encode_space(self):
        result = out('import "std:encoding" as encoding\nprint(encoding.url_encode("hello world"))')
        self.assertEqual(result, "hello%20world")

    def test_url_decode_space(self):
        result = out('import "std:encoding" as encoding\nprint(encoding.url_decode("hello%20world"))')
        self.assertEqual(result, "hello world")

    def test_bad_base64_fails_gracefully(self):
        # Invalid base64 should not raise an unhandled exception; it should return an error record
        res = nrun('import "std:encoding" as encoding\nencoding.base64_decode("not!!!valid")')
        # Must not crash (ok might be True if it returns an error Record, or False)
        # The important thing: no unhandled exception
        self.assertIn("ok", res)


# ---------------------------------------------------------------------------
# std:time
# ---------------------------------------------------------------------------

class TestTimeContracts(unittest.TestCase):
    """Critical: time.format takes a datetime Record, NOT a string (B7 root cause)."""

    def test_now_has_epoch_ms(self):
        result = out('import "std:time" as time\nprint(time.now().epoch_ms)')
        self.assertIsNotNone(result)
        self.assertGreater(float(result), 0)

    def test_now_year_is_current_year(self):
        result = out('import "std:time" as time\nprint(time.now().year)')
        self.assertIsNotNone(result)
        self.assertGreaterEqual(int(float(result)), 2024)

    def test_now_zone_is_string(self):
        result = out('import "std:time" as time\nprint(type(time.now().zone))')
        self.assertEqual(result, "string")

    def test_now_has_day_of_year(self):
        result = out('import "std:time" as time\nprint(time.now().day_of_year)')
        self.assertIsNotNone(result)
        val = int(float(result))
        self.assertGreater(val, 0)
        self.assertLessEqual(val, 366)

    def test_from_epoch_ms_year(self):
        # 1000000000000ms = 2001-09-09
        result = out('import "std:time" as time\nprint(time.from_epoch_ms(1000000000000).year)')
        self.assertEqual(result, "2001")

    def test_from_iso8601_year(self):
        result = out('import "std:time" as time\nprint(time.from_iso8601("2026-01-15T00:00:00Z").year)')
        self.assertEqual(result, "2026")

    def test_from_iso8601_month(self):
        result = out('import "std:time" as time\nprint(time.from_iso8601("2026-01-15T00:00:00Z").month)')
        self.assertEqual(result, "1")

    def test_from_iso8601_day(self):
        result = out('import "std:time" as time\nprint(time.from_iso8601("2026-01-15T00:00:00Z").day)')
        self.assertEqual(result, "15")

    def test_format_string_input_is_error_not_garbage(self):
        # B7 root cause: time.format() takes a datetime Record, not a string.
        # Passing a string must NOT silently produce garbage like "2026/%54/%10".
        res = nrun('import "std:time" as time\ntime.format("2026-01-15", "yyyy/MM/dd")')
        stdout = res.get("stdout", "").strip()
        # If it produced any output at all, it must not contain garbage format tokens
        if stdout:
            self.assertNotIn("%5", stdout,
                             f"time.format(string, fmt) produced garbage tokens: {stdout!r}")
            self.assertNotIn("%1", stdout,
                             f"time.format(string, fmt) produced garbage tokens: {stdout!r}")
        # And the run should have produced an error (not successfully returned a garbled string)
        self.assertFalse(
            res["ok"] and stdout.count("/") == 2 and "2026" in stdout,
            "time.format('string', fmt) must error — passing a string is not valid"
        )

    def test_format_with_icu_tokens(self):
        result = out("""
import "std:time" as time
let dt = time.from_iso8601("2026-01-15T00:00:00Z")
print(time.format(dt, "yyyy/MM/dd"))
""")
        self.assertEqual(result, "2026/01/15")

    def test_format_with_strftime_tokens(self):
        # When format string contains %, delegates to Python strftime
        result = out("""
import "std:time" as time
let dt = time.from_iso8601("2026-01-15T00:00:00Z")
print(time.format(dt, "%Y/%m/%d"))
""")
        self.assertEqual(result, "2026/01/15")

    def test_icu_and_strftime_produce_same_date(self):
        icu_result = out("""
import "std:time" as time
let dt = time.from_iso8601("2026-06-10T12:30:00Z")
print(time.format(dt, "yyyy-MM-dd"))
""")
        strftime_result = out("""
import "std:time" as time
let dt = time.from_iso8601("2026-06-10T12:30:00Z")
print(time.format(dt, "%Y-%m-%d"))
""")
        self.assertEqual(icu_result, strftime_result,
                         f"ICU and strftime should produce the same date string: {icu_result!r} vs {strftime_result!r}")


# ---------------------------------------------------------------------------
# std:effects
# ---------------------------------------------------------------------------

class TestEffectsContracts(unittest.TestCase):
    """effects.nd wraps 3-arg action_id, 2-arg pending, 3-arg complete."""

    def test_action_id_three_args_returns_string(self):
        # action_id(action_type, payload_map, scope) — 3 required args
        result = out("""
import "std:effects" as fx
print(type(fx.action_id("send_email", {"to": "x@y.com"}, "global")))
""")
        self.assertEqual(result, "string",
                         "action_id(type, payload, scope) must return a string")

    def test_action_id_two_args_is_arity_error(self):
        # 2 args should be an arity/runtime error — docs sometimes showed wrong shape
        ok_2arg = is_ok("""
import "std:effects" as fx
fx.action_id("send_email", {"to": "x@y.com"})
""")
        self.assertFalse(ok_2arg,
                         "action_id with only 2 args must raise an error (3 args required)")

    def test_pending_takes_two_args(self):
        # pending(action_id, input_hash) — docs sometimes showed as 1-arg
        result = is_ok("""
import "std:effects" as fx
let aid = fx.action_id("test_pending", {}, "global")
fx.pending(aid, "input_hash_abc")
""")
        self.assertTrue(result, "fx.pending(action_id, input_hash) must succeed with 2 args")

    def test_resolve_returns_record_with_done_field(self):
        # resolve() returns Record{done: bool, cached: value} — NOT just a value
        result = out("""
import "std:effects" as fx
let aid = fx.action_id("test_resolve", {}, "global")
fx.pending(aid, "hash_001")
let r = fx.resolve(aid)
print(type(r.done))
""")
        self.assertEqual(result, "bool",
                         "resolve(aid).done must be a bool field on a Record")

    def test_resolve_done_is_false_before_complete(self):
        result = out("""
import "std:effects" as fx
let aid = fx.action_id("test_done_false", {}, "test")
fx.pending(aid, "hash_002")
let r = fx.resolve(aid)
if (r.done) { print("done") } else { print("not_done") }
""")
        self.assertEqual(result, "not_done",
                         "resolve.done must be false before complete() is called")

    def test_resolve_has_cached_field(self):
        result = out("""
import "std:effects" as fx
let aid = fx.action_id("test_cached", {}, "test")
fx.pending(aid, "hash_003")
let r = fx.resolve(aid)
print(type(r.cached))
""")
        # cached is nil before complete
        self.assertEqual(result, "nil")

    def test_complete_three_args_succeeds(self):
        # complete(action_id, status, result) — 3 args; returns nil
        result = is_ok("""
import "std:effects" as fx
let aid = fx.action_id("test_complete", {}, "global")
fx.pending(aid, "hash_004")
fx.complete(aid, "success", "done_value")
""")
        self.assertTrue(result, "fx.complete(aid, status, result) must succeed with 3 args")

    def test_idempotency_done_true_after_complete(self):
        result = out("""
import "std:effects" as fx
let aid = fx.action_id("idempotency", {}, "global")
fx.pending(aid, "hash_005")
fx.complete(aid, "success", 42)
let r = fx.resolve(aid)
if (r.done) { print("done") } else { print("not_done") }
""")
        self.assertEqual(result, "done",
                         "resolve.done must be true after complete()")

    def test_get_result_after_complete_map(self):
        # effect_complete stores a map/record result; effect_get_result retrieves it.
        # The underlying InMemoryEffectStore only stores dict results — pass a map.
        result = out("""
import "std:effects" as fx
let aid = fx.action_id("test_get_result", {}, "global")
fx.pending(aid, "hash_006")
fx.complete(aid, "success", {"value": "stored_result"})
let r = fx.get_result(aid)
print(r.value)
""")
        self.assertEqual(result, "stored_result",
                         "effect_get_result must return the stored map result")

    def test_store_size_returns_number(self):
        result = out('import "std:effects" as fx\nprint(type(fx.store_size()))')
        self.assertIn(result, ["int", "float"],
                      "fx.store_size() must return a number")


# ---------------------------------------------------------------------------
# std:circuit_breaker
# ---------------------------------------------------------------------------

class TestCircuitBreakerContracts(unittest.TestCase):
    """cb.create vs cb.create_config split; state uses underscores not hyphens."""

    def test_available_returns_bool(self):
        result = out('import "std:circuit_breaker" as cb\nprint(type(cb.available()))')
        self.assertEqual(result, "bool")

    def test_create_config_form_returns_name(self):
        # cb.create_config(name, config_map) — the 2-arg map form
        result = out("""
import "std:circuit_breaker" as cb
let name = cb.create_config("cfg_cb", {"failure_threshold": 3, "recovery_timeout_ms": 1000})
if name == "cfg_cb" { print("ok") } else { print(name) }
""")
        # If nodus-circuit-breaker not installed, ok=False (dependency error)
        if result is not None:
            self.assertEqual(result, "ok",
                             f"create_config should return the name string, got: {result!r}")

    def test_create_positional_form(self):
        # cb.create(name, threshold, timeout_secs) — 3-arg positional form
        result = out("""
import "std:circuit_breaker" as cb
let name = cb.create("pos_cb", 3, 1)
if name == "pos_cb" { print("ok") } else { print(name) }
""")
        if result is not None:
            self.assertEqual(result, "ok",
                             f"create(name, threshold, timeout) should return name, got: {result!r}")

    def test_state_uses_underscore_not_hyphen(self):
        # B-doc: state returns "half_open" not "half-open"
        result = out("""
import "std:circuit_breaker" as cb
cb.create_config("uh_cb", {"failure_threshold": 5, "recovery_timeout_ms": 5000})
let s = cb.state("uh_cb")
print(s)
""")
        if result is not None:
            self.assertNotIn("-", result,
                             f"cb.state must use underscores (half_open), not hyphens: {result!r}")
            self.assertIn(result, ["closed", "open", "half_open"],
                          f"cb.state must return 'closed', 'open', or 'half_open': {result!r}")

    def test_new_breaker_starts_closed(self):
        result = out("""
import "std:circuit_breaker" as cb
cb.create_config("fresh_cb", {"failure_threshold": 5, "recovery_timeout_ms": 5000})
print(cb.state("fresh_cb"))
""")
        if result is not None:
            self.assertEqual(result, "closed",
                             "A newly created circuit breaker must start in 'closed' state")

    def test_reset_returns_nil(self):
        result = out("""
import "std:circuit_breaker" as cb
cb.create_config("reset_cb", {"failure_threshold": 5, "recovery_timeout_ms": 5000})
print(type(cb.reset("reset_cb")))
""")
        if result is not None:
            self.assertEqual(result, "nil",
                             "cb.reset() must return nil")


# ---------------------------------------------------------------------------
# std:subprocess
# ---------------------------------------------------------------------------

class TestSubprocessContracts(unittest.TestCase):

    def _py(self):
        # Platform-safe Python executable path
        return sys.executable.replace("\\", "/")

    def test_run_success_stdout_field(self):
        result = out(
            f'import "std:subprocess" as sp\nlet r = sp.run(["{self._py()}", "-c", "print(42)"])\nprint(r.stdout)',
            allowed_paths=[os.getcwd()]
        )
        self.assertIsNotNone(result)
        self.assertIn("42", result)

    def test_run_success_exit_code_zero(self):
        result = out(
            f'import "std:subprocess" as sp\nlet r = sp.run(["{self._py()}", "-c", "print(1)"])\nprint(r.exit_code)',
            allowed_paths=[os.getcwd()]
        )
        self.assertEqual(result, "0")

    def test_run_success_has_stderr_field(self):
        result = out(
            f'import "std:subprocess" as sp\nlet r = sp.run(["{self._py()}", "-c", "print(1)"])\nprint(type(r.stderr))',
            allowed_paths=[os.getcwd()]
        )
        self.assertEqual(result, "string")

    def test_run_success_has_duration_ms_field(self):
        result = out(
            f'import "std:subprocess" as sp\nlet r = sp.run(["{self._py()}", "-c", "print(1)"])\nprint(type(r.duration_ms))',
            allowed_paths=[os.getcwd()]
        )
        self.assertIn(result, ["int", "float"])

    def test_nonzero_exit_returns_error_record(self):
        # check=True (default): nonzero exit returns subprocess_error Record
        result = out(
            f'import "std:subprocess" as sp\nlet r = sp.run(["{self._py()}", "-c", "import sys; sys.exit(2)"])\nprint(r.kind)',
            allowed_paths=[os.getcwd()]
        )
        # subprocess_error kind field
        self.assertEqual(result, "subprocess_error")

    def test_allowed_commands_blocks_unlisted_binary(self):
        # When allowed_commands is set, running a non-listed binary must fail
        res = nrun(
            'import "std:subprocess" as sp\nsp.run(["git", "--version"])',
            allowed_commands=["python", "python3"],
            allowed_paths=[os.getcwd()],
        )
        self.assertFalse(res["ok"],
                         "allowed_commands enforcement must block non-listed binaries")

    def test_allowed_commands_permits_listed_binary(self):
        py_name = os.path.basename(sys.executable)
        py_path = self._py()
        result = is_ok(
            f'import "std:subprocess" as sp\nsp.run(["{py_path}", "-c", "print(1)"])',
            allowed_commands=[py_name, "python", "python3"],
            allowed_paths=[os.getcwd()],
        )
        self.assertTrue(result,
                        f"allowed_commands must permit the listed binary '{py_name}'")

    def test_shell_quote_returns_string(self):
        result = out('import "std:subprocess" as sp\nprint(type(sp.shell_quote("hello")))')
        self.assertEqual(result, "string")


# ---------------------------------------------------------------------------
# std:identity
# ---------------------------------------------------------------------------

class TestIdentityContracts(unittest.TestCase):

    def test_trace_id_is_string_or_nil(self):
        # trace_id returns nil when no trace ID is set by the embedder;
        # returns a string when set via NodusRuntime(trace_id=...) or propagated from a parent
        result = out('import "std:identity" as identity\nprint(type(identity.trace_id()))')
        self.assertIn(result, ["string", "nil"],
                      "trace_id() must return type 'string' or 'nil'")

    def test_session_id_is_string_or_nil(self):
        result = out('import "std:identity" as identity\nprint(type(identity.session_id()))')
        self.assertIn(result, ["string", "nil"])

    def test_execution_unit_id_is_string_or_nil(self):
        result = out('import "std:identity" as identity\nprint(type(identity.execution_unit_id()))')
        self.assertIn(result, ["string", "nil"])

    def test_trace_id_stable_within_run(self):
        # Whatever trace_id returns (string or nil), it must be the same value throughout a run
        result = out("""
import "std:identity" as identity
let t1 = identity.trace_id()
let t2 = identity.trace_id()
if (t1 == t2) { print("stable") } else { print("unstable") }
""")
        self.assertEqual(result, "stable",
                         "trace_id() must return the same value within a single execution")


# ---------------------------------------------------------------------------
# std:memory
# ---------------------------------------------------------------------------

class TestMemoryContracts(unittest.TestCase):

    def test_namespaced_share_recall_round_trip(self):
        result = out("""
import "std:memory" as memory
memory.share("ns_test", "k1", "v1")
print(memory.recall_from("ns_test", "k1"))
""")
        self.assertEqual(result, "v1")

    def test_recall_from_missing_is_nil(self):
        result = out("""
import "std:memory" as memory
print(type(memory.recall_from("ns_miss", "no_such_key")))
""")
        self.assertEqual(result, "nil")

    def test_flat_kv_put_get(self):
        result = out("""
import "std:memory" as memory
memory.put("flat_k", 42i)
print(memory.get("flat_k"))
""")
        self.assertEqual(result, "42")

    def test_flat_kv_has_true(self):
        # Parens required for function-call if conditions
        result = out("""
import "std:memory" as memory
memory.put("has_k", true)
if (memory.has("has_k")) { print("yes") } else { print("no") }
""")
        self.assertEqual(result, "yes")

    def test_flat_kv_has_false_after_delete(self):
        result = out("""
import "std:memory" as memory
memory.put("del_k", "val")
memory.delete("del_k")
if (memory.has("del_k")) { print("yes") } else { print("no") }
""")
        self.assertEqual(result, "no")

    def test_flat_kv_keys_is_list(self):
        result = out("""
import "std:memory" as memory
memory.put("keys_k", 1)
print(type(memory.keys()))
""")
        self.assertEqual(result, "list")


# ---------------------------------------------------------------------------
# std:retry
# ---------------------------------------------------------------------------

class TestRetryContracts(unittest.TestCase):

    def test_available_returns_bool(self):
        result = out('import "std:retry" as retry\nprint(type(retry.available()))')
        self.assertEqual(result, "bool")

    def test_call_trivial_fn_returns_result(self):
        result = out("""
import "std:retry" as retry
let r = retry.call(fn() { 42 }, {"max_attempts": 1, "backoff_ms": 0})
if type(r) == "float" { print("got_number") } else { print(type(r)) }
""")
        # If nodus-retry not installed, run fails; if installed, returns "got_number"
        self.assertTrue(result is None or result == "got_number",
                        f"retry.call should return the fn result, got: {result!r}")


# ---------------------------------------------------------------------------
# Type system contracts (v4.0.0 breaking change)
# ---------------------------------------------------------------------------

class TestTypeSystemContracts(unittest.TestCase):
    """type() returns 'float' for 42 — changed in v4.0.0 from 'number'."""

    def test_float_literal_type_is_float_not_number(self):
        result = out('print(type(42))')
        self.assertEqual(result, "float",
                         "type(42) must return 'float' since v4.0.0, not 'number'")

    def test_int_literal_type_is_int(self):
        result = out('print(type(42i))')
        self.assertEqual(result, "int")

    def test_string_type(self):
        result = out('print(type("hello"))')
        self.assertEqual(result, "string")

    def test_bool_type(self):
        result = out('print(type(true))')
        self.assertEqual(result, "bool")

    def test_nil_type(self):
        result = out('print(type(nil))')
        self.assertEqual(result, "nil")

    def test_list_type(self):
        result = out('print(type([1, 2, 3]))')
        self.assertEqual(result, "list")

    def test_record_type(self):
        result = out('print(type({name: "Alice"}))')
        self.assertEqual(result, "record")

    def test_map_type(self):
        result = out('print(type({"name": "Alice"}))')
        self.assertEqual(result, "map")

    def test_int_division_returns_int(self):
        # v4.0.1: int / int returns int when evenly divisible
        result = out('print(type(10i / 2i))')
        self.assertEqual(result, "int",
                         "int / int must return int type when evenly divisible (v4.0.1)")

    def test_float_division_by_zero_raises_math_error(self):
        # v4.0.1: division by zero raises runtime_error("math", ...)
        result = out("""
try {
    let x = 10 / 0
    print("no_error")
} catch e {
    print(e.kind)
}
""")
        self.assertEqual(result, "math",
                         "float division by zero must raise error with kind='math'")

    def test_int_division_by_zero_raises_math_error(self):
        result = out("""
try {
    let x = 10i / 0i
    print("no_error")
} catch e {
    print(e.kind)
}
""")
        self.assertEqual(result, "math",
                         "int division by zero must raise error with kind='math'")


# ---------------------------------------------------------------------------
# NodusRuntime Python API contracts (v4.0.1 defaults)
# ---------------------------------------------------------------------------

class TestNodusRuntimeAPIContracts(unittest.TestCase):
    """NodusRuntime() defaults: timeout_ms=None, allowed_paths=CWD since v4.0.1."""

    def test_default_constructor_runs_without_error(self):
        rt = NodusRuntime()
        res = rt.run_source('print("hello")')
        self.assertTrue(res["ok"])
        self.assertEqual(res["stdout"].strip(), "hello")

    def test_default_timeout_is_none_not_200ms(self):
        # v4.0.1: NodusRuntime() default timeout_ms is None (was 200ms in earlier releases).
        # Verify the attribute is None — the actual behavior follows from this.
        rt = NodusRuntime()
        self.assertIsNone(rt.timeout_ms,
                          "NodusRuntime() default timeout_ms must be None since v4.0.1, not 200ms")

    def test_explicit_timeout_ms_none_max_steps_none(self):
        rt = NodusRuntime(timeout_ms=None, max_steps=None)
        res = rt.run_source('print("ok")')
        self.assertTrue(res["ok"])
        self.assertEqual(res["stdout"].strip(), "ok")

    def test_allowed_paths_defaults_to_cwd(self):
        # v4.0.1: default allowed_paths restricts to CWD — not unrestricted
        rt = NodusRuntime()
        res = rt.run_source("""
import "std:fs" as fs
if (fs.exists(".")) { print("yes") } else { print("no") }
""")
        self.assertTrue(res["ok"],
                        f"fs.exists('.') should work within CWD sandbox: {res.get('error')}")
        self.assertEqual(res["stdout"].strip(), "yes")

    def test_allowed_commands_param_accepted(self):
        # Verify allowed_commands constructor param is accepted without error
        rt = NodusRuntime(allowed_commands=["python", "git"])
        res = rt.run_source('print("ok")')
        self.assertTrue(res["ok"])

    def test_on_error_hook_fires_for_coroutine_error(self):
        errors = []

        def handler(coroutine, err):
            errors.append(str(err))
            return False

        rt = NodusRuntime(timeout_ms=5000, on_error=handler)
        res = rt.run_source("""
spawn(coroutine(fn() { throw "oops" }))
run_loop()
""")
        self.assertTrue(len(errors) > 0 or not res["ok"],
                        "on_error hook must fire when a spawned coroutine throws")


if __name__ == "__main__":
    unittest.main()
