# Nodus Demos

Three demos that show why the Nodus stack is different.

---

## Prerequisites

```bash
pip install nodus-lang
```

---

## Demo 1 — Live embed (5 min)

Runs a governed Nodus VM inside a Python worker. Swap code at runtime with no rebuilds.

```bash
cd demos/embed_worker
python worker.py                              # default: Fibonacci sequence
python worker.py '{"code": "print(42)"}'     # inject custom code
python worker.py '{"code": "while (true) { let x = 1i }"}'  # hits max_steps limit
```

See `embed_worker/README.md` for the full breakdown.

---

## Demo 2 — Agent orchestration (coming soon)

Plan → approve → execute with human-in-the-loop governance.

See `agent_orchestration/DESIGN.md` for what's built, what's missing, and the
implementation plan (~3.5 days to fully runnable).

---

## Demo 3 — Package conversion (5 min)

Wraps a plain Python utility in a Nodus pipeline that adds pre/post checks,
structured error handling, and observability.

```bash
cd demos/package_conversion

# BEFORE: bare Python
python transform.py sample_input.json output.json name email

# AFTER: Nodus-orchestrated
nodus run pipeline.nd
```

Try the breakage cases:

```bash
# Missing input file
mv sample_input.json _hidden.json && nodus run pipeline.nd
mv _hidden.json sample_input.json
```

See `package_conversion/README.md` for the full before/after comparison.

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
    pipeline.nd                    ← AFTER: Nodus-orchestrated wrapper
    sample_input.json
    README.md
  agent_orchestration/
    DESIGN.md                      ← design doc; not runnable yet
```
