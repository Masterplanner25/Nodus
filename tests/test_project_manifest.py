import io
import os
from contextlib import redirect_stdout

import nodus as lang
from nodus.tooling.project import load_project


def test_project_manifest_parses_package_table(tmp_path):
    manifest = tmp_path / "nodus.toml"
    manifest.write_text(
        "\n".join(
            [
                "[package]",
                'name = "example"',
                'version = "0.1.0"',
                "",
                "[dependencies]",
                'json = "1.0.0"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    project = load_project(str(tmp_path))

    assert project.name == "example"
    assert project.version == "0.1.0"
    assert project.dependencies["json"].kind == "version"
    assert project.dependencies["json"].value == "1.0.0"


def test_nodus_init_creates_manifest_and_src_main(tmp_path):
    exit_code = lang.main(["nodus", "init", "--project-root", str(tmp_path)])

    assert exit_code == 0
    manifest_path = tmp_path / "nodus.toml"
    entry_path = tmp_path / "src" / "main.nd"
    assert manifest_path.is_file()
    assert entry_path.is_file()
    manifest_text = manifest_path.read_text(encoding="utf-8")
    assert "[package]" in manifest_text
    assert '[dependencies]' in manifest_text


def test_nodus_run_accepts_project_directory(tmp_path):
    (tmp_path / "nodus.toml").write_text(
        "\n".join(
            [
                "[package]",
                'name = "demo"',
                'version = "0.1.0"',
                "",
                "[dependencies]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "main.nd").write_text('print("project run")\n', encoding="utf-8")

    current = os.getcwd()
    stdout = io.StringIO()
    try:
        os.chdir(tmp_path)
        with redirect_stdout(stdout):
            exit_code = lang.main(["nodus", "run", str(tmp_path)])
    finally:
        os.chdir(current)

    assert exit_code == 0
    assert stdout.getvalue() == "project run\n"
