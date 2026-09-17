# Demo 3 — Package conversion: Python utility → Nodus-orchestrated job

**What it proves:** You can wrap an existing Python utility in a Nodus
workflow to get declared steps, pre/post condition checks, structured error
handling, and a recorded run — without rewriting the core logic.

## Setup

```bash
pip install nodus-lang
cd demos/package_conversion
```

## The before: plain Python

`transform.py` filters a JSON array to keep only `name` and `email` fields.
It works — but a bad input is a traceback, there are no pre/post checks, and
nothing records that it ran.

```bash
python transform.py sample_input.json output.json name email
# 4 records written to output.json
```

## The after: Nodus-orchestrated pipeline

`pipeline.nd` wraps the same Python script in a three-step `workflow`:

```bash
nodus run --time-limit 10 pipeline.nd
```

Output:

```
=== pipeline start ===
[1/3] checking input...
[2/3] running transform...
4 records written to output.json
[3/3] verifying output...
=== pipeline done ===
```

`--time-limit` is not optional. `nodus run` bounds the whole program at
**200 ms of wall clock** by default, and spawning a Python interpreter costs
about that on its own — the pipeline is one extra loop away from
`Execution timed out` without the flag.

## What to observe

**Pre-condition check** — hide the input and run again:

```bash
mv sample_input.json _hidden.json && nodus run --time-limit 10 pipeline.nd
mv _hidden.json sample_input.json
```

```
=== pipeline start ===
[1/3] checking input...
=== pipeline FAILED at step 'check_input': input file not found: sample_input.json ===
```

Exit code is 1. Steps 2 and 3 never ran, because `after` makes them depend
on step 1 — so step 3 cannot "verify" an `output.json` left over from an
earlier run. (The runtime also reports the failing step on stderr with a
Nodus stack trace; the lines above are stdout.)

**Structured exit-code handling** — corrupt the input so `transform.py`
itself fails:

```bash
cp sample_input.json _good.json && echo '{not json' > sample_input.json
nodus run --time-limit 10 pipeline.nd
mv _good.json sample_input.json
```

```
=== pipeline start ===
[1/3] checking input...
[2/3] running transform...
=== pipeline FAILED at step 'transform': transform exited 1: json.decoder.JSONDecodeError: Expecting property name enclosed in double quotes: line 1 column 2 (char 1) ===
```

The step captured the exit code and stderr, and reported the one line that
matters instead of letting a Python traceback escape.

**Inspect without running** — `nodus graph` shows the step DAG the workflow
declares, and does not execute the file:

```bash
nodus graph pipeline.nd
```

```json
{"workflow": "convert", "graph_id": "g_f5053c72", "nodes": ["check_input", "transform", "verify"], "edges": [["check_input", "transform"], ["transform", "verify"]], ...}
```

**Every run is recorded** — the runtime keeps each run's status and last
error under `.nodus/` in the working directory:

```bash
nodus workflow runs
```

Each entry carries `workflow_name`, `status` (`completed` / `failed`), and
`last_error` — `"input file not found: sample_input.json"` for the run above.

From the second run onward, `nodus run` prints a one-line warning on stderr
that the default JSON-file store becomes SQLite at 6.0.0. That is the
runtime's staged-change notice, not the demo misbehaving;
`NODUS_WORKFLOW_STORE_BACKEND=local` silences it.

**Filesystem scope** — a script under `nodus run` cannot write outside the
project root. Add `fs.write("../escape.txt", "x")` to a step and it is refused
with `path '../escape.txt' escapes the project root`; `--allow-paths` widens
the jail.

## The difference at a glance

| | `python transform.py ...` | `nodus run pipeline.nd` |
|---|---|---|
| Missing input | `FileNotFoundError` traceback | Clear error at step 1, later steps skipped, exit 1 |
| Non-zero exit | Traceback | Captured; last stderr line reported, exit 1 |
| Output verification | None | Step 3 confirms the file exists |
| Observability | `print` only | `nodus graph` (the DAG), `nodus workflow runs` (every run, its status, its error) |
| Filesystem scope | Unrestricted | Writes jailed to the project root |

## Extend it

Retry the transform step on failure with `with { retries: N }` — the runtime
re-runs the step body up to N more times before the run fails:

```nd
step transform after check_input with { retries: 2, retry_delay_ms: 100 } {
    ...
}
```

Details, including how state persists across attempts, are in
`docs/guide/workflows-and-tasks.md` §5.
