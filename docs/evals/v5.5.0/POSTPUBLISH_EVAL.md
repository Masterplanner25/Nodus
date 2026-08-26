# v5.5.0 — Post-publish evaluation (Stage 5)

Against the **published** package, installed from PyPI into a fresh venv. The question
this stage asks is not "did the gates pass" — Gate 10 already answered that against the
wheel — but "does this work the way a new user would expect".

```
install   pip install nodus-lang==5.5.0
resolved  .../stage5/v5/Lib/site-packages/nodus
version   5.5.0
page      https://pypi.org/project/nodus-lang/5.5.0/
```

---

## The index lagged the upload, and that is worth knowing

`pip install nodus-lang==5.5.0` failed twice with `No matching distribution found`,
listing every version up to 5.4.0 — while `https://pypi.org/pypi/nodus-lang/json` already
reported `5.5.0` as latest with both artifacts present and unyanked.

It was neither a failed upload nor propagation: **pip's local index cache**.
`--no-cache-dir` installed it immediately. Worth recording because the symptom reads
exactly like a botched publish, and the reflex — re-upload — is impossible against an
immutable release.

---

## What a new user does first

The thing this release is about, run from an install with no repo anywhere near it:

```
$ python -m nodus docs
Nodus 5.5.0 — documentation and agent material

  llms.txt
    machine-readable project index — start here if you are an agent
    [local] .../site-packages/nodus/llms.txt

  llms-full.txt
    full content summaries for indexers
    [web] https://github.com/Masterplanner25/Nodus/blob/v5.5.0/llms-full.txt
```

The bundled index resolves out of `site-packages` (9,551 bytes, names 5.5.0), and every
web link is pinned to `/blob/v5.5.0/` rather than `main`. Before this release the same
user had nothing: no shipped index, no command that mentioned documentation, and a PyPI
page whose relative links the renderer had silently dropped.

`--version` reports `Nodus 5.5.0`; `--help` lists 45 command lines including `docs`.

---

## A real program, using the 5.x surface

```nodus
workflow build {
    state total = 0i with { merge: "sum" }
    step lint { total += 1i return "linted" }
    step test after lint { total += 2i return "tested" }
    step ship after test with { allow_failure: true } { throw "flaky deploy" }
}
let r = run_workflow(build)
```

```
steps={"lint": "linted", "test": "tested"}
failed=[]  total=3
```

Three things at once, all behaving: a folded `state` cell summing contributions from two
steps (`total=3`), `allow_failure` letting a throwing step leave the run's verdict clean
(`failed=[]`), and the failed step correctly absent from `steps`.

`nodus check` returns `hello.nd: OK`.

`nodus fmt --check` reported the file **not** formatted — which is correct, not a defect:
the one-line step bodies are mine. Running `fmt` expanded them to multi-line blocks, and
the reformatted file produces byte-identical output. Checked rather than assumed, because
"the formatter disagrees with the docs' own examples" would be a real finding.

---

## The guarantee this release tightened

```
$ python -m nodus run bypass.nd
Runtime error at bypass.nd:2:27: Workflow step 'w.b' cannot be called directly — a step
body runs only as part of its workflow, in dependency order. Use run_workflow() (or
run_goal()) to execute the flow.
```

Named by flow and step, and it says what to do instead. This is the one behaviour in
5.5.0 that can turn previously-"working" code into an error, so its message carrying the
remedy matters more than usual.

---

## Verdict

**Good.** The release does what it says from a clean install, and the feature it is
principally about — an agent being able to find the material written for it — works from
inside a venv with no repo present, which is precisely the situation it was reported from.

### Open, not filed

`nodus fmt --check` exits non-zero for a file a user just wrote by hand, which is correct
behaviour and also the first thing a newcomer will hit if they follow the guide's examples
verbatim and then run the format gate. Not a defect; possibly a documentation nicety
(mention `nodus fmt` before `fmt --check`). Recorded here rather than filed, because
either choice is defensible.

### Carried forward

`nodus-run-action` still pins 5.4.0 in its README. `nodus_gate --consumers` flags it, and
it is Stage 6's work — see `STAGE6_DOWNSTREAM_SWEEP.md`.
