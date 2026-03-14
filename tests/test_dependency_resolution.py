from nodus.runtime.project import install_dependencies, load_project, read_lockfile


def test_path_dependency_install(tmp_path):
    dep = tmp_path / "utils"
    dep.mkdir()
    (dep / "nodus.toml").write_text('name = "utils"\nversion = "1.2.3"\n', encoding="utf-8")
    (dep / "util.nd").write_text("export let value = 1\n", encoding="utf-8")

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
    resolved = install_dependencies(config, update=True)
    assert "utils" in resolved
    lock = read_lockfile(config.lock_path)
    assert lock["utils"].version == "1.2.3"
