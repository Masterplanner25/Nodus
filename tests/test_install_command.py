import io
from contextlib import redirect_stdout

import nodus as lang


def test_install_populates_modules_and_runtime_loads_dependency(tmp_path):
    registry_root = tmp_path / "registry"
    json_dep = registry_root / "json-1.2.0"
    json_dep.mkdir(parents=True)
    (json_dep / "nodus.toml").write_text(
        '[package]\nname = "json"\nversion = "1.2.0"\n',
        encoding="utf-8",
    )
    (json_dep / "module.nd").write_text('export let version = "1.2.0"\n', encoding="utf-8")

    project = tmp_path / "app"
    (project / ".nodus").mkdir(parents=True)
    (project / "src").mkdir()
    (project / "nodus.toml").write_text(
        "\n".join(
            [
                "[package]",
                'name = "app"',
                'version = "0.1.0"',
                "",
                "[dependencies]",
                'json = "1.2.0"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (project / ".nodus" / "registry.toml").write_text(
        '[packages.json."1.2.0"]\npath = "../../registry/json-1.2.0"\n',
        encoding="utf-8",
    )
    (project / "src" / "main.nd").write_text('import "json:module" as j\nprint(j.version)\n', encoding="utf-8")

    assert lang.main(["nodus", "install", "--project-root", str(project)]) == 0
    assert (project / ".nodus" / "modules" / "json" / "module.nd").is_file()

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = lang.main(["nodus", "run", str(project)])
    assert exit_code == 0
    assert stdout.getvalue() == "1.2.0\n"


def test_add_and_remove_commands_update_manifest_and_modules(tmp_path):
    registry_root = tmp_path / "registry"
    dep = registry_root / "json-1.2.0"
    dep.mkdir(parents=True)
    (dep / "nodus.toml").write_text(
        '[package]\nname = "json"\nversion = "1.2.0"\n',
        encoding="utf-8",
    )
    (dep / "module.nd").write_text("export let value = 1\n", encoding="utf-8")

    project = tmp_path / "app"
    (project / ".nodus").mkdir(parents=True)
    (project / "src").mkdir()
    (project / "src" / "main.nd").write_text("print(1)\n", encoding="utf-8")
    (project / "nodus.toml").write_text(
        "[package]\nname = \"app\"\nversion = \"0.1.0\"\n\n[dependencies]\n",
        encoding="utf-8",
    )
    (project / ".nodus" / "registry.toml").write_text(
        '[packages.json."1.2.0"]\npath = "../../registry/json-1.2.0"\n',
        encoding="utf-8",
    )

    assert lang.main(["nodus", "add", "json", "--project-root", str(project)]) == 0
    manifest_text = (project / "nodus.toml").read_text(encoding="utf-8")
    assert 'json = "1.2.0"' in manifest_text
    assert (project / ".nodus" / "modules" / "json").is_dir()

    assert lang.main(["nodus", "remove", "json", "--project-root", str(project)]) == 0
    manifest_text = (project / "nodus.toml").read_text(encoding="utf-8")
    assert 'json = "1.2.0"' not in manifest_text
    assert not (project / ".nodus" / "modules" / "json").exists()
