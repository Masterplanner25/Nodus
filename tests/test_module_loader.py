import os

from nodus.tooling.runner import run_source


def _write(tmp_path, name: str, content: str) -> str:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return str(path)


def test_module_import_execution(tmp_path):
    util_path = _write(
        tmp_path,
        "util.nd",
        'export let value = 3\n',
    )
    main_path = _write(
        tmp_path,
        "main.nd",
        f'import {{ value }} from "{os.path.basename(util_path)}"\nprint(value)\n',
    )
    code = open(main_path, "r", encoding="utf-8").read()
    result, _vm = run_source(code, filename=main_path)
    assert result["ok"] is True
    assert result["stdout"].strip() == "3.0"


def test_module_caching(tmp_path):
    counter_path = _write(
        tmp_path,
        "counter.nd",
        "export let counter = 0\ncounter = counter + 1\n",
    )
    main_path = _write(
        tmp_path,
        "main.nd",
        f'import "{os.path.basename(counter_path)}" as a\nimport "{os.path.basename(counter_path)}" as b\nprint(a.counter)\nprint(b.counter)\n',
    )
    code = open(main_path, "r", encoding="utf-8").read()
    result, _vm = run_source(code, filename=main_path)
    assert result["ok"] is True
    assert result["stdout"].strip() == "1.0\n1.0"


def test_export_visibility(tmp_path):
    mod_path = _write(
        tmp_path,
        "mod.nd",
        "let hidden = 5\nexport let visible = 1\n",
    )
    main_path = _write(
        tmp_path,
        "main.nd",
        f'import {{ hidden }} from "{os.path.basename(mod_path)}"\n',
    )
    code = open(main_path, "r", encoding="utf-8").read()
    result, _vm = run_source(code, filename=main_path)
    assert result["ok"] is False
    assert result["error"]["type"] == "runtime"
    assert result["error"]["kind"] == "import"
