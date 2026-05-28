"""std:secrets — CSPRNG, token, UUID builtins for Nodus VM."""

import os
import secrets as _sec
import struct
import uuid as _uuid


def _uuid_v7() -> str:
    """UUID v7: timestamp-prefixed random UUID per RFC 9562."""
    import time as _t
    ms = int(_t.time() * 1000)
    rand = _sec.token_bytes(10)  # 80 bits of randomness
    # Layout: [0:48] = ms, [48:52] = 0111 (version 7), [52:64] = 12 rand bits
    # [64:66] = 10 (variant), [66:128] = 62 rand bits
    ms_hi = (ms >> 16) & 0xFFFFFFFF
    ms_lo = ms & 0xFFFF
    rand_a = (struct.unpack(">H", rand[:2])[0]) & 0x0FFF
    rand_b = (struct.unpack(">Q", rand[2:])[0]) & 0x3FFFFFFFFFFFFFFF
    ver_rand_a = 0x7000 | rand_a
    var_rand_b = 0x8000000000000000 | rand_b
    raw = struct.pack(">IHH", ms_hi, ms_lo, ver_rand_a) + struct.pack(">Q", var_rand_b)
    return str(_uuid.UUID(bytes=raw))


def register(vm, registry) -> None:
    """Register secrets_* builtins onto the registry."""

    def _to_int(v, name):
        if isinstance(v, float) and v.is_integer():
            return int(v)
        if isinstance(v, int) and not isinstance(v, bool):
            return v
        vm.runtime_error("type", f"secrets.{name}: expected integer")

    def builtin_secrets_random_bytes(n):
        n = _to_int(n, "random_bytes")
        if n < 0:
            vm.runtime_error("value", "secrets.random_bytes: n must be non-negative")
        return _sec.token_bytes(n)

    def builtin_secrets_random_int(lo, hi):
        lo = _to_int(lo, "random_int")
        hi = _to_int(hi, "random_int")
        if lo > hi:
            vm.runtime_error("value", f"secrets.random_int: min ({lo}) > max ({hi})")
        return _sec.randbelow(hi - lo + 1) + lo

    def builtin_secrets_token_hex(n_bytes):
        n_bytes = _to_int(n_bytes, "token_hex")
        if n_bytes <= 0:
            vm.runtime_error("value", "secrets.token_hex: n_bytes must be positive")
        return _sec.token_hex(n_bytes)

    def builtin_secrets_token_base64(n_bytes):
        n_bytes = _to_int(n_bytes, "token_base64")
        if n_bytes <= 0:
            vm.runtime_error("value", "secrets.token_base64: n_bytes must be positive")
        import base64 as _b64
        return _b64.b64encode(_sec.token_bytes(n_bytes)).decode("ascii")

    def builtin_secrets_token_urlsafe(n_bytes):
        n_bytes = _to_int(n_bytes, "token_urlsafe")
        if n_bytes <= 0:
            vm.runtime_error("value", "secrets.token_urlsafe: n_bytes must be positive")
        return _sec.token_urlsafe(n_bytes)

    _ALNUM = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

    def builtin_secrets_token_alphanumeric(n_chars):
        n_chars = _to_int(n_chars, "token_alphanumeric")
        if n_chars <= 0:
            vm.runtime_error("value", "secrets.token_alphanumeric: n_chars must be positive")
        return "".join(_sec.choice(_ALNUM) for _ in range(n_chars))

    def builtin_secrets_uuid_v4():
        return str(_uuid.uuid4())

    def builtin_secrets_uuid_v7():
        return _uuid_v7()

    registry.add("secrets_random_bytes", 1, builtin_secrets_random_bytes)
    registry.add("secrets_random_int", 2, builtin_secrets_random_int)
    registry.add("secrets_token_hex", 1, builtin_secrets_token_hex)
    registry.add("secrets_token_base64", 1, builtin_secrets_token_base64)
    registry.add("secrets_token_urlsafe", 1, builtin_secrets_token_urlsafe)
    registry.add("secrets_token_alphanumeric", 1, builtin_secrets_token_alphanumeric)
    registry.add("secrets_uuid_v4", 0, builtin_secrets_uuid_v4)
    registry.add("secrets_uuid_v7", 0, builtin_secrets_uuid_v7)
