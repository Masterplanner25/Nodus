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
