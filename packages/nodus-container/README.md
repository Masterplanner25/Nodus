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
`--privileged` exists. That is not a gap this package opens —
[SECURITY_POSTURE.md §5](https://github.com/Masterplanner25/Nodus/blob/main/docs/governance/SECURITY_POSTURE.md)
already records that a permitted subprocess's binary and arguments are
unrestricted — but this package makes it a one-liner, which is worth knowing
before you grant it. Mounts are read-only by default for that reason.

To restrict *arguments*, use a `CapabilityPolicy`: it receives the call's
arguments, and `build_argv` is pure so the argv a call would make can be
inspected before it runs.

### Under `nodus serve`, check which nodus-lang you are on

The server's treatment of submitted code changed in
[#754](https://github.com/Masterplanner25/Nodus/issues/754), and the two
behaviours are opposites:

- **Through nodus-lang 5.9.0**, code sent to `POST /execute` ran with subprocess,
  network and environment access permitted, and **no flag could restrict it**. If
  you are on one of those releases, anything that can reach the port can run
  `docker` — put the server behind something that authenticates, and treat this
  package's presence as incidental to that.
- **After #754 ships**, submitted code is denied those by default and the
  operator grants them:

  ```bash
  nodus serve --auth-token "$TOKEN" --allow-subprocess --allowed-commands docker
  ```

The allowlist is the part worth typing. `--allow-subprocess` alone permits every
executable on the host.

## Status

Published from the [nodus-lang repository](https://github.com/Masterplanner25/Nodus/tree/main/packages/nodus-container),
where it is developed alongside the runtime rather than in a repository of its own.

Design and the capability argument in full:
[NODUS_CONTAINER.md](https://github.com/Masterplanner25/Nodus/blob/main/docs/ecosystem/NODUS_CONTAINER.md).
Issue: [#85](https://github.com/Masterplanner25/Nodus/issues/85).
