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

## Install

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

## Documentation

- [Language Specification](docs/language/LANGUAGE_SPEC.md) — full syntax, types, control flow, imports, coroutines
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
  "version": "1.1.2",
  "softwareRequirements": "Python >= 3.10"
}
</script>
