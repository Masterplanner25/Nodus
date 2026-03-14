from nodus.tooling.project import LockedPackage, read_lockfile, write_lockfile


def test_lockfile_generation_is_deterministic(tmp_path):
    lock_path = tmp_path / "nodus.lock"
    packages = {
        "utils": LockedPackage(name="utils", version="1.2.3", source="path:../utils", hash="sha256:bbb"),
        "json": LockedPackage(name="json", version="1.2.0", source="registry", hash="sha256:aaa"),
    }

    write_lockfile(str(lock_path), packages)
    first = lock_path.read_text(encoding="utf-8")
    write_lockfile(str(lock_path), dict(reversed(list(packages.items()))))
    second = lock_path.read_text(encoding="utf-8")
    loaded = read_lockfile(str(lock_path))

    assert first == second
    assert first.startswith("[[package]]\nname = \"json\"")
    assert loaded["json"].source == "registry"
    assert loaded["utils"].hash == "sha256:bbb"
