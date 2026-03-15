import os

from nodus.runtime.module import NodusModule
from nodus.tooling.loader import run_source as run_with_loader
from nodus.tooling.runner import run_source


def _write(tmp_path, name: str, content: str) -> str:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return str(path)


def test_runtime_loader_exposes_module_object_alias(tmp_path):
    module_path = _write(
        tmp_path,
        "mathx.nd",
        "export let value = 4\n"
        "export fn inc() {\n"
        "    return value + 1\n"
        "}\n",
    )
    main_path = _write(
        tmp_path,
        "main.nd",
        f'import "{os.path.basename(module_path)}" as mathx\n',
    )
    vm = run_with_loader(open(main_path, "r", encoding="utf-8").read(), source_path=main_path)
    module = vm.globals["mathx"]
    assert isinstance(module, NodusModule)
    assert module.kind == "module"
    assert module.path == os.path.abspath(module_path)
    assert module.get_export("value") == 4.0
    assert module.get_export("inc")() == 5.0
    module.set_export("value", 6.0)
    assert module.get_export("value") == 6.0


def test_module_executes_once_when_imported_multiple_times(tmp_path):
    module_path = _write(
        tmp_path,
        "once.nd",
        "export let counter = 0\n"
        "counter = counter + 1\n",
    )
    main_path = _write(
        tmp_path,
        "main.nd",
        f'import "{os.path.basename(module_path)}" as a\n'
        f'import "{os.path.basename(module_path)}" as b\n'
        "print(a.counter)\n"
        "print(b.counter)\n",
    )
    code = open(main_path, "r", encoding="utf-8").read()
    result, _vm = run_source(code, filename=main_path)
    assert result["ok"] is True
    assert result["stdout"].strip() == "1.0\n1.0"
