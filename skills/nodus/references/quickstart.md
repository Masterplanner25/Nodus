# Nodus Quickstart

Read this before drafting or editing `.nd` code.

## Mental model

Nodus is a workflow and orchestration language. Prefer workflows, step results, durable state, coroutines, and channels over Python-style application structure.

## Rules that matter most

- `{"key": val}` is a map. Use `m["key"]`.
- `{key: val}` is a record. Use `r.key`.
- `json.parse()` returns a map.
- Bare numeric literals are floats. Use `42i` for ints.
- `+=`, `-=`, `*=`, `/=` work (v4.0.1+). `**` does not — use `math.pow()`.
- `print()` takes one argument only.
- Imports must be top-level.
- Expressions do not continue across newlines.
- Shared mutable closure state must live in a map.
- Channels are built in: `channel()`, `send()`, `recv()`, `close()`. Do not import `std:channel`.
- `spawn()` requires a coroutine value. Create it first, then `spawn(c)`, then `run_loop()`.
- Workflow results are maps. Use bracket access.
- `checkpoint` is valid only inside step bodies.

## Minimal patterns

```nd
let state = {"count": 0i}
let inc = fn() {
    state["count"] = state["count"] + 1i
}
inc()
print("count: \(state["count"])")
```

```nd
workflow sample {
    state processed = 0i

    step ingest {
        return ["a", "b"]
    }

    step count after ingest {
        for item in ingest {
            processed = processed + 1i
        }
        checkpoint "after_count"
        return processed
    }
}

let r = run_workflow(sample)
print(r["steps"]["count"])
print(r["state"]["processed"])
```

## Verification

```bash
nodus check script.nd
nodus run script.nd
nodus run --time-limit 5000 script.nd
```
