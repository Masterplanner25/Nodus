"""std:encoding — base64, hex, URL encoding builtins for Nodus VM."""

import base64 as _b64
import urllib.parse as _urlparse


def register(vm, registry) -> None:
    """Register encoding_* builtins onto the registry."""

    def _enc_err(message, category="decode_error", *, input=None):
        return vm.make_err(
            "encoding_error",
            message,
            payload={"category": category, "input": input},
        )

    def _to_bytes_enc(value, fname):
        if isinstance(value, bytes):
            return value
        if isinstance(value, str):
            return value.encode("utf-8")
        vm.runtime_error("type", f"{fname}: expected string or bytes")

    # ── Base64 ───────────────────────────────────────────────────────
    def builtin_encoding_base64_encode(data):
        b = _to_bytes_enc(data, "encoding.base64_encode")
        return _b64.b64encode(b).decode("ascii")

    def builtin_encoding_base64_decode(s):
        if not isinstance(s, str):
            vm.runtime_error("type", "encoding.base64_decode: expected a string")
        try:
            return _b64.b64decode(s)
        except Exception:
            return _enc_err(f"invalid base64: {s[:40]!r}", input=s[:40])

    def builtin_encoding_base64_url_encode(data):
        b = _to_bytes_enc(data, "encoding.base64_url_encode")
        return _b64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")

    def builtin_encoding_base64_url_decode(s):
        if not isinstance(s, str):
            vm.runtime_error("type", "encoding.base64_url_decode: expected a string")
        try:
            # Add padding back
            padded = s + "=" * (-len(s) % 4)
            return _b64.urlsafe_b64decode(padded)
        except Exception:
            return _enc_err(f"invalid URL-safe base64: {s[:40]!r}", input=s[:40])

    # ── Hex ──────────────────────────────────────────────────────────
    def builtin_encoding_hex_encode(data):
        if isinstance(data, bytes):
            return data.hex()
        if isinstance(data, str):
            return data.encode("utf-8").hex()
        vm.runtime_error("type", "encoding.hex_encode: expected string or bytes")

    def builtin_encoding_hex_encode_upper(data):
        if isinstance(data, bytes):
            return data.hex().upper()
        if isinstance(data, str):
            return data.encode("utf-8").hex().upper()
        vm.runtime_error("type", "encoding.hex_encode_upper: expected string or bytes")

    def builtin_encoding_hex_decode(s):
        if not isinstance(s, str):
            vm.runtime_error("type", "encoding.hex_decode: expected a string")
        try:
            return bytes.fromhex(s)
        except ValueError:
            return _enc_err(f"invalid hex string: {s[:40]!r}", input=s[:40])

    # ── URL encoding ─────────────────────────────────────────────────
    _RFC3986_SAFE = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.~"

    def builtin_encoding_url_encode(s):
        if not isinstance(s, str):
            vm.runtime_error("type", "encoding.url_encode: expected a string")
        return _urlparse.quote(s, safe=_RFC3986_SAFE)

    def builtin_encoding_url_decode(s):
        if not isinstance(s, str):
            vm.runtime_error("type", "encoding.url_decode: expected a string")
        try:
            return _urlparse.unquote(s)
        except Exception:
            return _enc_err(f"invalid percent-encoded string: {s[:40]!r}", input=s[:40])

    def builtin_encoding_url_encode_form(m):
        if not isinstance(m, dict):
            vm.runtime_error("type", "encoding.url_encode_form: expected a map")
        parts = []
        for k, v in m.items():
            k_enc = _urlparse.quote(str(k), safe="")
            if isinstance(v, list):
                for item in v:
                    parts.append(f"{k_enc}={_urlparse.quote(str(item), safe='').replace('%20', '+')}")
            else:
                v_enc = _urlparse.quote(str(v), safe="").replace("%20", "+")
                parts.append(f"{k_enc}={v_enc}")
        return "&".join(parts)

    def builtin_encoding_url_decode_form(s):
        if not isinstance(s, str):
            vm.runtime_error("type", "encoding.url_decode_form: expected a string")
        result = {}
        if not s:
            return result
        for part in s.split("&"):
            if "=" in part:
                k, _, v = part.partition("=")
            else:
                k, v = part, ""
            k = _urlparse.unquote_plus(k)
            v = _urlparse.unquote_plus(v)
            if k in result:
                existing = result[k]
                if isinstance(existing, list):
                    existing.append(v)
                else:
                    result[k] = [existing, v]
            else:
                result[k] = v
        return result

    # ── Registration ─────────────────────────────────────────────────
    registry.add("encoding_base64_encode", 1, builtin_encoding_base64_encode)
    registry.add("encoding_base64_decode", 1, builtin_encoding_base64_decode)
    registry.add("encoding_base64_url_encode", 1, builtin_encoding_base64_url_encode)
    registry.add("encoding_base64_url_decode", 1, builtin_encoding_base64_url_decode)
    registry.add("encoding_hex_encode", 1, builtin_encoding_hex_encode)
    registry.add("encoding_hex_encode_upper", 1, builtin_encoding_hex_encode_upper)
    registry.add("encoding_hex_decode", 1, builtin_encoding_hex_decode)
    registry.add("encoding_url_encode", 1, builtin_encoding_url_encode)
    registry.add("encoding_url_decode", 1, builtin_encoding_url_decode)
    registry.add("encoding_url_encode_form", 1, builtin_encoding_url_encode_form)
    registry.add("encoding_url_decode_form", 1, builtin_encoding_url_decode_form)
