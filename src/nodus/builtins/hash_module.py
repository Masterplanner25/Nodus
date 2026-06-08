"""std:hash — hashing and HMAC builtins for Nodus VM."""

import base64
import hashlib
import hmac as _hmac

from nodus.vm.types import BuiltinMethod, Record

_CHUNK = 65536


def _to_bytes(value):
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    return None


def _make_hash_record(digest: bytes, algorithm: str) -> Record:
    return Record({
        "to_hex": BuiltinMethod(lambda: digest.hex()),
        "to_hex_upper": BuiltinMethod(lambda: digest.hex().upper()),
        "to_base64": BuiltinMethod(lambda: base64.b64encode(digest).decode()),
        "to_base64_url": BuiltinMethod(lambda: base64.urlsafe_b64encode(digest).rstrip(b"=").decode()),
        "to_bytes": BuiltinMethod(lambda: digest),
        "algorithm": algorithm,
        "length": len(digest),
    }, kind="hash")


def register(vm, registry) -> None:
    """Register hash_* builtins onto the registry."""

    def _type_err(fname, value):
        return vm.make_err(
            "type_error",
            f"{fname}: data must be string or bytes, got {vm.builtin_type(value)}",
            payload={"category": "type_error", "input": None, "algorithm": None},
        )

    def _io_err(fname, msg):
        return vm.make_err("io_error", f"{fname}: {msg}",
                           payload={"category": "io_error", "input": None, "algorithm": None})

    def _state_err(fname):
        return vm.make_err("state_error", f"{fname}: builder already finalized",
                           payload={"category": "state_error", "input": None, "algorithm": None})

    def _ensure_allowed(path, op):
        vm._ensure_path_allowed(path, op)

    # ── One-shot hash functions ──────────────────────────────────────
    def _one_shot(alg_name, hashlib_name):
        def fn(data):
            b = _to_bytes(data)
            if b is None:
                return _type_err(f"hash.{alg_name}", data)
            digest = hashlib.new(hashlib_name, b).digest()
            return _make_hash_record(digest, alg_name)
        return fn

    # ── Builder factory ──────────────────────────────────────────────
    def _builder(alg_name, hashlib_name):
        def fn():
            h = hashlib.new(hashlib_name)
            state = {"done": False}

            def update(data):
                if state["done"]:
                    return _state_err(f"hash.{alg_name}_builder.update")
                b = _to_bytes(data)
                if b is None:
                    return _type_err(f"hash.{alg_name}_builder.update", data)
                h.update(b)
                return None

            def finalize():
                if state["done"]:
                    return _state_err(f"hash.{alg_name}_builder.finalize")
                state["done"] = True
                return _make_hash_record(h.digest(), alg_name)

            return Record({
                "update": BuiltinMethod(update),
                "finalize": BuiltinMethod(finalize),
                "algorithm": alg_name,
            }, kind="hash_builder")
        return fn

    # ── File hash functions ──────────────────────────────────────────
    def _file_hash(alg_name, hashlib_name):
        def fn(path):
            if not isinstance(path, str):
                vm.runtime_error("type", f"hash.{alg_name}_file: path must be a string")
            _ensure_allowed(path, f"hash.{alg_name}_file")
            try:
                h = hashlib.new(hashlib_name)
                with open(path, "rb") as f:
                    while True:
                        chunk = f.read(_CHUNK)
                        if not chunk:
                            break
                        h.update(chunk)
                return _make_hash_record(h.digest(), alg_name)
            except FileNotFoundError:
                return _io_err(f"hash.{alg_name}_file", f"file not found: {path!r}")
            except PermissionError:
                return _io_err(f"hash.{alg_name}_file", f"permission denied: {path!r}")
            except OSError as exc:
                return _io_err(f"hash.{alg_name}_file", str(exc))
        return fn

    # ── HMAC functions ───────────────────────────────────────────────
    def _hmac_fn(alg_name, hashlib_name):
        def fn(key, message):
            k = _to_bytes(key)
            if k is None:
                return _type_err(f"hash.hmac_{alg_name}", key)
            m = _to_bytes(message)
            if m is None:
                return _type_err(f"hash.hmac_{alg_name}", message)
            digest = _hmac.new(k, m, hashlib_name).digest()
            return _make_hash_record(digest, f"hmac-{alg_name}")
        return fn

    # ── Constant-time compare ────────────────────────────────────────
    def builtin_hash_compare(a, b):
        def _normalize(v):
            if isinstance(v, bytes):
                return v
            if isinstance(v, str):
                return v.encode("utf-8")
            if isinstance(v, Record) and v.kind == "hash":
                to_bytes_fn = v.fields.get("to_bytes")
                if isinstance(to_bytes_fn, BuiltinMethod):
                    return to_bytes_fn._fn()
            return None

        a_b = _normalize(a)
        b_b = _normalize(b)
        if a_b is None or b_b is None:
            return False
        return _hmac.compare_digest(a_b, b_b)

    # ── Algorithms: sha256, sha512, blake2b, sha1, md5 ──────────────
    _ALGS = [
        ("sha256", "sha256"),
        ("sha512", "sha512"),
        ("blake2b", "blake2b"),
        ("sha1", "sha1"),
        ("md5", "md5"),
    ]

    for nodus_name, py_name in _ALGS:
        registry.add(f"hash_{nodus_name}", 1, _one_shot(nodus_name, py_name))
        registry.add(f"hash_{nodus_name}_builder", 0, _builder(nodus_name, py_name))
        registry.add(f"hash_{nodus_name}_file", 1, _file_hash(nodus_name, py_name))
        registry.add(f"hash_hmac_{nodus_name}", 2, _hmac_fn(nodus_name, py_name))

    registry.add("hash_compare", 2, builtin_hash_compare)
