# Nodus Examples

Use these as starting points, then validate with `nodus check`.

## Hello world

```nd
print("Hello, Nodus!")
let name = "world"
print("Hello, \(name)!")
```

## Record vs map

```nd
let user = {name: "Alice", age: 30i}
let cfg = {"host": "localhost", "port": 8080i}

print(user.name)
print(cfg["host"])
```

## Safe closure mutation

```nd
let state = {"count": 0i}

let increment = fn() {
    state["count"] = state["count"] + 1i
}

increment()
increment()
print(state["count"])
```

## Workflow

```nd
workflow text_pipeline {
    state word_count = 0i

    step parse {
        return ["hello", "world", "nodus"]
    }

    step count after parse {
        for word in parse {
            word_count = word_count + 1i
        }
        return word_count
    }
}

let r = run_workflow(text_pipeline)
print(r["steps"]["count"])
print(r["state"]["word_count"])
```

## Coroutines and channels

```nd
let ch = channel()
let log = []

let producer = coroutine(fn() {
    send(ch, "task-1")
    send(ch, "task-2")
    close(ch)
})

let consumer = coroutine(fn() {
    let item = recv(ch)
    while (item != nil) {
        list_push(log, item)
        item = recv(ch)
    }
})

spawn(producer)
spawn(consumer)
run_loop()
print(log)
```

## JSON map access

```nd
import "std:json" as json

let raw = "{\"name\": \"Alice\"}"
let data = json.parse(raw)
print(data["name"])
```
