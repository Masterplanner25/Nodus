# Making a Nodus Library Importable

This guide explains how to ship a pip-installable Python package that
also exposes Nodus (`.nd`) source files so that `import "your-library"` works
in any Nodus script after `pip install your-library`.

This is the convention all official Nodus libraries (`nodus-mcp`, `nodus-a2a`,
etc.) follow. Copy it exactly — the entry-point group name and callable
contract are fixed and shared across the ecosystem.

---

## The contract

Your Python package declares one entry point in the `nodus.nd` group:

```toml
# pyproject.toml
[project.entry-points."nodus.nd"]
your-library = "your_package.nd:get_nd_root"
```

The value is a `module:callable` reference. The callable is invoked with **no
arguments** and must return the **absolute path to the directory containing
your `.nd` source files** (the *nd root*):

```python
# src/your_package/nd.py
import os

def get_nd_root() -> str:
    """Return the absolute path to this package's .nd source root."""
    return os.path.dirname(os.path.abspath(__file__))
```

That is the complete interface. One entry point, one callable, one return value.

### Why a callable, not a static string

The installed location of a package (`site-packages/your_package/`) is only
known at runtime — the path depends on which Python interpreter, virtual
environment, and OS the package is installed into. A static string path
cannot be computed at package-author time. The callable form lets the
function compute `os.path.dirname(__file__)` relative to its own location,
which is always correct regardless of where pip put it.

---

## File layout convention

```
src/
└── your_package/
    ├── __init__.py
    ├── nd.py            # exposes get_nd_root()
    └── nd/              # the nd root directory
        ├── index.nd     # resolved by: import "your-library"
        ├── client.nd    # resolved by: import "your-library:client"
        └── server.nd    # resolved by: import "your-library:server"
```

`get_nd_root()` returns the path to `your_package/nd/`. The resolver then:

- `import "your-library"` → looks for `nd_root/index.nd` ✓
- `import "your-library:client"` → looks for `nd_root/client.nd` ✓
- `import "your-library:server/handler"` → looks for `nd_root/server/handler.nd` ✓

The `index.nd` at the nd root is required for bare `import "your-library"` to
work.

---

## Complete minimal example

**`pyproject.toml`:**

```toml
[project]
name = "nodus-example"
version = "0.1.0"
dependencies = ["nodus-lang>=4.0.0"]

[project.entry-points."nodus.nd"]
nodus-example = "nodus_example.nd:get_nd_root"

[tool.setuptools.package-data]
nodus_example = ["nd/*.nd"]
```

**`src/nodus_example/nd.py`:**

```python
import os

def get_nd_root() -> str:
    return os.path.dirname(os.path.abspath(__file__))
```

**`src/nodus_example/nd/index.nd`:**

```nd
fn hello(name) {
    return "Hello from nodus-example, " + name + "!"
}
```

**Usage after `pip install nodus-example`:**

```nd
import "nodus-example" as ex
print(ex.hello("world"))
// → Hello from nodus-example, world!
```

---

## Resolution precedence

The Nodus module resolver checks locations in this order for `import "name"`:

1. `{project_root}/name.nd` or `{project_root}/name/index.nd` — project-local file
2. `{project_root}/.nodus/modules/name/index.nd` — Nodus package manager
3. `src/nodus/stdlib/name.nd` — bundled stdlib (only for `std:*` prefix normally)
4. **`nodus.nd` entry-point lookup** — pip-installed packages ← this guide

**Local always wins.** If `.nodus/modules/your-library/index.nd` exists in the
project, it shadows the pip-installed package. This is intentional: a developer
can drop a local copy of a library into `.nodus/modules/` to override the
installed version during development.

---

## Including .nd files in the wheel

By default, setuptools does not include non-Python files. Add a
`package-data` declaration so your `.nd` files are bundled into the wheel:

```toml
[tool.setuptools.package-data]
your_package = ["nd/*.nd", "nd/**/*.nd"]
```

Verify the files are present in the built wheel before publishing:

```bash
pip wheel . -w dist/ && unzip -l dist/your_package-*.whl | grep '\.nd'
```

---

## Testing the entry point locally

During development, before publishing to PyPI, install your package in
editable mode:

```bash
pip install -e .
```

Then in any Nodus script in a project with `project_root` set:

```nd
import "your-library" as lib
print(lib.hello("developer"))
```

The entry point is active immediately after `pip install -e .` — no additional
setup steps are required. This is the key advantage of Option 3 over the
`python -m your_library init` approach: `pip install` is sufficient.

---

## Checklist for library authors

- [ ] `pyproject.toml` declares `[project.entry-points."nodus.nd"]` with
      `your-library = "your_package.nd:get_nd_root"`
- [ ] `nd.py` (or equivalent) defines `get_nd_root() -> str` returning
      `os.path.dirname(os.path.abspath(__file__))`
- [ ] `nd/index.nd` exists at the nd root (required for bare `import "name"`)
- [ ] `[tool.setuptools.package-data]` includes `nd/*.nd`
- [ ] Wheel verified to contain the `.nd` files
- [ ] `pip install -e .` + `import "name"` tested in a Nodus script

---

## What happens on failure

If `import "your-library"` fails, the error message lists all paths that were
attempted, including the entry-point check:

```
Import not found: 'your-library' (tried
  /project/your-library.nd,
  /project/.nodus/modules/your-library/index.nd,
  ...,
  <no nodus.nd entry-point for 'your-library'>   ← entry-point not registered
)
```

If the entry point is registered but the `.nd` files are missing from the
wheel, it will list the paths it tried inside the nd root before failing.
