# Nodus Debug Adapter Protocol

Nodus includes a minimal Debug Adapter Protocol server for IDE debugging over stdio.

The adapter reuses the existing runtime debugger. It does not add a second execution engine, and it does not move project or package logic into the runtime.

## Capabilities

The current adapter supports:

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

Breakpoints are source-path and line based. Stack traces and variables come from the runtime VM and debugger frame state.

## Starting The Adapter

Run the adapter over stdio:

```bash
nodus dap
```

The adapter uses standard DAP `Content-Length` framing on stdin/stdout.

## Launch Arguments

The `launch` request currently accepts:

- `program`: absolute or relative path to the `.nd` script to debug
- `projectRoot`: optional project root used for runtime import resolution

The debuggee starts paused at entry so the client can register breakpoints before execution continues.

## VS Code Example

You can connect with a local debug extension or a generic DAP client. A minimal launch configuration looks like this:

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

If your client supports direct stdio adapter commands instead of a wrapper extension, launch:

```json
{
  "command": "nodus",
  "args": ["dap"]
}
```

## Design Notes

- The adapter is implemented under tooling as `src/nodus/dap/server.py`.
- Execution still happens in the existing VM with the existing runtime debugger hooks.
- Script stdout and stderr are surfaced as DAP `output` events so the protocol stream stays valid.
- Variables currently expose function arguments and locals as name/value pairs.

## Current Limitations

- The adapter is single-session and single-threaded.
- Variable inspection is currently shallow; values are rendered to strings and are not yet expandable.
- Exception stop events and richer launch options are not implemented yet.
