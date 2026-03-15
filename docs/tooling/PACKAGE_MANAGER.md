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
- version requirements resolved from a registry (local or remote HTTP)
- `{ path = "./relative/path" }` for local dependencies

### Semver constraint syntax

| Constraint | Meaning |
|---|---|
| `"^1.0.0"` | Compatible: `>=1.0.0, <2.0.0` |
| `"~1.0.0"` | Patch-level: `>=1.0.0, <1.1.0` |
| `"1.0.0"` | Exact version only |
| `">=1.0.0"` | Minimum version (no upper bound) |

Example manifest with constraints:

```toml
[package]
name = "myapp"
version = "0.1.0"

[dependencies]
mypackage = "^1.0.0"
otherlib  = "~2.1.0"
exactpkg  = "1.0.0"
locallib  = { path = "../locallib" }
```

Resolution is tooling-only. Runtime execution never contacts the network.

## Commands

- `nodus init` initializes `nodus.toml`, `src/main.nd`, and `.nodus/modules/`
- `nodus install` installs dependencies from the manifest
- `nodus install --registry <url>` installs using the specified HTTP registry URL
- `nodus add <package> "<constraint>"` adds a registry dependency to `nodus.toml` (e.g. `nodus add mypackage "^1.0.0"`), installs it, and updates `nodus.lock`
- `nodus add <package> --path <rel-path>` adds a local path dependency
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

## Registry Installation

Version dependencies (e.g. `utils = "^1.0.0"`) can be resolved and installed from an HTTP registry.

### Configuration priority

1. `--registry <url>` CLI flag (not yet wired to CLI arg parsing; pass via `install_dependencies_for_project(registry_url=...)`)
2. `NODUS_REGISTRY_URL` environment variable
3. `registry_url` field in `[package]` section of `nodus.toml`
4. If none set: falls back to the local `.nodus/registry.toml`

### nodus.toml with registry URL

```toml
[package]
name = "myapp"
version = "0.1.0"
registry_url = "https://registry.example.com"

[dependencies]
utils = "^1.0.0"
```

### Registry protocol

The registry must serve JSON at `GET {registry_url}/packages/{name}`:

```json
{
  "name": "utils",
  "versions": [
    {
      "version": "1.0.0",
      "url": "https://registry.example.com/dist/utils-1.0.0.tar.gz",
      "sha256": "abcdef..."
    }
  ]
}
```

Archives may be `.tar.gz`, `.tgz`, or `.zip`. A leading top-level directory inside the archive is automatically stripped.

SHA-256 of the downloaded archive is verified before extraction. The lockfile records `source = "registry"`.

### Lockfile output for registry deps

```toml
[[package]]
name = "utils"
version = "1.0.0"
source = "registry"
url = "https://registry.example.com/dist/utils-1.0.0.tar.gz"
hash = "sha256:..."
path = ".nodus/modules/utils"
```

### Error handling

- `RegistryError` is raised on network failures, HTTP errors, or checksum mismatches.
- On version constraint mismatch, the error message lists all available versions returned by the registry.
- Checksum verification happens before extraction; a mismatch aborts install and raises `RegistryError`.

Note: v0.9 will add `nodus publish` and registry authentication.

## Notes
- The package manager is local-first and keeps runtime execution separate from manifest parsing and dependency resolution.
- Legacy manifests that place `name` and `version` at the top level still load, but new projects should use `[package]`.
- Module resolution checks project modules first, then `.nodus/modules`, then stdlib.
