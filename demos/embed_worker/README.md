# Demo 1 — Live embed: Nodus VM inside a governed worker

**What it proves:** Nodus is embeddable. A host Python process can load,
govern, and run arbitrary Nodus code at runtime with no rebuilds. The host
owns policy (timeout, sandbox, allowed paths); the script owns logic.

## Setup

```bash
pip install nodus-lang
cd demos/embed_worker
```

## Run the default program

```bash
python worker.py
```

Expected output:
```
First 10 Fibonacci numbers:
  fib(0) = 0
  fib(1) = 1
  fib(2) = 1
  ...
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

The worker executes whatever code arrives — governed by the limits set in
`TIMEOUT_MS`, `MAX_STEPS`, `ALLOWED_PATHS`, and `ALLOW_NETWORK`.

## What to observe

| Governance knob | Where set | What it does |
|---|---|---|
| `timeout_ms=5000` | `worker.py` | Kills execution after 5 s wall-clock |
| `max_steps=200_000` | `worker.py` | Caps VM instruction count |
| `allowed_paths=None` | `worker.py` | No filesystem restriction (demo); set to `["/data"]` to jail |
| `allow_network=False` | `worker.py` | Blocks all `http_*` builtins |

## Try breaking the sandbox

```bash
# HTTP is blocked — this should return an error
python worker.py '{"code": "let r = http_get(\"https://example.com\")\nprint(r)"}'

# Infinite loop — killed by max_steps
python worker.py '{"code": "while (true) { let x = 1i }"}'
```
