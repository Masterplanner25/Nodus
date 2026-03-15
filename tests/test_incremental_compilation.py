import io
import json
import os
from contextlib import redirect_stdout

import nodus as lang

from nodus.runtime.module_loader import ModuleLoader


def _write(tmp_path, name: str, content: str) -> str:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return str(path)


def _bump_mtime(path: str) -> None:
    current = os.stat(path).st_mtime_ns
    updated = current + 2_000_000_000
    os.utime(path, ns=(updated, updated))


def test_unchanged_modules_skip_reparsing_and_recompilation(tmp_path, monkeypatch):
    (tmp_path / "nodus.toml").write_text('name = "demo"\nversion = "0.1.0"\n', encoding="utf-8")
    util_path = _write(tmp_path, "util.nd", "export let value = 1\n")
    main_path = _write(tmp_path, "main.nd", 'import "./util.nd" as util\nprint(util.value)\n')

    ModuleLoader(project_root=str(tmp_path)).load_module_from_path(main_path)

    parse_calls = []
    compile_calls = []
    original_parse = ModuleLoader._parse_module
    original_compile = ModuleLoader._compile_module

    def counting_parse(self, module_id, **kwargs):
        parse_calls.append(module_id)
        return original_parse(self, module_id, **kwargs)

    def counting_compile(self, metadata):
        compile_calls.append(metadata.module_id)
        return original_compile(self, metadata)

    monkeypatch.setattr(ModuleLoader, "_parse_module", counting_parse)
    monkeypatch.setattr(ModuleLoader, "_compile_module", counting_compile)

    ModuleLoader(project_root=str(tmp_path)).load_module_from_path(main_path)

    assert parse_calls == []
    assert compile_calls == []


def test_dependency_change_triggers_recompilation(tmp_path, monkeypatch):
    (tmp_path / "nodus.toml").write_text('name = "demo"\nversion = "0.1.0"\n', encoding="utf-8")
    util_path = _write(tmp_path, "util.nd", "export let value = 1\n")
    main_path = _write(tmp_path, "main.nd", 'import "./util.nd" as util\nprint(util.value)\n')

    ModuleLoader(project_root=str(tmp_path)).load_module_from_path(main_path)

    with open(util_path, "w", encoding="utf-8") as handle:
        handle.write("export let value = 2\n")
    _bump_mtime(util_path)

    compile_calls = []
    original_compile = ModuleLoader._compile_module

    def counting_compile(self, metadata):
        compile_calls.append(metadata.module_id)
        return original_compile(self, metadata)

    monkeypatch.setattr(ModuleLoader, "_compile_module", counting_compile)

    ModuleLoader(project_root=str(tmp_path)).load_module_from_path(main_path)

    assert set(compile_calls) == {os.path.abspath(main_path), os.path.abspath(util_path)}


def test_dependency_graph_persists_and_cli_prints_it(tmp_path):
    (tmp_path / "nodus.toml").write_text('name = "demo"\nversion = "0.1.0"\n', encoding="utf-8")
    util_path = _write(tmp_path, "util.nd", "export let value = 1\n")
    main_path = _write(tmp_path, "main.nd", 'import "./util.nd" as util\nprint(util.value)\n')

    ModuleLoader(project_root=str(tmp_path)).load_module_from_path(main_path)

    graph_path = tmp_path / ".nodus" / "deps.json"
    assert graph_path.is_file()

    payload = json.loads(graph_path.read_text(encoding="utf-8"))
    modules = payload["modules"]
    assert os.path.abspath(main_path) in modules
    assert os.path.abspath(util_path) in modules
    assert modules[os.path.abspath(main_path)]["imports"] == [os.path.abspath(util_path)]
    assert modules[os.path.abspath(util_path)]["imports"] == []

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = lang.main(["nodus", "deps", "--project-root", str(tmp_path)])

    assert exit_code == 0
    cli_payload = json.loads(stdout.getvalue())
    assert cli_payload == payload
