"""Turning a `ContainerSpec` into an argv, and running it through someone else's runner (#85).

**`build_argv` is pure and `run` takes an injected runner**, and the split is the
design rather than a convenience. Three things follow from it:

- The argv can be tested without a container engine present.
- A `CapabilityPolicy` can inspect the argv a call *would* make -- refusing
  `--privileged`, or a writable mount of `/` -- instead of pattern-matching a
  shell string. Argument-level restriction is a policy question, not a capability
  one, and this is what makes it answerable.
- Nothing here imports a subprocess module, so the package declares no capability
  of its own. The Nodus side passes `std:subprocess.run` in, and **that** call is
  what `allow_subprocess` and `allowed_commands` gate.

On why there is no `container` capability: one would be unenforceable. Anything
holding `subprocess` can already run `docker` directly, so a capability beside it
would be bypassed by the capability the caller already has -- a control an
operator believes they have and does not. `docs/ecosystem/NODUS_CONTAINER.md`
carries the full argument and the measurements behind it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from .models import SUPPORTED_ENGINES, ContainerResult, ContainerSpec


class ContainerSpecError(ValueError):
    """A spec that cannot become an argv. Raised where it is written."""


def build_argv(spec: ContainerSpec) -> list[str]:
    """The argv *spec* becomes. Pure -- nothing is executed.

    Deterministic, including environment ordering: an argv that varies run to run
    cannot be compared in a test, diffed in a trace, or matched by a policy.
    """
    if spec.engine not in SUPPORTED_ENGINES:
        raise ContainerSpecError(
            f"unknown engine {spec.engine!r}; expected one of "
            f"{', '.join(sorted(SUPPORTED_ENGINES))}"
        )
    if not spec.image or not spec.image.strip():
        raise ContainerSpecError("a container spec needs an image")

    argv: list[str] = [spec.engine, "run"]
    if spec.remove:
        argv.append("--rm")
    for key in sorted(spec.env):
        argv += ["-e", f"{key}={spec.env[key]}"]
    for mount in spec.mounts:
        if not mount.source or not mount.target:
            raise ContainerSpecError(
                f"a mount needs both a source and a target, got "
                f"{mount.source!r} -> {mount.target!r}"
            )
        argv += ["-v", mount.as_argument()]
    if spec.workdir:
        argv += ["-w", spec.workdir]
    if spec.network:
        argv += ["--network", spec.network]
    argv.append(spec.image)
    argv.extend(spec.command)
    return argv


def run(spec: ContainerSpec, *, runner: Callable[[list[str]], object]) -> ContainerResult:
    """Build the argv and hand it to *runner*.

    `runner` is anything taking `list[str]` and returning a mapping or object with
    `exit_code` / `stdout` / `stderr` -- which is exactly what
    `std:subprocess.run` gives back. Injected rather than imported so this package
    stays free of an execution dependency, and so a test can supply a fake.
    """
    argv = build_argv(spec)
    raw = runner(argv)
    return ContainerResult(
        exit_code=int(_field(raw, "exit_code", 0)),
        stdout=str(_field(raw, "stdout", "")),
        stderr=str(_field(raw, "stderr", "")),
        argv=tuple(argv),
    )


def _field(raw: object, name: str, default: object) -> object:
    """Read *name* off a mapping or an object.

    Both shapes are accepted because both are what callers have: a Nodus record
    marshals to a mapping, and a Python caller is likelier to hand over an object.
    Refusing one of them would make the runner injectable in theory only.
    """
    if isinstance(raw, Mapping):
        return raw.get(name, default)
    return getattr(raw, name, default)
