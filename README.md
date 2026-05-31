# Nodus

[![CI](https://github.com/Masterplanner25/nodus-lang/actions/workflows/ci.yml/badge.svg)](https://github.com/Masterplanner25/nodus-lang/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/nodus-lang.svg)](https://pypi.org/project/nodus-lang/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

```bash
pip install nodus-lang
nodus init
nodus run
nodus repl
```

Nodus is a bytecode-compiled scripting language and runtime created by **Shawn Knight** as part of the Masterplan Infinite Weave ecosystem. It implements the Infinity Algorithm's execution model as a first-class language construct, expressed through coroutines, task graphs, workflows, and goals on a deterministic stack-based VM.

For a machine-readable project index see [llms.txt](llms.txt).

The Nodus ecosystem spans **29 standalone packages** across 6 tiers, all available at
`github.com/Masterplanner25`. A unified SDK (`nodus-sdk`) provides a single installation
story: `pip install nodus-sdk[agent,sql,fastapi]`. Incubator design scaffolds live under
`packages/`; production packages live at `C:\dev\`.

## Install

Requires **Python 3.10+**.

```bash
pip install nodus-lang
```

For the optional FastAPI/Uvicorn server stack:

```bash
pip install "nodus-lang[server]"
```

## Quick Start

Create a project:

```bash
mkdir my-app
cd my-app
nodus init
nodus run
```

`nodus init` creates `nodus.toml` and `src/main.nd`.

`nodus run` executes the current project's `src/main.nd` when run inside a project root.

Start the REPL:

```bash
nodus repl
```

Useful REPL commands:

- `:help` shows REPL commands.
- `:quit` exits the REPL.

## Run A File

Create `hello.nd`:

```nd
print("hello")
```

Run it explicitly:

```bash
nodus run hello.nd
```

When you provide a file path, Nodus runs only that file. When you run `nodus run` with no file inside a project, Nodus runs only `src/main.nd`.

## Common Commands

- `nodus --version`
- `nodus run hello.nd`
- `nodus run`
- `nodus repl`
- `nodus check hello.nd`
- `nodus check`
- `nodus fmt hello.nd`

## Standard Library

Import standard library modules with the `std:` prefix:

```nd
import "std:math" as math
print(math.abs(-4))
```

**v4.1 AI-native stdlib additions:**

| Module | Purpose |
|---|---|
| `std:identity` | `trace_id()`, `session_id()`, `execution_unit_id()` — auto-propagated |
| `std:effects` | EXACTLY_ONCE idempotency: `resolve`, `pending`, `complete`, `action_id` |
| `std:sys` | `sys.v1.*` versioned syscall dispatch with uniform `{status, data, error, trace_id}` envelope |
| `std:memory` | Extended: `recall_from(ns, key)`, `recall_all(ns)`, `share(ns, key, val)` |
| `std:retry` | `retry.call(func, policy_map)` — wraps nodus-retry (optional dep) |
| `std:circuit_breaker` | `cb.create/call/state/reset` — wraps nodus-circuit-breaker (optional dep) |

## Documentation

- [Language Specification](docs/language/LANGUAGE_SPEC.md) — full syntax, types, control flow, imports, coroutines
- [Ecosystem Specs](docs/ecosystem/README.md) - implementation specs for proposed Nodus libraries and frameworks
- [Architecture](docs/runtime/ARCHITECTURE.md) — runtime pipeline and module system
- [Changelog](CHANGELOG.md) — version history
- [Contributing](CONTRIBUTING.md) — development setup, code style, and contribution process
- [llms.txt](llms.txt) — machine-readable project index for AI tools

<!-- Structured metadata for search engines and AI indexers (schema.org/SoftwareApplication) -->
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "name": "Nodus",
  "description": "A bytecode-compiled scripting language and distributed workflow runtime implementing the Infinity Algorithm as a first-class language construct.",
  "author": {
    "@type": "Person",
    "name": "Shawn Knight",
    "url": "https://github.com/Masterplanner25"
  },
  "applicationCategory": "DeveloperApplication",
  "programmingLanguage": "Python",
  "operatingSystem": "Linux, macOS, Windows",
  "url": "https://github.com/Masterplanner25/nodus-lang",
  "downloadUrl": "https://pypi.org/project/nodus-lang/",
  "license": "https://spdx.org/licenses/MIT.html",
  "version": "4.0.0",
  "softwareRequirements": "Python >= 3.10"
}
</script>
