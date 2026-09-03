"""Value types for a container invocation (#85).

Pure data. Nothing here reaches an engine, imports a subprocess module, or knows
what a Nodus runtime is -- which is what lets `build_argv` be tested without
Docker installed, and lets a `CapabilityPolicy` inspect the argv a call *would*
make rather than pattern-matching a shell string.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Engines whose CLI takes the argv shape this builds. Named once; `build_argv`
#: validates against it rather than accepting any string, so a typo is refused
#: where it is written instead of surfacing as "docker: command not found".
SUPPORTED_ENGINES = frozenset({"docker", "podman"})


@dataclass(frozen=True)
class Mount:
    """A host path made visible inside the container.

    `read_only` defaults to **True**, and that default is the one opinion this
    package holds. A writable bind mount is the mechanism behind
    `docker run -v /:/host` -- the escape from `allowed_paths` that
    `SECURITY_POSTURE.md §5` describes -- so it is the thing a reader should have
    to type rather than the thing they get by forgetting.
    """

    source: str
    target: str
    read_only: bool = True

    def as_argument(self) -> str:
        suffix = "ro" if self.read_only else "rw"
        return f"{self.source}:{self.target}:{suffix}"


@dataclass(frozen=True)
class ContainerSpec:
    """What to run, as data."""

    image: str
    command: tuple[str, ...] = ()
    engine: str = "docker"
    env: dict[str, str] = field(default_factory=dict)
    mounts: tuple[Mount, ...] = ()
    workdir: str | None = None
    network: str | None = None
    remove: bool = True


@dataclass(frozen=True)
class ContainerResult:
    """The same shape `subprocess.run` returns, plus the argv that produced it.

    Nothing new to learn for a reader who has used `std:subprocess`, and keeping
    the argv means a refusal or a surprise can be read back afterwards -- which
    matters most when the refusal came from a capability policy inspecting it.
    """

    exit_code: int
    stdout: str = ""
    stderr: str = ""
    argv: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.exit_code == 0
