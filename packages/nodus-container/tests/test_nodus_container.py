"""`nodus-container` scaffold tests (#85).

No test requires a container engine, which is the point of splitting `build_argv`
from `run`: the argv is a pure function of the spec, and execution is somebody
else's callable. A live-engine test belongs in this package's own CI, marked and
skipped when `docker` is absent.
"""

import pytest

from nodus_container import (
    ContainerResult,
    ContainerSpec,
    ContainerSpecError,
    Mount,
    build_argv,
    run,
)


class TestBuildArgv:
    def test_the_minimal_spec(self):
        assert build_argv(ContainerSpec(image="alpine:3")) == [
            "docker", "run", "--rm", "alpine:3",
        ]

    def test_the_command_goes_after_the_image(self):
        """Argv order is not cosmetic: anything after the image is the
        container's argv, and anything before it is the engine's."""
        argv = build_argv(ContainerSpec(image="alpine:3", command=("echo", "hi")))
        assert argv[argv.index("alpine:3") + 1:] == ["echo", "hi"]

    def test_environment_is_sorted(self):
        """Deterministic, so an argv can be compared in a test, diffed in a trace,
        and matched by a policy. Insertion order would make all three unreliable."""
        argv = build_argv(
            ContainerSpec(image="i", env={"B": "2", "A": "1", "C": "3"})
        )
        assert argv[argv.index("-e"):][:6] == ["-e", "A=1", "-e", "B=2", "-e", "C=3"]

    def test_mounts_are_read_only_unless_asked(self):
        """The one opinion this package holds -- a writable bind mount is the
        mechanism behind `-v /:/host`, so it has to be typed."""
        spec = ContainerSpec(image="i", mounts=(Mount(source="/a", target="/b"),))
        assert "-v" in build_argv(spec)
        assert "/a:/b:ro" in build_argv(spec)

        writable = ContainerSpec(
            image="i", mounts=(Mount(source="/a", target="/b", read_only=False),)
        )
        assert "/a:/b:rw" in build_argv(writable)

    def test_optional_flags_appear_only_when_set(self):
        bare = build_argv(ContainerSpec(image="i"))
        assert "-w" not in bare and "--network" not in bare

        full = build_argv(ContainerSpec(image="i", workdir="/src", network="none"))
        assert full[full.index("-w") + 1] == "/src"
        assert full[full.index("--network") + 1] == "none"

    def test_remove_can_be_turned_off(self):
        assert "--rm" not in build_argv(ContainerSpec(image="i", remove=False))

    def test_podman_takes_the_same_shape(self):
        assert build_argv(ContainerSpec(image="i", engine="podman"))[0] == "podman"

    @pytest.mark.parametrize(
        "spec, fragment",
        [
            (ContainerSpec(image=""), "needs an image"),
            (ContainerSpec(image="   "), "needs an image"),
            (ContainerSpec(image="i", engine="containerd"), "unknown engine"),
            (
                ContainerSpec(image="i", mounts=(Mount(source="/a", target=""),)),
                "needs both a source and a target",
            ),
        ],
    )
    def test_a_bad_spec_is_refused_where_it_is_written(self, spec, fragment):
        with pytest.raises(ContainerSpecError) as caught:
            build_argv(spec)
        assert fragment in str(caught.value)


class TestRun:
    def test_it_uses_the_injected_runner(self):
        seen = {}

        def fake(argv):
            seen["argv"] = argv
            return {"exit_code": 0, "stdout": "hello\n", "stderr": ""}

        result = run(ContainerSpec(image="alpine:3", command=("echo", "hello")), runner=fake)
        assert isinstance(result, ContainerResult)
        assert result.ok and result.stdout == "hello\n"
        assert seen["argv"][0] == "docker"

    def test_the_argv_is_carried_on_the_result(self):
        """So a refusal or a surprise can be read back -- which matters most when
        the refusal came from a policy inspecting the argv."""
        result = run(ContainerSpec(image="i"), runner=lambda argv: {"exit_code": 0})
        assert result.argv == ("docker", "run", "--rm", "i")

    def test_a_non_zero_exit_is_reported_not_raised(self):
        """The same contract `subprocess.run` has: a failing command is a result,
        not an exception. A spec that cannot become an argv is the exception."""
        result = run(
            ContainerSpec(image="i"),
            runner=lambda argv: {"exit_code": 3, "stderr": "boom"},
        )
        assert not result.ok
        assert result.exit_code == 3 and result.stderr == "boom"

    def test_an_object_runner_works_as_well_as_a_mapping(self):
        """A Nodus record marshals to a mapping; a Python caller is likelier to
        return an object. Accepting only one would make the runner injectable in
        theory only."""

        class Reply:
            exit_code = 0
            stdout = "ok"
            stderr = ""

        assert run(ContainerSpec(image="i"), runner=lambda argv: Reply()).stdout == "ok"

    def test_a_bad_spec_never_reaches_the_runner(self):
        def explode(argv):  # pragma: no cover - must not be called
            raise AssertionError("the runner was called with an invalid spec")

        with pytest.raises(ContainerSpecError):
            run(ContainerSpec(image=""), runner=explode)


class TestItDeclaresNoExecutionDependency:
    def test_nothing_imports_a_subprocess_module(self):
        """The reason this package declares no capability of its own: it cannot
        execute anything. If that stops being true, the security argument in
        `docs/ecosystem/NODUS_CONTAINER.md` stops being true with it."""
        from pathlib import Path

        package = Path(__file__).resolve().parents[1] / "src" / "nodus_container"
        for module in sorted(package.glob("*.py")):
            source = module.read_text(encoding="utf-8")
            for banned in ("import subprocess", "from subprocess", "os.system", "os.popen"):
                assert banned not in source, f"{module.name} reaches for {banned}"
