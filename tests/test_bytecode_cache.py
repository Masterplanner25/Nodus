import os

import nodus as lang

from nodus.runtime import bytecode_cache
from nodus.runtime.module_loader import ModuleLoader


def _write(tmp_path, name: str, content: str) -> str:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return str(path)


def _bump_mtime(path: str) -> None:
    current = os.stat(path).st_mtime_ns
    updated = current + 2_000_000_000
    os.utime(path, ns=(updated, updated))


def test_bytecode_cache_written_after_first_compile(tmp_path):
    main_path = _write(tmp_path, "main.nd", "let value = 1\n")

    loader = ModuleLoader(project_root=str(tmp_path))
    loader.load_module_from_path(main_path)

    cache_root = tmp_path / ".nodus" / "cache"
    files = sorted(cache_root.glob("*.nbc"))
    assert len(files) == 1
    cached = bytecode_cache.load_cached_bytecode(str(tmp_path), main_path)
    assert cached is not None
    assert cached.code.get("module_name") == os.path.abspath(main_path)


def test_bytecode_cache_reused_on_second_run(tmp_path, monkeypatch):
    main_path = _write(tmp_path, "main.nd", "let value = 1\n")
    ModuleLoader(project_root=str(tmp_path)).load_module_from_path(main_path)

    compile_calls = []
    original = ModuleLoader._compile_module

    def counting_compile(self, metadata):
        compile_calls.append(metadata.module_id)
        return original(self, metadata)

    monkeypatch.setattr(ModuleLoader, "_compile_module", counting_compile)

    loader = ModuleLoader(project_root=str(tmp_path))
    loader.load_module_from_path(main_path)

    assert compile_calls == []


def test_bytecode_cache_invalidates_when_source_changes(tmp_path, monkeypatch):
    main_path = _write(tmp_path, "main.nd", "let value = 1\n")
    ModuleLoader(project_root=str(tmp_path)).load_module_from_path(main_path)

    with open(main_path, "w", encoding="utf-8") as handle:
        handle.write("let value = 2\n")
    _bump_mtime(main_path)

    compile_calls = []
    original = ModuleLoader._compile_module

    def counting_compile(self, metadata):
        compile_calls.append(metadata.module_id)
        return original(self, metadata)

    monkeypatch.setattr(ModuleLoader, "_compile_module", counting_compile)

    loader = ModuleLoader(project_root=str(tmp_path))
    loader.load_module_from_path(main_path)

    assert compile_calls == [os.path.abspath(main_path)]


def test_bytecode_cache_invalidates_when_version_changes(tmp_path, monkeypatch):
    main_path = _write(tmp_path, "main.nd", "let value = 1\n")
    ModuleLoader(project_root=str(tmp_path)).load_module_from_path(main_path)

    compile_calls = []
    original = ModuleLoader._compile_module

    def counting_compile(self, metadata):
        compile_calls.append(metadata.module_id)
        return original(self, metadata)

    monkeypatch.setattr(ModuleLoader, "_compile_module", counting_compile)
    monkeypatch.setattr(bytecode_cache, "NODUS_BYTECODE_VERSION", bytecode_cache.NODUS_BYTECODE_VERSION + 1)

    loader = ModuleLoader(project_root=str(tmp_path))
    loader.load_module_from_path(main_path)

    assert compile_calls == [os.path.abspath(main_path)]


def test_cli_cache_clear_removes_cached_bytecode(tmp_path):
    (tmp_path / "nodus.toml").write_text('name = "demo"\nversion = "0.1.0"\n', encoding="utf-8")
    main_path = _write(tmp_path, "main.nd", "let value = 1\n")
    ModuleLoader(project_root=str(tmp_path)).load_module_from_path(main_path)

    cache_root = tmp_path / ".nodus" / "cache"
    assert any(cache_root.iterdir())

    exit_code = lang.main(["nodus", "cache", "clear", "--path", str(tmp_path)])

    assert exit_code == 0
    assert list(cache_root.iterdir()) == []
