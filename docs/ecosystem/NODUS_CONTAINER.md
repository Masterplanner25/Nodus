# `nodus-container`

**Status:** spec + scaffold (#85). Not published.
**Tier:** 2 — infrastructure primitives, distributed on PyPI.
**Depends on:** `std:subprocess` (nodus-lang ≥ 5.0.0).

---

## Summary

Orchestrate container execution — Docker, Podman, or any CLI-compatible engine —
from a Nodus workflow, without dropping back to bash. Launch a container, stream
its output, capture its result.

It is an **adapter over `std:subprocess`**, not a container runtime. Nodus does
not talk to the Docker daemon socket, does not implement the OCI spec, and does
not manage images. It builds an argv, runs it, and shapes the result into the
record `subprocess.run` already returns.

---

## The capability question, settled

This was the first thing to decide, and the answer is **no new capability**.

The obvious instinct is that container execution deserves its own entry in
`ALL_CAPABILITIES`: `docker run -v /:/host` grants the container write access to
the entire host filesystem, and often root inside it, which is materially more
authority than an ordinary subprocess. An operator might reasonably want to say
*"you may shell out, but not run containers."*

**That capability would be unenforceable, and this project does not ship those.**
Anything holding `subprocess` can already reach a container engine:

```nodus
subprocess.run(["docker", "run", "-v", "/:/host", "alpine", "sh", "-c", "..."])
```

A `container` capability sitting beside `subprocess` would be bypassed by the
capability the program already holds — a control an operator believes they have
and does not. That is the pattern #473 and #478 were both filed for, and the same
reason `max_memory_mb` is refused at construction where it cannot be metered
(#160) rather than accepted and quietly ignored.

### What the enforceable boundary actually is

`allowed_commands`, which already exists and already works. Verified against
5.9.0:

| configuration | result |
|---|---|
| `allow_subprocess=True` | any binary runs |
| `allow_subprocess=True, allowed_commands=["docker"]` | `subprocess command not in allowed_commands: 'cmd'` |
| `allow_subprocess=True, allowed_commands=["cmd"]` | runs |
| `sp.shell(...)` with any `allowed_commands` | `subprocess shell mode is not permitted when allowed_commands is set` |

That last row is why the allowlist is a real boundary rather than a speed bump:
shell mode is refused outright when an allowlist is set, so `sh -c "docker …"`
cannot be used to step around it.

So an operator granting container execution writes:

```python
NodusRuntime(allow_subprocess=True, allowed_commands=["docker"])
```

and one withholding it simply leaves `docker` out of the list. **This library
declares `subprocess` and nothing else, because that is what it actually needs
and what actually gates it.**

### What is genuinely not bounded, and is not this library's to fix

`-v /:/host` still escapes `allowed_paths`, and `--privileged` still exists. That
is not a hole this adapter opens: `SECURITY_POSTURE.md §5` already records that
when subprocess is enabled *"the subprocess binary and its arguments are
unrestricted — only `stdout`/`stderr` redirect paths and `cwd` are validated
against `allowed_paths`."* A container adapter makes an existing gap **more
ergonomic**, which is worth saying out loud in the README rather than discovering.

Argument-level restriction (refusing `-v`, `--privileged`, `--network=host`) is a
**policy** question, not a capability one: `CapabilityPolicy.check` receives the
call's arguments and can already refuse on them. This library's job is to make
that inspectable — see *Argument shaping* below.

---

## Public Python API

```python
from nodus_container import ContainerSpec, ContainerResult, run, build_argv
```

| Function | Signature | Description |
|---|---|---|
| `build_argv` | `(spec: ContainerSpec) -> list[str]` | The argv this spec becomes. Pure; no execution |
| `run` | `(spec, *, runner) -> ContainerResult` | Execute through an injected runner |

`runner` is any callable taking `list[str]` and returning the record
`subprocess.run` produces. The library never imports a subprocess module itself —
that is what keeps it testable without a container engine present, and what lets
the Nodus side pass `std:subprocess.run` straight in.

---

## Public model contracts

### `ContainerSpec`

| Field | Type | Notes |
|---|---|---|
| `image` | `str` | Required |
| `command` | `list[str]` | Argv inside the container; empty means the image's entrypoint |
| `engine` | `str` | `"docker"` (default) or `"podman"` |
| `env` | `dict[str, str]` | Becomes `-e K=V`, sorted, so an argv is reproducible |
| `mounts` | `list[Mount]` | Host↔container bind mounts |
| `workdir` | `str \| None` | `-w` |
| `network` | `str \| None` | `--network` |
| `remove` | `bool` | `--rm`, default `True` |

### `Mount`

`source`, `target`, `read_only` (default `True`).

**Read-only by default is the one opinion this library holds.** A writable mount
is the mechanism behind the escape described above, so it is the thing a reader
should have to type.

### `ContainerResult`

`exit_code`, `stdout`, `stderr`, `ok`, `argv` — the same shape `subprocess.run`
returns, plus the argv that produced it. Nothing new to learn, and the argv is
kept so a refusal or a surprise can be read back.

---

## Argument shaping

`build_argv` is pure and separately testable, which is the point: a
`CapabilityPolicy` that wants to refuse `--privileged` or a writable root mount
can inspect the argv the call *would* make, rather than pattern-matching a shell
string. Splitting construction from execution is what makes that possible, and is
why `run` takes an injected runner rather than reaching for subprocess itself.

---

## Package dependencies

None. Pure standard library, like `nodus-retry` and `nodus-events` in Tier 1 —
the engine is invoked through the injected runner, so nothing is imported to
talk to it.

---

## Test plan

- `build_argv` for every field, including ordering (env sorted, `--rm` placement)
- read-only default, and that `read_only=False` produces `:rw`
- `podman` produces the same argv shape as `docker`
- `run` with a fake runner: success, non-zero exit, and the argv carried through
- refusal of an empty image, and of a mount with no target

No test requires a container engine. A live-engine test belongs in the package's
own CI, marked and skipped when `docker` is absent.

---

## Verified against a real engine

The argv is not asserted, it is executed. Against **Docker 29.2.1**:

```
docker run --rm -e GREETING=hi python:3.11-slim python -c print("from inside the container")
-> exit 0, stdout: "from inside the container"
```

And the read-only default is enforced by the engine, not merely emitted:

| mount | container's write to the host path | host file |
|---|---|---|
| `Mount(source=…, target="/m")` (default) | **exit 1**, read-only filesystem | unchanged |
| `Mount(…, read_only=False)` | exit 0 | **overwritten** |

The second row is the escape this document warns about, demonstrated: a writable
bind mount reaches the host filesystem, outside `allowed_paths`. That is why the
default is the other way round, and why `allowed_commands` — not a mount flag — is
where an operator draws the line.

The package's own 17 tests need no engine; this was a separate, deliberate check,
because "the argv looks right" and "the argv runs" are different claims.

## Acceptance criteria

1. `build_argv` is pure and total over `ContainerSpec`.
2. `run` never imports a subprocess module.
3. The README states the `-v /:/host` gap and points at `allowed_commands`.
4. Published metadata declares no `nodus-lang` upper bound (policy, 2026-08-17).
5. A row in `docs/ecosystem/README.md` before publishing — a package with no row
   there is invisible to the count *and* to the drift sweep, which is how
   `nodus-a2a-wire` and `nodus-workflow-ai` went unnoticed.
