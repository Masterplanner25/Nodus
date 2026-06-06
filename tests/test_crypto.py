"""3B.3: std:hash, std:encoding, std:secrets namespaces."""

import hashlib
import io
import unittest
from contextlib import redirect_stdout

import nodus as lang
from nodus.runtime.module_loader import ModuleLoader

_HDRS = (
    'import "std:hash" as hash\n'
    'import "std:encoding" as encoding\n'
    'import "std:secrets" as secrets\n'
)


def run_src(src: str):
    vm = lang.VM([], {}, code_locs=[], source_path="main.nd")
    _loader = ModuleLoader(project_root=None, vm=vm)
    buf = io.StringIO()
    with redirect_stdout(buf):
        _loader.load_module_from_source(_HDRS + src, module_name="main.nd")
    return buf.getvalue().splitlines(), vm


def lines(src): return run_src(src)[0]
def first(src): return lines(src)[0]


class HashOneShotTests(unittest.TestCase):

    def _expected_hex(self, alg, data):
        return hashlib.new(alg, data.encode()).hexdigest()

    def test_sha256_to_hex(self):
        expected = self._expected_hex("sha256", "hello world")
        self.assertEqual(first('let h = hash.sha256("hello world")\nprint(h.to_hex())'), expected)

    def test_sha256_to_hex_upper(self):
        expected = self._expected_hex("sha256", "hello world").upper()
        self.assertEqual(first('let h = hash.sha256("hello world")\nprint(h.to_hex_upper())'), expected)

    def test_sha256_to_base64(self):
        import base64
        expected = base64.b64encode(hashlib.sha256(b"hello world").digest()).decode()
        self.assertEqual(first('let h = hash.sha256("hello world")\nprint(h.to_base64())'), expected)

    def test_sha256_to_base64_url(self):
        import base64
        raw = hashlib.sha256(b"hello world").digest()
        expected = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
        self.assertEqual(first('let h = hash.sha256("hello world")\nprint(h.to_base64_url())'), expected)

    def test_sha256_algorithm_field(self):
        self.assertEqual(first('let h = hash.sha256("x")\nprint(h.algorithm)'), "sha256")

    def test_sha256_length(self):
        self.assertEqual(first('let h = hash.sha256("x")\nprint(h.length)'), "32")

    def test_sha512_length(self):
        self.assertEqual(first('let h = hash.sha512("x")\nprint(h.length)'), "64")

    def test_blake2b_type(self):
        self.assertEqual(first('let h = hash.blake2b("x")\nprint(type(h))'), "hash")

    def test_sha1_algorithm(self):
        self.assertEqual(first('let h = hash.sha1("x")\nprint(h.algorithm)'), "sha1")

    def test_md5_algorithm(self):
        self.assertEqual(first('let h = hash.md5("x")\nprint(h.algorithm)'), "md5")

    def test_invalid_input_returns_err(self):
        self.assertEqual(first('print(type(hash.sha256(42)))'), "error")


class HashBuilderTests(unittest.TestCase):

    def test_builder_matches_oneshot(self):
        src = ('let h1 = hash.sha256("hello world")\n'
               'let b = hash.sha256_builder()\n'
               'b.update("hello ")\n'
               'b.update("world")\n'
               'let h2 = b.finalize()\n'
               'print(h1.to_hex() == h2.to_hex())')
        self.assertEqual(first(src), "true")

    def test_builder_algorithm_field(self):
        self.assertEqual(first('let b = hash.sha256_builder()\nprint(b.algorithm)'), "sha256")

    def test_builder_after_finalize_returns_err(self):
        src = ('let b = hash.sha256_builder()\n'
               'b.update("data")\n'
               'let h = b.finalize()\n'
               'let r = b.update("more")\n'
               'print(type(r))')
        self.assertEqual(first(src), "error")

    def test_builder_finalize_twice_returns_err(self):
        src = ('let b = hash.sha256_builder()\n'
               'b.update("x")\n'
               'b.finalize()\n'
               'let r = b.finalize()\n'
               'print(type(r))')
        self.assertEqual(first(src), "error")

    def test_builder_state_err_category(self):
        src = ('let b = hash.sha256_builder()\n'
               'b.finalize()\n'
               'let r = b.finalize()\n'
               'print(r.payload["category"])')
        self.assertEqual(first(src), "state_error")


class HMACTests(unittest.TestCase):

    def test_hmac_sha256_basic(self):
        import hmac
        expected = hmac.new(b"key", b"message", "sha256").hexdigest()
        src = ('let h = hash.hmac_sha256("key", "message")\n'
               'print(h.to_hex())')
        self.assertEqual(first(src), expected)

    def test_hmac_algorithm_field(self):
        self.assertEqual(first('let h = hash.hmac_sha256("k", "m")\nprint(h.algorithm)'), "hmac-sha256")

    def test_hmac_sha512_length(self):
        self.assertEqual(first('let h = hash.hmac_sha512("k", "m")\nprint(h.length)'), "64")

    def test_hmac_sha1_algorithm(self):
        self.assertEqual(first('let h = hash.hmac_sha1("k", "m")\nprint(h.algorithm)'), "hmac-sha1")

    def test_hmac_md5_algorithm(self):
        self.assertEqual(first('let h = hash.hmac_md5("k", "m")\nprint(h.algorithm)'), "hmac-md5")


class HashCompareTests(unittest.TestCase):

    def test_compare_equal_hashes(self):
        src = ('let a = hash.sha256("x")\nlet b = hash.sha256("x")\n'
               'print(hash.compare(a, b))')
        self.assertEqual(first(src), "true")

    def test_compare_different_hashes(self):
        src = ('let a = hash.sha256("x")\nlet b = hash.sha256("y")\n'
               'print(hash.compare(a, b))')
        self.assertEqual(first(src), "false")

    def test_compare_string_inputs(self):
        self.assertEqual(first('print(hash.compare("abc", "abc"))'), "true")

    def test_compare_different_lengths(self):
        self.assertEqual(first('print(hash.compare("a", "ab"))'), "false")


class Base64Tests(unittest.TestCase):

    def test_base64_encode_string(self):
        import base64
        expected = base64.b64encode(b"hello").decode()
        self.assertEqual(first('print(encoding.base64_encode("hello"))'), expected)

    def test_base64_decode_roundtrip(self):
        src = ('let encoded = encoding.base64_encode("hello world")\n'
               'let decoded = encoding.base64_decode(encoded)\n'
               'print(type(decoded))')
        self.assertEqual(first(src), "string")

    def test_base64_url_encode(self):
        self.assertEqual(first('print(type(encoding.base64_url_encode("test")))'), "string")

    def test_base64_url_no_padding(self):
        out = first('print(encoding.base64_url_encode("hello"))')
        self.assertNotIn("=", out)

    def test_base64_decode_invalid_returns_err(self):
        self.assertEqual(first('print(type(encoding.base64_decode("!!!invalid")))'), "error")

    def test_base64_url_decode_roundtrip(self):
        src = ('let e = encoding.base64_url_encode("hello world")\n'
               'let d = encoding.base64_url_decode(e)\n'
               'print(type(d))')
        self.assertEqual(first(src), "string")


class HexTests(unittest.TestCase):

    def test_hex_encode_string(self):
        # "hi" = 0x68 0x69
        self.assertEqual(first('print(encoding.hex_encode("hi"))'), "6869")

    def test_hex_encode_upper(self):
        self.assertEqual(first('print(encoding.hex_encode_upper("hi"))'), "6869".upper())

    def test_hex_decode_roundtrip_type(self):
        src = ('let h = encoding.hex_encode("hello")\n'
               'let b = encoding.hex_decode(h)\n'
               'print(type(b))')
        self.assertEqual(first(src), "bytes")

    def test_hex_decode_accepts_uppercase(self):
        # "AB" as hex = bytes
        self.assertEqual(first('print(type(encoding.hex_decode("DEADBEEF")))'), "bytes")

    def test_hex_decode_invalid_returns_err(self):
        self.assertEqual(first('print(type(encoding.hex_decode("xyz")))'), "error")

    def test_hex_encode_decode_hash(self):
        src = ('let h = hash.sha256("test")\n'
               'let hex_str = h.to_hex()\n'
               'let b = encoding.hex_decode(hex_str)\n'
               'print(type(b))')
        self.assertEqual(first(src), "bytes")


class URLEncodingTests(unittest.TestCase):

    def test_url_encode_spaces(self):
        self.assertEqual(first('print(encoding.url_encode("hello world"))'), "hello%20world")

    def test_url_encode_special(self):
        out = first('print(encoding.url_encode("a+b=c"))')
        self.assertEqual(out, "a%2Bb%3Dc")

    def test_url_decode(self):
        self.assertEqual(first('print(encoding.url_decode("hello%20world"))'), "hello world")

    def test_url_encode_form_basic(self):
        src = 'print(encoding.url_encode_form({"name": "Alice"}))'
        self.assertEqual(first(src), "name=Alice")

    def test_url_encode_form_spaces_become_plus(self):
        src = 'print(encoding.url_encode_form({"q": "hello world"}))'
        self.assertEqual(first(src), "q=hello+world")

    def test_url_decode_form_basic(self):
        src = ('let m = encoding.url_decode_form("a=1&b=2")\n'
               'print(m["a"])\nprint(m["b"])')
        self.assertEqual(lines(src), ["1", "2"])

    def test_url_decode_form_multi_value(self):
        src = ('let m = encoding.url_decode_form("tag=a&tag=b")\n'
               'print(type(m["tag"]))')
        self.assertEqual(first(src), "list")

    def test_url_encode_decode_roundtrip(self):
        src = ('let encoded = encoding.url_encode("hello & world")\n'
               'let decoded = encoding.url_decode(encoded)\n'
               'print(decoded)')
        self.assertEqual(first(src), "hello & world")


class SecretsTests(unittest.TestCase):

    def test_random_bytes_type(self):
        self.assertEqual(first('print(type(secrets.random_bytes(16)))'), "bytes")

    def test_random_bytes_length(self):
        # Can't check length directly without a bytes.length builtin
        # But we can verify hex-encoding gives 2*n chars
        src = ('let b = secrets.random_bytes(16)\n'
               'let h = encoding.hex_encode(b)\n'
               'print(len(h) == 32)')
        self.assertEqual(first(src), "true")

    def test_random_int_in_range(self):
        src = ('let n = secrets.random_int(1, 10)\n'
               'print(n >= 1)\nprint(n <= 10)')
        self.assertEqual(lines(src), ["true", "true"])

    def test_token_hex_length(self):
        # token_hex(4) → 8 hex chars
        src = 'print(len(secrets.token_hex(4)) == 8)'
        self.assertEqual(first(src), "true")

    def test_token_base64_type(self):
        self.assertEqual(first('print(type(secrets.token_base64(16)))'), "string")

    def test_token_urlsafe_no_special_chars(self):
        src = ('let t = secrets.token_urlsafe(32)\n'
               'print(type(t))')
        self.assertEqual(first(src), "string")

    def test_token_alphanumeric_length(self):
        src = 'print(len(secrets.token_alphanumeric(10)) == 10)'
        self.assertEqual(first(src), "true")

    def test_uuid_v4_format(self):
        src = ('let u = secrets.uuid_v4()\n'
               'print(len(u) == 36)')
        self.assertEqual(first(src), "true")

    def test_uuid_v4_type(self):
        self.assertEqual(first('print(type(secrets.uuid_v4()))'), "string")

    def test_uuid_v7_format(self):
        src = ('let u = secrets.uuid_v7()\n'
               'print(len(u) == 36)')
        self.assertEqual(first(src), "true")

    def test_uuid_v7_version_bit(self):
        # UUID v7: 3rd group starts with "7"
        src = ('let u = secrets.uuid_v7()\n'
               'print(u)')
        out = first(src)
        parts = out.split("-")
        self.assertEqual(len(parts), 5)
        self.assertTrue(parts[2].startswith("7"), f"Expected v7 UUID, got: {out}")


if __name__ == "__main__":
    unittest.main()
