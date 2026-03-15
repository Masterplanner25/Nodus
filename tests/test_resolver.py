from nodus.tooling.project import load_project
from nodus.tooling.registry import Registry
from nodus.tooling.resolver import resolve_project_dependencies


def test_resolver_builds_dependency_graph(tmp_path):
    helper = tmp_path / "workflow_utils"
    helper.mkdir()
    (helper / "nodus.toml").write_text(
        '[package]\nname = "workflow_utils"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (helper / "module.nd").write_text("export let ok = true\n", encoding="utf-8")

    registry_root = tmp_path / "registry"
    registry_dep = registry_root / "json-1.2.0"
    registry_dep.mkdir(parents=True)
    (registry_dep / "nodus.toml").write_text(
        '[package]\nname = "json"\nversion = "1.2.0"\n',
        encoding="utf-8",
    )
    (registry_dep / "module.nd").write_text("export let value = 1\n", encoding="utf-8")

    project = tmp_path / "app"
    (project / ".nodus").mkdir(parents=True)
    (project / "nodus.toml").write_text(
        "\n".join(
            [
                "[package]",
                'name = "app"',
                'version = "0.1.0"',
                "",
                "[dependencies]",
                'json = "1.2.0"',
                'workflow_utils = { path = "../workflow_utils" }',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (project / ".nodus" / "registry.toml").write_text(
        "\n".join(
            [
                '[packages.json."1.2.0"]',
                'path = "../../registry/json-1.2.0"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    resolution = resolve_project_dependencies(
        load_project(str(project)),
        update=True,
        registry=Registry.from_project_root(str(project)),
    )

    assert resolution.graph["json"] == ()
    assert resolution.graph["workflow_utils"] == ()
    assert resolution.packages["json"].source == "registry"
    assert resolution.packages["workflow_utils"].source == "path"
    assert resolution.packages["workflow_utils"].source_path == "../workflow_utils"


def test_resolver_detects_version_conflicts(tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "nodus.toml").write_text(
        "\n".join(
            [
                "[package]",
                'name = "shared"',
                'version = "0.1.0"',
                "",
                "[dependencies]",
                'json = "1.1.0"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (shared / "module.nd").write_text("export let ok = true\n", encoding="utf-8")

    registry_root = tmp_path / "registry"
    for version in ("1.1.0", "1.2.0"):
        dep = registry_root / f"json-{version}"
        dep.mkdir(parents=True)
        (dep / "nodus.toml").write_text(
            f'[package]\nname = "json"\nversion = "{version}"\n',
            encoding="utf-8",
        )
        (dep / "module.nd").write_text(f'export let version = "{version}"\n', encoding="utf-8")

    project = tmp_path / "app"
    (project / ".nodus").mkdir(parents=True)
    (project / "nodus.toml").write_text(
        "\n".join(
            [
                "[package]",
                'name = "app"',
                'version = "0.1.0"',
                "",
                "[dependencies]",
                'json = "1.2.0"',
                'shared = { path = "../shared" }',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (project / ".nodus" / "registry.toml").write_text(
        "\n".join(
            [
                '[packages.json."1.1.0"]',
                'path = "../../registry/json-1.1.0"',
                "",
                '[packages.json."1.2.0"]',
                'path = "../../registry/json-1.2.0"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    try:
        resolve_project_dependencies(
            load_project(str(project)),
            update=True,
            registry=Registry.from_project_root(str(project)),
        )
    except ValueError as err:
        assert "does not satisfy" in str(err)
    else:
        raise AssertionError("expected version conflict")
