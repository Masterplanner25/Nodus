"""
Demo 1 — Live embed: Nodus VM inside a governed worker.

What this proves
----------------
Nodus is embeddable. A host Python process can load, govern, and execute
arbitrary Nodus code at runtime with no rebuilds. The host owns policy
(timeouts, sandbox, allowed paths); the script owns logic.

Run
---
    pip install nodus-lang
    python worker.py                        # runs the default program
    python worker.py '{"code": "print(42)"}'  # runs custom code from JSON
"""

import json
import sys

from nodus.runtime.embedding import NodusRuntime

# ── governance knobs ──────────────────────────────────────────────────────────
TIMEOUT_MS    = 5_000       # wall-clock limit per execution
MAX_STEPS     = 200_000     # VM instruction budget
ALLOWED_PATHS = None        # None = no filesystem restriction in this demo
ALLOW_NETWORK = False       # no outbound HTTP from embedded scripts

# ── default program ───────────────────────────────────────────────────────────
DEFAULT_PROGRAM = r"""
fn fibonacci(n) {
  if (n <= 1i) { return n }
  return fibonacci(n - 1i) + fibonacci(n - 2i)
}

fn range_list(n) {
  let acc = []
  let i = 0i
  while (i < n) {
    acc = acc + [i]
    i = i + 1i
  }
  return acc
}

let indices = range_list(10i)
print("First 10 Fibonacci numbers:")
let i = 0i
while (i < 10i) {
  print("  fib(" + str(i) + ") = " + str(fibonacci(i)))
  i = i + 1i
}
"""


def handle(event: dict) -> dict:
    """Execute a Nodus program.  event["code"] overrides the default."""
    code = event.get("code", DEFAULT_PROGRAM)

    rt = NodusRuntime(
        timeout_ms=TIMEOUT_MS,
        max_steps=MAX_STEPS,
        allowed_paths=ALLOWED_PATHS,
        allow_network=ALLOW_NETWORK,
    )
    result = rt.run_source(code)

    return {
        "ok":     result["ok"],
        "stdout": result.get("stdout", ""),
        "error":  result.get("error"),
    }


if __name__ == "__main__":
    if len(sys.argv) > 1:
        event = json.loads(sys.argv[1])
    else:
        event = {}

    out = handle(event)

    if out["ok"]:
        print(out["stdout"], end="")
    else:
        err = out["error"] or {}
        print(f"[error] {err.get('type', 'error')}: {err.get('message', out['error'])}")
        sys.exit(1)
