Implement the DAP evaluate command for the Nodus debug adapter (DAP-001).
When a user is paused at a breakpoint in VS Code or any DAP client, they
should be able to evaluate expressions in the debug console. Currently
all evaluate requests return an error or no response.

GitHub: https://github.com/Masterplanner25/Nodus/issues/106

Arguments: $ARGUMENTS
(Omit to implement. Pass "design" to read the DAP spec section and confirm
the plan before making changes.)

## Pre-flight checks

1. Read `src/nodus/dap/server.py` — understand `handle_message()` structure,
   `DebugSession`, and what state it holds about the current VM.
2. Check which DAP commands are implemented (grep for `if command ==` in
   `handle_message`) — confirm `evaluate` is absent.
3. Read `tests/test_dap_server.py` — understand the test pattern.
4. Run the existing DAP tests:
   ```powershell
   cd "C:\dev\Coding Language"
   PYTHONPATH="C:/dev/Coding Language/src" `
     "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/test_dap_server.py -v
   ```

## DAP evaluate request spec

The client sends:
```json
{
  "command": "evaluate",
  "arguments": {
    "expression": "<nodus expression>",
    "frameId": 1,
    "context": "repl"    // "repl" | "watch" | "hover" | "clipboard"
  }
}
```

The server responds:
```json
{
  "result": "<string representation of result>",
  "type": "<optional type string>",
  "variablesReference": 0
}
```

`variablesReference` > 0 means the result can be further expanded.
For v1, always return 0 (atomic result, no expansion needed).

On error, send an error response (not a crash):
```json
{"success": false, "message": "<error description>"}
```

## Implementation

### Step 1 — `handle_message` in DebugAdapterServer

Add after the existing `variables` branch:

```python
if command == "variables":
    variables_reference = int(arguments.get("variablesReference", 0))
    self.send_response(request_seq, command, {"variables": self.session.variables(variables_reference)})
    return False

if command == "evaluate":
    expression = arguments.get("expression", "")
    frame_id = int(arguments.get("frameId", 0))
    context = arguments.get("context", "repl")
    result, type_name, error = self.session.evaluate(expression, frame_id, context)
    if error is not None:
        self.send_error(request_seq, command, error)
    else:
        self.send_response(request_seq, command, {
            "result": result,
            "type": type_name,
            "variablesReference": 0,
        })
    return False
```

### Step 2 — `DebugSession.evaluate` method

Add to the `DebugSession` class:

```python
def evaluate(self, expression: str, frame_id: int, context: str) -> tuple[str, str, str | None]:
    """Evaluate a Nodus expression in the current debug context.
    
    Returns: (result_str, type_name, error_message)
    On success: error_message is None.
    On failure: result_str and type_name are empty strings.
    """
    vm = self._vm
    if vm is None:
        return "", "", "No active debug session"
    
    # Wrap in a run-source call with the current VM's globals
    from nodus.frontend.lexer import tokenize
    from nodus.frontend.parser import Parser
    from nodus.compiler.compiler import Compiler
    from nodus.runtime.module_loader import ModuleLoader
    
    try:
        # Compile the expression as a program: let __eval_result__ = <expr>
        # so we can read it back from globals after execution
        wrapped = f"let __eval_result__ = ({expression})\n"
        loader = ModuleLoader(project_root=None)
        code, functions, code_locs = loader.compile_only(
            wrapped, module_name="<eval>"
        )
    except Exception as exc:
        return "", "", f"Compile error: {exc}"
    
    # Create a child VM that inherits the current globals
    from nodus.vm.vm import VM
    child_vm = VM(
        code, functions,
        code_locs=code_locs,
        initial_globals=dict(vm.globals),
        host_globals=getattr(vm, "host_globals", None),
    )
    try:
        child_vm.run()
        result_val = child_vm.globals.get("__eval_result__")
        result_str = child_vm.value_to_string(result_val, quote_strings=True)
        type_name = child_vm.builtin_type(result_val)
        return result_str, str(type_name), None
    except Exception as exc:
        return "", "", str(exc)
```

### Step 3 — Tests

Add to `tests/test_dap_server.py`:

```python
def test_evaluate_expression_at_breakpoint(self):
    """evaluate command returns expression result in debug context."""
    # Launch a script that hits a breakpoint, then evaluate
    src = "let x = 42\nprint(x)\n"
    ...  # set up session with source, hit breakpoint at line 1
    
    msg = {
        "type": "request",
        "command": "evaluate",
        "seq": 10,
        "arguments": {"expression": "x + 1", "frameId": 1, "context": "repl"}
    }
    result = server.handle_message(msg)
    # Verify send_response was called with result containing "43"

def test_evaluate_syntax_error_returns_error_response(self):
    """evaluate with bad expression sends error response, not crash."""
    msg = {
        "type": "request",
        "command": "evaluate",
        "seq": 11,
        "arguments": {"expression": "let x = }", "frameId": 1, "context": "repl"}
    }
    # Should call send_error, not raise

def test_evaluate_undefined_variable_returns_error(self):
    """evaluate with undefined variable sends error response."""
    msg = {
        "type": "request",
        "command": "evaluate",
        "seq": 12,
        "arguments": {"expression": "undefined_var", "frameId": 1, "context": "repl"}
    }
    # Should call send_error
```

## Key constraints

- **Never crash the DAP server on a bad expression.** Always return a proper DAP
  error response. The server must stay alive across evaluate failures.
- **Read-only evaluation.** The child VM receives a *copy* of `vm.globals` (not
  a reference). Side effects on the evaluated expression do NOT modify the paused
  VM's state.
- **Security:** `evaluate` runs arbitrary Nodus code. If the DAP server is
  configured with `allowed_paths`, pass them to the child VM. Do not weaken sandboxing.
- **`variablesReference: 0`** for all results in v1 (no drill-down). Variable
  drill-down can be added in a later pass.
- **`context` field:** for v1, treat `"repl"`, `"watch"`, `"hover"`, and
  `"clipboard"` identically — evaluate and return the string representation.
  Context-specific formatting can be added later.

## Dev environment

```powershell
cd "C:\dev\Coding Language"

# Run DAP tests
PYTHONPATH="C:/dev/Coding Language/src" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/test_dap_server.py -v

# Run full suite regression guard
PYTHONPATH="C:/dev/Coding Language/src" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q --tb=no `
  --ignore=tests/test_scheduler_fairness.py
```

## Commit and push

```powershell
git commit -m @'
feat(dap): implement evaluate command for interactive expression evaluation

DAP evaluate request: compiles expression as "let __eval_result__ = (expr)",
runs in a child VM with a copy of the paused VM globals, returns string
representation and type name. Child VM is read-only (copy of globals, not
reference). Bad expressions return DAP error responses, not server crashes.

Tests added: evaluate at breakpoint, syntax error, undefined variable.
Closes #106 (DAP-001).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

Push to `github.com/Masterplanner25/Nodus`.
