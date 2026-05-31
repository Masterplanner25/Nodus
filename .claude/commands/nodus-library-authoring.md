Build the "Build a Nodus companion library" guide and template (Milestone 5).
Goal: a third party could build nodus-a2a without reverse-engineering nodus-mcp.
The ecosystem is reproducible, not just maintainable by one person.

No prerequisites. Can run independently.

## What this delivers

1. A complete "Build a Nodus companion library" guide at `docs/guide/build-a-library.md`
2. A minimal template structure demonstrating both authoring patterns
3. Namespacing conventions documented with examples

## Guide outline

Create `docs/guide/build-a-library.md` with these sections:

### 1. When to build a companion library

Use a companion library when you want to:
- Expose Python services as tools callable from Nodus scripts
- Ship reusable `.nd` modules that other Nodus projects can import
- Provide a higher-level API over nodus-lang primitives

Don't build a companion library just to wrap a Python package — use
`register_function()` directly in your app instead.

### 2. Two authoring patterns

**Pattern A: Python-backed library**
The library is primarily Python. `.nd` files are thin wrappers that expose
Python functionality as Nodus-callable tools.

```
nodus-mylib/
  pyproject.toml
  nodus_mylib/
    __init__.py
    nd.py              # exports get_nd_root()
    nd/
      index.nd         # tool wrappers + host function calls
    handlers.py        # the actual Python implementation
```

**Pattern B: Mixed Python + .nd library**
The library has substantial `.nd` business logic that orchestrates Python services.
Python provides capabilities; Nodus provides the orchestration.

```
nodus-mylib/
  pyproject.toml
  nodus_mylib/
    __init__.py
    nd.py
    nd/
      index.nd         # public API
      internal.nd      # internal helpers
      workflows.nd     # workflow definitions
    runtime.py         # attach_to_runtime() and host functions
    services.py        # Python services
```

### 3. Minimal Pattern A walkthrough

Step-by-step: create a library from scratch.

1. `pyproject.toml` with entry-point declaration
2. `nd.py` with `get_nd_root()`
3. `nd/index.nd` calling host functions
4. `runtime.py` with `attach_to_runtime(rt)` that registers host functions
5. Test that `import "my-library"` resolves
6. Test that tools are callable from Nodus scripts

### 4. Namespacing conventions

- Tool names: `"mylib.operation"` — always dotted, library prefix first
- Host function names: `"_mylib_internal"` — underscore prefix, library prefix
- Module subpath: `import "mylib:submodule"` → `submodule.nd`
- Avoid `std:` prefix — that is reserved for nodus-lang stdlib

### 5. Compatibility requirements

The library must declare its nodus-lang dependency:
```toml
[project]
dependencies = ["nodus-lang>=4.0.0"]
```

Only depend on APIs listed in `docs/governance/COMPANION_LIBRARY_CONTRACT.md`.
Do NOT import from `nodus.vm`, `nodus.runtime.scheduler`, or `nodus.tooling.*`.

### 6. Testing your library

Three test layers:
1. **Unit tests:** Python handler logic in isolation (no NodusRuntime needed)
2. **Integration tests:** `NodusRuntime` + your library + a Nodus script
3. **Entry-point test:** Verify `_resolve_installed_package("your-library")` returns
   a valid path after `pip install -e . --no-deps`

See `library-entry-points.md §"Testing the entry point locally"` for the entry-point test.

### 7. Release checklist

```markdown
- [ ] pyproject.toml declares [project.entry-points."nodus.nd"]
- [ ] get_nd_root() returns an absolute path that exists
- [ ] index.nd exports the public API
- [ ] Tool names use dotted namespacing (no collision with std:)
- [ ] Only COMPANION_LIBRARY_CONTRACT.md APIs are used
- [ ] Unit + integration + entry-point tests all pass
- [ ] README shows: install, attach_to_runtime, import, use
- [ ] pyproject.toml dependencies include nodus-lang>=4.x.0
```

## Minimal template

In `docs/guide/build-a-library.md` include a copyable minimal template:

```python
# nodus_mylib/nd.py
import os

def get_nd_root() -> str:
    return os.path.join(os.path.dirname(__file__), "nd")
```

```python
# nodus_mylib/runtime.py
def attach_to_runtime(rt):
    rt.register_function("_mylib_echo", lambda msg: msg, arity=1)
    rt.tool_registry.register({
        "name": "mylib.echo",
        "handler": lambda msg: {"echoed": msg},
        "description": "Echo a message back",
        "schema": {"type": "object", "properties": {"msg": {"type": "string"}}, "required": ["msg"]},
    })
```

```nd
// nodus_mylib/nd/index.nd
fn echo(msg) {
    return _mylib_echo(msg)
}
```

```python
# tests/test_integration.py
from nodus import NodusRuntime
from nodus_mylib.runtime import attach_to_runtime

def test_import_and_use():
    rt = NodusRuntime(timeout_ms=5000)
    attach_to_runtime(rt)
    r = rt.run_source('import "mylib"\nprint(mylib.echo("hello"))')
    assert r["ok"]
    assert "hello" in r["stdout"]
```

## nodus-mcp as a reference implementation

After this guide is written, verify that:
- nodus-mcp can be used as a worked example of Pattern A
- nodus-extension can be used as a worked example of Pattern B
- Both are referenced from the guide as "see this repo for a complete example"

## Exit criteria

- `docs/guide/build-a-library.md` exists and covers both patterns end-to-end
- Minimal template is copyable and works
- Namespacing conventions documented
- A third party reading only this guide + COMPANION_LIBRARY_CONTRACT.md could build
  a working companion library without reading nodus-mcp source code

## Dev environment

No special setup — this is primarily a documentation task.
Validate the template example:
```powershell
cd "C:\dev\Coding Language"
PYTHONPATH="C:/dev/Coding Language/src" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" `
  -c "from nodus import NodusRuntime; rt = NodusRuntime(); rt.register_function('test', lambda: 42, arity=0); print(rt.run_source('print(test())'))"
```
