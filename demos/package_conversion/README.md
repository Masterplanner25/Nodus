# Demo 3 — Package conversion: Python utility → Nodus-orchestrated job

**What it proves:** You can wrap an existing Python utility in a Nodus
pipeline to get pre/post condition checks, structured error handling, and
observable execution — without rewriting the core logic.

## Setup

```bash
pip install nodus-lang
cd demos/package_conversion
```

## The before: plain Python

`transform.py` filters a JSON array to keep only `name` and `email` fields.
It works — but fails silently on bad input, has no pre/post checks, and
produces no observable output beyond its own `print`.

```bash
python transform.py sample_input.json output.json name email
# 4 records written to output.json
```

## The after: Nodus-orchestrated pipeline

`pipeline.nd` wraps the same Python script:

```bash
nodus run pipeline.nd
```

Expected output:
```
=== pipeline start ===
[1/3] checking input...
[2/3] running transform...
4 records written to output.json
[3/3] verifying output...
=== pipeline done ===
```

## What to observe

**Pre-condition check:** delete `sample_input.json` and run again — the
pipeline catches the missing input at step 1 with a clear message instead of
crashing inside Python.

**Structured exit-code handling:** replace `transform.py` with a version that
exits non-zero — the pipeline captures and logs the exit code and stderr
without a Python traceback escaping to the user.

**Sandbox:** the pipeline runs inside a `NodusRuntime` with `allowed_paths`
set to the working directory. A script cannot write outside it, regardless of
what `transform.py` does.

## The difference at a glance

| | `python transform.py ...` | `nodus run pipeline.nd` |
|---|---|---|
| Missing input | `FileNotFoundError` traceback | Clear error at step 1 |
| Non-zero exit | Silent or traceback | Logged with exit code + stderr |
| Output verification | None | Step 3 confirms file exists |
| Observability | `print` only | Runtime event bus (all steps) |
| Filesystem scope | Unrestricted | Governed by `allowed_paths` |

## Extend it

Add retry on failure:

```nd
let attempts = 0i
let ok = false
while (attempts < 3i) {
  let result = subprocess_run(["python", "transform.py", in_path, out_path, "name", "email"])
  if (result.exit_code == 0i) {
    ok = true
    attempts = 3i  // break
  }
  attempts = attempts + 1i
}
```
