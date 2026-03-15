import os

from nodus.tooling.runner import run_source


def _write(tmp_path, name: str, content: str) -> str:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return str(path)


def test_module_globals_isolated(tmp_path):
    mod_a = _write(
        tmp_path,
        "a.nd",
        "export let value = 1\n",
    )
    mod_b = _write(
        tmp_path,
        "b.nd",
        "export let value = 2\n",
    )
    main_path = _write(
        tmp_path,
        "main.nd",
        f'import "{os.path.basename(mod_a)}" as a\nimport "{os.path.basename(mod_b)}" as b\nprint(a.value)\nprint(b.value)\n',
    )
    code = open(main_path, "r", encoding="utf-8").read()
    result, _vm = run_source(code, filename=main_path)
    assert result["ok"] is True
    assert result["stdout"].strip() == "1.0\n2.0"


def test_named_imports_are_live_bindings(tmp_path):
    shared = _write(
        tmp_path,
        "shared.nd",
        "export let value = 1\n",
    )
    main_path = _write(
        tmp_path,
        "main.nd",
        f'import {{ value }} from "{os.path.basename(shared)}"\n'
        "print(value)\n"
        "value = value + 1\n"
        "print(value)\n",
    )
    code = open(main_path, "r", encoding="utf-8").read()
    result, _vm = run_source(code, filename=main_path)
    assert result["ok"] is True
    assert result["stdout"].strip() == "1.0\n2.0"


def test_alias_module_accesses_live_exports(tmp_path):
    shared = _write(
        tmp_path,
        "counter.nd",
        "export let value = 1\n",
    )
    main_path = _write(
        tmp_path,
        "main.nd",
        f'import "{os.path.basename(shared)}" as counter\n'
        "print(counter.value)\n"
        "counter.value = counter.value + 1\n"
        "print(counter.value)\n",
    )
    code = open(main_path, "r", encoding="utf-8").read()
    result, _vm = run_source(code, filename=main_path)
    assert result["ok"] is True
    assert result["stdout"].strip() == "1.0\n2.0"
