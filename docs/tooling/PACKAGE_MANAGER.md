# Package Manager

Nodus includes a minimal, local-first package manager intended for small automation projects.

## Project Files

- `nodus.toml` manifest
- `nodus.lock` lockfile
- `.nodus/modules/` installed dependencies
- `src/main.nd` default project entrypoint

## Manifest Format

```toml
[package]
name = "example"
version = "0.1.0"

[dependencies]
utils = "1.0.0"
```

Supported sources:
- version requirements resolved from the local registry
- `{ path = "./relative/path" }` for local dependencies

Resolution is tooling-only and offline-only. Runtime execution never contacts the network.

## Commands

- `nodus init` initializes `nodus.toml`, `src/main.nd`, and `.nodus/modules/`
- `nodus install` installs dependencies from the manifest
- `nodus add <package>` adds the latest locally available registry version to `nodus.toml`, installs it, and updates `nodus.lock`
- `nodus remove <package>` removes a dependency from `nodus.toml`, prunes the local install, and updates `nodus.lock`
- `nodus package-list` lists resolved dependencies and lockfile status

`nodus deps` is reserved for the runtime module dependency graph used by incremental compilation.

## Lockfile
`nodus.lock` records the resolved dependency set in a deterministic array-of-tables format.

Example:

```toml
[[package]]
name = "json"
version = "1.2.0"
source = "registry"
hash = "sha256:abc123..."

[[package]]
name = "workflow_utils"
version = "0.1.0"
source = "path"
path = "../workflow_utils"
hash = "sha256:def456..."
```

Entries are sorted by package name so repeated installs produce stable output.

## Install Layout

Installed dependencies are copied into:

```text
.nodus/
  modules/
    json/
      module.nd
    workflow_utils/
      module.nd
```

Resolution and installation order is:

1. read `nodus.toml`
2. resolve the dependency graph
3. populate `.nodus/modules/`
4. write `nodus.lock`

## Import Resolution
Dependencies are imported using the `package:module` syntax:

```nd
import "utils:strings"
```

This resolves to `.nodus/modules/utils/strings.nd`.

## Notes
- The package manager is local-first and keeps runtime execution separate from manifest parsing and dependency resolution.
- Legacy manifests that place `name` and `version` at the top level still load, but new projects should use `[package]`.
- Module resolution checks project modules first, then `.nodus/modules`, then stdlib.
