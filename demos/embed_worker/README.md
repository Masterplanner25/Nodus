# Demo 1 — Live embed: Nodus VM inside a governed worker

**What it proves:** Nodus is embeddable. A host Python process can load,
govern, and run arbitrary Nodus code at runtime with no rebuilds. The host
owns policy (timeout, step budget, filesystem, network, subprocess, env); the
script owns logic.

## Setup

```bash
pip install nodus-lang
cd demos/embed_worker
```

## Run the default program

```bash
python worker.py
```

Output:
```
First 10 Fibonacci numbers:
  fib(0) = 0
  fib(1) = 1
  fib(2) = 1
  fib(3) = 2
  fib(4) = 3
  fib(5) = 5
  fib(6) = 8
  fib(7) = 13
  fib(8) = 21
  fib(9) = 34
```

## Inject code at runtime (the wow moment)

Swap `event["code"]` without touching the worker:

```bash
python worker.py '{"code": "print(\"hello from injected code!\")"}'
```

Or run a multi-line program inline:

```bash
python worker.py '{"code": "let x = 6i * 7i\nprint(\"The answer is \" + str(x))"}'
```

The worker executes whatever code arrives — governed by the limits set at the
top of `worker.py`.

## What to observe

| Governance knob | Where set | What it does |
|---|---|---|
| `timeout_ms=5000` | `worker.py` | Kills execution after 5 s wall-clock |
| `max_steps=200_000` | `worker.py` | Caps VM instruction count |
| `allowed_paths=None` | `worker.py` | No filesystem restriction (demo); set to `["/data"]` to jail. A bare `NodusRuntime()` jails to the CWD |
| `allow_network=False` | `worker.py` | Blocks all `http_*` builtins |
| `allow_subprocess` / `allow_env` | not set | **Also denied** — every capability flag defaults to `False` since 5.0.0. The worker names only the one the demo exercises |

## Try breaking the sandbox

Each of these exits 1 with a `sandbox` error naming the flag that would grant
the capability:

```bash
# HTTP is blocked
python worker.py '{"code": "let r = http_get(\"https://example.com\")\nprint(r)"}'
# [error] sandbox: Blocked: network access is not granted; pass allow_network=True to NodusRuntime to allow it

# So is spawning a process, without the worker saying anything about it
python worker.py '{"code": "let r = subprocess_run([\"python\", \"-c\", \"print(1)\"])\nprint(r)"}'
# [error] sandbox: Blocked: subprocess execution is not granted; pass allow_subprocess=True to NodusRuntime to allow it

# Infinite loop — killed by max_steps
python worker.py '{"code": "while (true) { let x = 1i }"}'
# [error] sandbox: Execution step limit exceeded
```

The denial contract an embedder can rely on is `error["kind"] == "sandbox"`
and the flag name in the message — not the sentence, which has changed
between releases.
