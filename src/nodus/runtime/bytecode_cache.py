"""Disk cache for compiled Nodus module bytecode."""

from __future__ import annotations

import hashlib
import os
import pickle

from nodus.runtime.module import ModuleBytecode, NODUS_BYTECODE_VERSION
from nodus.tooling.project import NODUS_DIRNAME


CACHE_DIRNAME = "cache"
CACHE_EXTENSION = ".nbc"


def cache_dir(project_root: str) -> str:
    return os.path.join(os.path.abspath(project_root), NODUS_DIRNAME, CACHE_DIRNAME)


def ensure_cache_dir(project_root: str) -> str:
    root = cache_dir(project_root)
    os.makedirs(root, exist_ok=True)
    return root


def source_mtime_ns(module_path: str) -> int:
    return os.stat(module_path).st_mtime_ns


def cache_key(module_path: str, mtime_ns: int) -> str:
    normalized_path = os.path.abspath(module_path)
    digest = hashlib.sha256(f"{normalized_path}\0{mtime_ns}".encode("utf-8")).hexdigest()
    return digest


def cache_path(project_root: str, module_path: str, mtime_ns: int) -> str:
    filename = f"{cache_key(module_path, mtime_ns)}{CACHE_EXTENSION}"
    return os.path.join(cache_dir(project_root), filename)


def load_cached_bytecode(project_root: str | None, module_path: str) -> ModuleBytecode | None:
    if project_root is None or not os.path.isfile(module_path):
        return None
    mtime_ns = source_mtime_ns(module_path)
    path = cache_path(project_root, module_path, mtime_ns)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as handle:
            payload = pickle.load(handle)
    except Exception:
        return None
    if not _is_valid_cache_payload(payload, module_path, mtime_ns):
        return None
    raw_unit = payload.get("module_bytecode")
    if not isinstance(raw_unit, dict):
        return None
    return ModuleBytecode.from_cache_payload(raw_unit)


def write_cached_bytecode(project_root: str | None, module_path: str, module_bytecode: ModuleBytecode) -> str | None:
    if project_root is None or not os.path.isfile(module_path):
        return None
    mtime_ns = source_mtime_ns(module_path)
    final_path = cache_path(project_root, module_path, mtime_ns)
    ensure_cache_dir(project_root)
    payload = {
        "cache_version": NODUS_BYTECODE_VERSION,
        "module_path": os.path.abspath(module_path),
        "mtime_ns": mtime_ns,
        "module_bytecode": module_bytecode.to_cache_payload(),
    }
    temp_path = final_path + ".tmp"
    with open(temp_path, "wb") as handle:
        pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(temp_path, final_path)
    return final_path


def clear_bytecode_cache(project_root: str) -> int:
    root = cache_dir(project_root)
    if not os.path.isdir(root):
        return 0
    removed = 0
    for entry in os.scandir(root):
        if not entry.is_file():
            continue
        os.remove(entry.path)
        removed += 1
    return removed


def _is_valid_cache_payload(payload: object, module_path: str, mtime_ns: int) -> bool:
    if not isinstance(payload, dict):
        return False
    return (
        payload.get("cache_version") == NODUS_BYTECODE_VERSION
        and payload.get("module_path") == os.path.abspath(module_path)
        and payload.get("mtime_ns") == mtime_ns
    )
