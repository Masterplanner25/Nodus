# Nodus Demos

Three demos that show why the Nodus stack is different. Two run today; the
third is a design document.

Every command below was run against nodus-lang 5.13.0 on 2026-09-16 and its
output pasted verbatim into the demo's own README.

---

## Prerequisites

```bash
pip install nodus-lang
```

Working from a checkout of this repo instead? Use the source tree, not
whatever is installed: `python nodus.py run ...` from the repo root, and
`PYTHONPATH=src python demos/embed_worker/worker.py`.

---

## Demo 1 — Live embed (5 min)

Runs a governed Nodus VM inside a Python worker. Swap code at runtime with no rebuilds.

```bash
cd demos/embed_worker
python worker.py                               # default: Fibonacci sequence
python worker.py '{"code": "print(42i)"}'      # inject custom code
python worker.py '{"code": "while (true) { let x = 1i }"}'  # hits max_steps limit
```

See `embed_worker/README.md` for the governance knobs and the sandbox probes
(network, subprocess, step budget).

---

## Demo 2 — Agent orchestration (design only)

Plan → approve → execute with human-in-the-loop governance.

See `agent_orchestration/DESIGN.md` for what the server already provides,
what is missing, and the implementation plan. Not runnable.

---

## Demo 3 — Package conversion (5 min)

Wraps a plain Python utility in a three-step Nodus workflow that adds pre/post
checks, structured error handling, and a recorded run.

```bash
cd demos/package_conversion

# BEFORE: bare Python
python transform.py sample_input.json output.json name email

# AFTER: Nodus-orchestrated
nodus run --time-limit 10 pipeline.nd
```

`--time-limit` matters: `nodus run` defaults to a 200 ms wall-clock budget
for the whole program, and spawning Python costs about that by itself.

Try the breakage case:

```bash
# Missing input -- step 1 fails, steps 2 and 3 are skipped, exit code 1
mv sample_input.json _hidden.json && nodus run --time-limit 10 pipeline.nd
mv _hidden.json sample_input.json
```

See `package_conversion/README.md` for the full before/after comparison, the
non-zero-exit case, and `nodus graph` / `nodus workflow runs`.

---

## Directory layout

```
demos/
  RUNME.md                         ← this file
  embed_worker/
    worker.py                      ← Python host with NodusRuntime
    README.md
  package_conversion/
    transform.py                   ← BEFORE: plain Python utility
    pipeline.nd                    ← AFTER: Nodus workflow wrapping it
    sample_input.json
    README.md
  agent_orchestration/
    DESIGN.md                      ← design doc; not runnable
```

Running Demo 3 creates `output.json` and a `.nodus/` run store in its
directory. Both are gitignored.
