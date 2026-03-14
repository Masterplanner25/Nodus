from nodus.tooling.installer import install_project
from nodus.tooling.project import load_project, read_lockfile
from nodus.tooling.resolver import resolve_project_dependencies


def test_installer_copies_path_dependency_into_nodus_modules(tmp_path):
    dependency = tmp_path / "utils"
    dependency.mkdir()
    (dependency / "nodus.toml").write_text('name = "utils"\nversion = "1.2.3"\n', encoding="utf-8")
    (dependency / "strings.nd").write_text('export fn upper(value) { return value }\n', encoding="utf-8")

    project = tmp_path / "app"
    project.mkdir()
    (project / "nodus.toml").write_text(
        '\n'.join(
            [
                'name = "app"',
                'version = "0.1.0"',
                "",
                "[dependencies]",
                'utils = { path = "../utils" }',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = load_project(str(project))
    resolution = resolve_project_dependencies(config, update=True)
    installed = install_project(config, resolution)

    assert (project / ".nodus" / "modules" / "utils" / "strings.nd").is_file()
    assert installed["utils"].version == "1.2.3"
    assert installed["utils"].hash.startswith("sha256:")
    assert read_lockfile(config.lock_path)["utils"].version == "1.2.3"
