# Companion Library Contract

**Version:** 4.0.0  
**Status:** Governing document  
**Maintainer:** Shawn Knight (Masterplanner25)

This document defines the exact surface a companion library (nodus-mcp, nodus-extension,
nodus-a2a, or any third-party library) may depend on when integrating with nodus-lang.
These APIs are stable for library authors. Everything not listed here is internal.

---

## 1. Discovery contract — how a library is found

A companion library declares itself importable by registering one entry point:

```toml
# In pyproject.toml:
[project.entry-points."nodus.nd"]
my-library = "my_package.nd:get_nd_root"
```

**Contract:**
- The entry-point group is `nodus.nd`. This name is frozen.
- The callable `get_nd_root()` takes no arguments and returns the absolute path to
  the directory containing the library's `.nd` source files.
- The returned path must exist and contain at least one `.nd` file (typically `index.nd`).
- The callable must not raise. If the library is misconfigured, return `None` or raise
  `ImportError` — both cause the import to fail with a clear error.
- After `pip install -e . --no-deps` the entry point is immediately active.

**What nodus-lang guarantees:**
- `import "my-library"` resolves by calling `get_nd_root()` and loading `index.nd`.
- `import "my-library:submodule"` loads `submodule.nd` from the same directory.
- Resolution happens via `importlib.metadata.entry_points(group="nodus.nd", name=name)`.
- The resolution logic is tested and stable (see `test_third_party_module_resolution.py`).

---

## 2. Tool registration contract — how a library exposes tools to Nodus scripts

A library registers Python callables as tools via `NodusRuntime.tool_registry`:

```python
from nodus import NodusRuntime

rt = NodusRuntime(timeout_ms=None)
rt.tool_registry.register({
    "name": "mylib.greet",     # must be dotted namespace
    "handler": my_python_fn,
    "description": "Greet a user",
    "schema": {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"]
    },
})
```

**Contract:**
- `NodusRuntime.tool_registry` is a `ToolRegistry` instance. The interface is:
  `register(metadata)`, `unregister(name)`, `invoke(name, args)`, `lookup(name)`,
  `list_tools()`, `has(name)`.
- Tool names must be dotted (`"mylib.greet"`, not `"greet"`). This is enforced.
- Python-registered tools persist across `run_source()` calls on the same runtime instance.
- Nodus scripts call tools via `std:tool`: `tool.call("mylib.greet", {name: "Alice"})`.
- The tool schema is validated at registration time, not at call time.

**What nodus-lang guarantees:**
- `ToolRegistry` interface is stable (Stable tier in LANGUAGE_STABILITY_INDEX.md).
- Tool calls from Nodus scripts reach the registered Python handler.
- Handler exceptions are caught and translated to Nodus error records.

---

## 3. Host function registration contract — lower-level than tools

For library internals that should not be user-visible as `std:tool` tools:

```python
rt.register_function("_mylib_internal", handler_fn, arity=2)
```

**Contract:**
- `register_function(name, fn, arity)` is Stable.
- Host functions are called from Nodus scripts by name: `_mylib_internal(a, b)`.
- Cannot shadow builtin names. Raises `ValueError` if attempted.
- Arguments are marshaled Python→Nodus automatically (see §5).

---

## 4. Runtime invocation contract — what a library may call on the runtime

A companion library's Python code may call:

| API | Tier | Notes |
|-----|------|-------|
| `NodusRuntime(...)` constructor | Stable | All constructor params documented in LANGUAGE_STABILITY_INDEX.md |
| `rt.run_source(source, ...)` | Stable | Returns `{ok, stdout, stderr, error}` dict |
| `rt.run_file(path, ...)` | Stable | Returns same dict; ok=False for missing files |
| `rt.register_function(name, fn, arity)` | Stable | |
| `rt.tool_registry.register/invoke/...` | Stable | |
| `rt.set_trace_id(id)` | Mostly Stable | |
| `rt.set_effect_store(store)` | Mostly Stable | |
| `rt.reset()` | Stable | |
| `rt.shutdown()` | Stable | |
| `rt.last_vm` | Internal | May be used read-only for inspection; do not modify |

**What a library must NOT do:**
- Import from `nodus.vm.vm` or `nodus.runtime.scheduler` directly for production code.
  These are internal. Anything accessed through them has no stability guarantee.
- Modify `rt.last_vm` state directly.
- Depend on `nodus.tooling.*` (tooling modules are CLI-facing, not library-facing).

---

## 5. Type marshaling contract — Python↔Nodus value translation

When Python and Nodus values cross the boundary:

| Python type | Nodus value | Notes |
|-------------|-------------|-------|
| `None` | `nil` | |
| `bool` | `bool` | |
| `str` | `string` | |
| `int` | `int` | |
| `float` (whole number) | `int` | e.g. `42.0` → `42i` |
| `float` (fractional) | `number` | |
| `list` | `list` | Elements recursively marshaled |
| `dict` | `map` | Keys stringified |
| `Record` (Nodus runtime) | `dict` | `record.fields` dict returned |

This marshaling happens automatically for host functions and tool handlers.
The full table is in `docs/guide/embedding-nodus.md §7`.

---

## 6. `.nd` module authoring contract — what a library's Nodus code may use

A library's `.nd` files ship inside the package and are importable as:
`import "my-library"` or `import "my-library:submodule"`.

**Contract:**
- `.nd` files may use any **Stable** language surface (see LANGUAGE_STABILITY_INDEX.md).
- `.nd` files may call host functions registered by the library's Python `attach_to_runtime()`
  or equivalent setup function.
- `.nd` files must not depend on internal builtins (names starting with `_`).
- `.nd` files should use the `_mylib_` prefix convention for host function names to avoid
  collision with the `std:` namespace and user-defined names.

---

## 7. Error translation contract

When a Python host function raises an exception, nodus-lang catches it and wraps it:

```python
# Python:
def my_fn(arg):
    raise ValueError("bad input")

# Nodus receives:
# err record with kind="host_error", message="bad input"
```

Libraries should raise standard Python exceptions. The error kind and message are
preserved. Stack traces from Python are NOT forwarded to Nodus scripts (they go to
the host's logging).

---

## 8. Compatibility promises

| What | Promise |
|------|---------|
| `nodus.nd` entry-point group name | **Frozen.** Will not change. |
| `NodusRuntime` public API | **Stable.** Breaking changes require major version bump. |
| `ToolRegistry` interface | **Stable.** |
| `register_function` interface | **Stable.** |
| Type marshaling rules | **Stable.** |
| `.nd` stable language surface | **Stable.** |
| Host function name collision behavior | **Stable.** Raises `ValueError`. |
| Internal VM/scheduler APIs | **No promise.** Not part of the contract. |

**Versioning:** The companion library contract version matches the nodus-lang version
that introduced each stability guarantee. A library that depends only on this contract
will work on any nodus-lang version ≥ the version where the feature it uses became Stable.

---

## 9. Minimum viable companion library structure

```
my-library/
  pyproject.toml          # declares nodus.nd entry point
  my_package/
    __init__.py
    nd.py                 # exports get_nd_root()
    nd/
      index.nd            # main .nd module
      submodule.nd        # optional
  tests/
    test_entry_point.py   # verifies entry point resolves
    test_integration.py   # verifies import + tool invocation
```

See `docs/guide/library-entry-points.md` for the full authoring guide.

---

## Related documents

- `docs/guide/library-entry-points.md` — entry-point authoring guide (how-to)
- `docs/guide/embedding-nodus.md` — NodusRuntime embedding guide
- `docs/guide/ai-primitives.md` — std:tool usage from Nodus scripts
- `docs/governance/LANGUAGE_STABILITY_INDEX.md` — stability tiers for all surfaces
- `docs/governance/ECOSYSTEM_BOUNDARY.md` — what the Nodus ecosystem is/isn't
- `docs/governance/ECOSYSTEM_READINESS_ASSESSMENT.md` — per-library readiness
