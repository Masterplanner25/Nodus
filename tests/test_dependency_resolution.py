from nodus.tooling.project import load_project
from nodus.tooling.registry import Registry
from nodus.tooling.resolver import resolve_project_dependencies


def test_dependency_graph_resolution_with_path_and_registry_sources(tmp_path):
    utils = tmp_path / "utils"
    utils.mkdir()
    (utils / "nodus.toml").write_text('name = "utils"\nversion = "1.2.3"\n', encoding="utf-8")
    (utils / "util.nd").write_text("export let value = 1\n", encoding="utf-8")

    registry_root = tmp_path / "registry"
    json_v1 = registry_root / "json-1.1.0"
    json_v2 = registry_root / "json-1.2.0"
    json_v1.mkdir(parents=True)
    json_v2.mkdir(parents=True)
    (json_v1 / "nodus.toml").write_text('name = "json"\nversion = "1.1.0"\n', encoding="utf-8")
    (json_v2 / "nodus.toml").write_text('name = "json"\nversion = "1.2.0"\n', encoding="utf-8")
    (json_v1 / "json.nd").write_text('export let version = "1.1.0"\n', encoding="utf-8")
    (json_v2 / "json.nd").write_text('export let version = "1.2.0"\n', encoding="utf-8")

    project = tmp_path / "app"
    project.mkdir()
    (project / ".nodus").mkdir()
    (project / "nodus.toml").write_text(
        '\n'.join(
            [
                'name = "app"',
                'version = "0.1.0"',
                "",
                "[dependencies]",
                'json = "^1.1.0"',
                'utils = { path = "../utils" }',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (project / ".nodus" / "registry.toml").write_text(
        '\n'.join(
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

    config = load_project(str(project))
    resolution = resolve_project_dependencies(config, update=True, registry=Registry.from_project_root(config.root))

    assert resolution.packages["utils"].version == "1.2.3"
    assert resolution.packages["json"].version == "1.2.0"
    assert resolution.graph["utils"] == ()
    assert resolution.graph["json"] == ()
    assert set(resolution.install_order) == {"json", "utils"}
