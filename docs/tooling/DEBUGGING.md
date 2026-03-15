# Debugging

Nodus exposes two debugging entrypoints built on the same runtime debugger:

- `nodus debug <script.nd>` for the built-in interactive debugger
- `nodus dap` for IDE clients that speak the Debug Adapter Protocol

The debug adapter reuses the existing runtime debugger hooks in `src/nodus/runtime/debugger.py`. It does not implement a second debugger or duplicate stepping and breakpoint logic in a separate execution engine.

## Interactive Debugger

Run:

```bash
nodus debug script.nd
```

The interactive debugger starts paused before the first instruction.

Supported commands:

- `step`
- `next`
- `out` / `stepout`
- `continue` / `run`
- `break <line>`
- `break <file>:<line>`
- `print <variable>`
- `stack`
- `locals`
- `quit`

Notes:

- Breakpoints are line-based and module-aware.
- Pauses use compiler-provided source locations.
- `locals` shows function locals or top-level globals when no function frame is active.

## Debug Adapter Protocol

Run the adapter over stdio:

```bash
nodus dap
```

The adapter uses standard DAP `Content-Length` framing on stdin/stdout.

### Supported Requests

- `initialize`
- `launch`
- `disconnect`
- `setBreakpoints`
- `continue`
- `pause`
- `next`
- `stepIn`
- `stepOut`
- `stackTrace`
- `scopes`
- `variables`

### Launch Arguments

The `launch` request accepts:

- `program`: path to the `.nd` file to debug
- `projectRoot`: optional project root for runtime import resolution

Execution starts paused at entry so the client can register breakpoints before continuing.

### Data Exposed To Editors

- Breakpoints are mapped by source path and line number.
- Stack traces come from VM/runtime debugger frame information.
- Variables expose function arguments and locals as name/value pairs.
- Script stdout and stderr are forwarded as DAP `output` events.

### VS Code Example

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "type": "nodus",
      "request": "launch",
      "name": "Debug Nodus Script",
      "debugServer": 0,
      "program": "${file}"
    }
  ]
}
```

If your client supports direct stdio adapter commands:

```json
{
  "command": "nodus",
  "args": ["dap"]
}
```

## Current Limitations

- The adapter is single-session and single-threaded.
- Variable inspection is shallow; values are rendered to strings and are not yet expandable.
- Exception stop events and richer launch/attach flows are not implemented yet.
