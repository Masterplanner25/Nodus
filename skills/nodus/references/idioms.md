# Nodus Idioms

Use these contrast pairs when the user is thinking in Python.

## Counter updates

```python
count += 1
```

```nd
count = count + 1i
```

Nodus has no compound assignment operators.

## Shared mutable state

```python
count = 0
def inc():
    global count
    count += 1
```

```nd
let state = {"count": 0i}
let inc = fn() {
    state["count"] = state["count"] + 1i
}
```

Assigning to an outer `let` inside a closure creates a local shadow.

## Printing values

```python
print("x:", x, "y:", y)
```

```nd
print("x: \(x), y: \(y)")
```

`print()` takes one argument.

## Parsed JSON access

```python
data["name"]
```

```nd
data["name"]
```

Use bracket notation because `json.parse()` returns a map.

## Membership checks

```python
if "name" in config:
    ...
```

```nd
if (has_key(config, "name")) {
    ...
}
```

Use `has_key()` for maps.

## Async shape

```python
await work()
```

```nd
let c = coroutine(fn() {
    work()
})
spawn(c)
run_loop()
```

Nodus uses cooperative coroutines and an explicit event loop.

## Workflow result access

```python
result.steps["build"]
```

```nd
r["steps"]["build"]
```

Treat workflow results as maps all the way down.

## Workflow composition (conditional routing / loops)

```python
# graph framework: a conditional edge picks one node
g.add_conditional_edges("classify", route, {"a": "pipe_a", "b": "pipe_b"})
```

```nd
step dispatch after classify {
    // one sub-workflow runs; the others never do
    match kind {
        "a" => run_workflow(pipe_a),
        _ => run_workflow(pipe_b),
    }
}
```

A single workflow is a static, acyclic DAG (every declared step runs; no per-step
guard; no cyclic `after`). Express conditional routing and iteration by
*composition*: control flow (`match`/`while`) selecting nested `run_workflow` calls.
Executes fine and each sub-workflow checkpoints independently, but not durable
across whole-flow resume yet (#322).
