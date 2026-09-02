# nodus-container

Container execution for Nodus workflows — launch a container, capture its result,
without dropping back to bash.

```python
from nodus_container import ContainerSpec, Mount, build_argv, run

spec = ContainerSpec(
    image="alpine:3",
    command=("echo", "hello"),
    mounts=(Mount(source="/data", target="/data"),),   # read-only by default
)
build_argv(spec)
# ['docker', 'run', '--rm', '-v', '/data:/data:ro', 'alpine:3', 'echo', 'hello']
```

`run(spec, runner=...)` executes it through a runner you supply — from Nodus,
that is `std:subprocess.run`. This package never imports a subprocess module.

## Security: read this before granting it

This is an adapter over `subprocess`, and it declares **no capability of its
own**. A `container` capability would be unenforceable: anything holding
`subprocess` can already run `docker` directly, so a control beside it would be
bypassed by the permission the caller already has.

**The enforceable boundary is `allowed_commands`:**

```python
NodusRuntime(allow_subprocess=True, allowed_commands=["docker"])
```

Withhold `docker` from that list and container execution is refused. Setting any
allowlist also refuses `subprocess.shell`, so `sh -c "docker …"` cannot step
around it.

**What is still not bounded:** `-v /:/host` escapes `allowed_paths`, and
`--privileged` exists. That is not a gap this package opens — `SECURITY_POSTURE.md
§5` already records that a permitted subprocess's binary and arguments are
unrestricted — but this package makes it a one-liner, which is worth knowing
before you grant it. Mounts are read-only by default for that reason.

To restrict *arguments*, use a `CapabilityPolicy`: it receives the call's
arguments, and `build_argv` is pure so the argv a call would make can be
inspected before it runs.

## Status

Spec-first scaffold (#85), not published. Design:
`docs/ecosystem/NODUS_CONTAINER.md`.
