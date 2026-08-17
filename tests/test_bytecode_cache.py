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


# closes: #449
def test_bytecode_cache_invalidates_when_nodus_lang_version_changes(tmp_path, monkeypatch):
    """An upgraded nodus-lang must not reuse bytecode from the previous one.

    Distinct from `test_bytecode_cache_invalidates_when_version_changes` above,
    which bumps `NODUS_BYTECODE_VERSION` — the *bytecode format* version, frozen at
    4 since v1.0 and governed by #366. That number does not move when the compiler
    changes, and the cache key is only `(absolute path, mtime)`, so before this
    every cached module stayed compiled by the old compiler across an upgrade until
    its source was touched.

    That is not a performance nit: it silently withholds compiler-level correctness
    fixes. Demonstrated with the #411 fix itself — with a populated `.nodus/` cache,
    an upgraded runtime kept running the forgeable `@exactly_once` envelope and
    printed FORGED. Clearing the cache was the only thing that applied the fix.
    """
    main_path = _write(tmp_path, "main.nd", "let value = 1\n")
    ModuleLoader(project_root=str(tmp_path)).load_module_from_path(main_path)

    compile_calls = []
    original = ModuleLoader._compile_module

    def counting_compile(self, metadata):
        compile_calls.append(metadata.module_id)
        return original(self, metadata)

    monkeypatch.setattr(ModuleLoader, "_compile_module", counting_compile)
    # Source and mtime unchanged; only the nodus-lang version differs.
    monkeypatch.setattr(bytecode_cache, "__version__", "9.9.9")

    loader = ModuleLoader(project_root=str(tmp_path))
    loader.load_module_from_path(main_path)

    assert compile_calls == [os.path.abspath(main_path)]


def test_bytecode_cache_is_reused_when_the_version_is_unchanged(tmp_path, monkeypatch):
    """Positive control: the version check must not defeat caching entirely.

    Without this, a change that made every load miss would satisfy the test above
    and quietly turn the cache off.
    """
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
