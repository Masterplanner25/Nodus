Build the cross-package install and discovery CI for the Nodus ecosystem (Milestone 2).
Goal: a clean-venv install of nodus-lang + nodus-mcp resolves, imports, and executes
correctly — verified in CI on every push, not just in dev-install mode.

No prerequisites. Can run independently of library graduation phases.

## What this delivers

1. A GitHub Actions workflow at `.github/workflows/ecosystem.yml` that:
   - Creates a clean venv
   - Installs nodus-lang from TestPyPI (or the built wheel from main)
   - Installs nodus-mcp from its repo (editable dev install until published)
   - Runs a minimal smoke script verifying discovery + tool registration + invocation

2. A smoke script at `tests/ecosystem/test_ecosystem_smoke.py`:
   - `import "nodus-mcp"` resolves in a Nodus script
   - A tool registered from Python is callable from Nodus
   - The result dict has the correct shape

3. Update nodus-mcp README to remove the "dev source" install caveat once CI passes.

## Implementation

### Step 1 — Smoke test script

Create `tests/ecosystem/test_ecosystem_smoke.py`:

```python
"""Ecosystem smoke test: clean install + discovery + tool invocation."""
import sys, unittest
from nodus import NodusRuntime

class EcosystemSmokeTests(unittest.TestCase):
    def test_nodus_mcp_entry_point_resolves(self):
        from nodus.runtime.module_loader import _resolve_installed_package
        path = _resolve_installed_package("nodus-mcp")
        self.assertIsNotNone(path, "nodus-mcp entry point did not resolve")
        import os
        self.assertTrue(os.path.isdir(path), f"nodus-mcp nd root not a directory: {path}")

    def test_nodus_mcp_importable_from_script(self):
        rt = NodusRuntime(timeout_ms=5000, max_steps=100000)
        result = rt.run_source('import "nodus-mcp"\nprint("ok")')
        self.assertTrue(result["ok"], f"nodus-mcp import failed: {result.get('error')}")
        self.assertIn("ok", result["stdout"])

    def test_tool_registration_and_invocation(self):
        rt = NodusRuntime(timeout_ms=5000, max_steps=100000)
        rt.tool_registry.register({
            "name": "smoke.echo",
            "handler": lambda msg: {"echoed": msg},
            "description": "Echo a message",
            "schema": {"type": "object", "properties": {"msg": {"type": "string"}}, "required": ["msg"]},
        })
        result = rt.run_source('''
import "std:tool" as tool
let r = tool.call("smoke.echo", {msg: "hello"})
print(r.echoed)
''')
        self.assertTrue(result["ok"], str(result.get("error")))
        self.assertIn("hello", result["stdout"])
```

### Step 2 — Ecosystem CI workflow

Create `.github/workflows/ecosystem.yml`:

```yaml
name: Ecosystem

on:
  push:
  pull_request:

jobs:
  ecosystem-smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install nodus-lang (dev wheel)
        run: |
          python -m pip install build wheel
          python -m build --wheel
          python -m pip install dist/nodus_lang-*.whl

      - name: Install nodus-mcp (dev editable)
        run: |
          # Once published, this becomes: pip install nodus-mcp
          pip install -e "C:/dev/nodus-mcp" --no-deps

      - name: Ecosystem smoke test
        run: python -m pytest tests/ecosystem/ -v
```

Note: the `pip install -e "C:/dev/nodus-mcp"` path is Linux/Windows specific.
For CI, either:
- Clone nodus-mcp as a submodule, OR
- Reference the GitHub repo directly: `pip install git+https://github.com/Masterplanner25/nodus-mcp.git`

Use the git+ form until nodus-mcp is published to PyPI.

### Step 3 — README caveat removal (nodus-mcp)

Once the ecosystem CI passes reliably, update `C:\dev\nodus-mcp\README.md`:
- Remove the "Once nodus-lang 4.0.0 is on PyPI: pip install nodus-mcp" caveat.
- Replace with the standard install instructions.
- Note that the CI badge reflects clean-install status.

## Exit criteria

- `tests/ecosystem/test_ecosystem_smoke.py` passes in a clean venv
- `.github/workflows/ecosystem.yml` passes in CI
- nodus-mcp README no longer has dev-source caveats for normal install

## Dev environment

```powershell
cd "C:\dev\Coding Language"

# Run smoke test manually
pip install -e "C:\dev\nodus-mcp" --no-deps
PYTHONPATH="C:/dev/Coding Language/src" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" `
  -m pytest tests/ecosystem/ -v
```
