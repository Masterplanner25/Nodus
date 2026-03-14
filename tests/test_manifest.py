import os

from nodus.tooling.project import load_project


def test_manifest_parsing(tmp_path):
    manifest = tmp_path / "nodus.toml"
    manifest.write_text(
        '\n'.join(
            [
                'name = "demo"',
                'version = "0.1.0"',
                "",
                "[dependencies]",
                'json = "^1.0"',
                'utils = { path = "../utils" }',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    project = load_project(str(tmp_path))
    assert project.name == "demo"
    assert project.dependencies["json"].kind == "version"
    assert project.dependencies["utils"].kind == "path"
    assert os.path.basename(project.manifest_path) == "nodus.toml"
